import logging
from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from app.database.connection import get_db_session
from app.database.models import GroupChannel, GroupMember, User
from app.services.auth_service import AuthService
import json
from fastapi import WebSocket, WebSocketDisconnect
from app.services.connection_manager import manager
from app.services.cache_service import cache_service

router = APIRouter(prefix="/v1/chat", tags=["Chat Channels"])
logger = logging.getLogger("orbitchat.chat_router")

# =========================================================================
# INTERNAL SECURITY DEPENDENCY: STATELESS JWT EXTRACTION
# =========================================================================
async def get_current_user_id(authorization: str = Header(..., description="Bearer JWT Token")) -> int:
    """
    Extracts and cryptographically validates the User ID from the HTTP Authorization Header.
    Throws a fast 401 response if the signature or token layout is broken.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format. Must start with 'Bearer '"
        )
    
    token = authorization.split(" ")[1]
    payload = AuthService.verify_access_token(token)
    
    # Extract the subject ('sub') claim containing the structural User ID string
    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token identity payload is missing its subject claim."
        )
    
    return int(user_id_str)


# =========================================================================
# ENDPOINTS
# =========================================================================

@router.post("/channels/create", status_code=status.HTTP_201_CREATED)
async def create_channel(
    name: str,
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """
    HTTP POST Endpoint to provision a new group channel workspace.
    Automatically binds the creator as the first permanent member of the room.
    """
    # 1. Instantiate the channel container
    new_channel = GroupChannel(name=name, creator_id=current_user_id)
    db.add(new_channel)
    await db.flush()  # Push to database to populate new_channel.id

    # 2. Automatically register the creator into the membership access ledger
    creator_membership = GroupMember(user_id=current_user_id, channel_id=new_channel.id)
    db.add(creator_membership)
    
    logger.info(f"User ID {current_user_id} successfully provisioned Channel '{name}' (ID: {new_channel.id})")
    
    return {
        "channel_id": new_channel.id,
        "name": new_channel.name,
        "creator_id": new_channel.creator_id,
        "created_at": new_channel.created_at
    }


@router.post("/channels/{channel_id}/join", status_code=status.HTTP_200_OK)
async def join_channel(
    channel_id: int,
    current_user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db_session)
):
    """
    HTTP POST Endpoint to add a user to an existing channel's access list.
    Enforces a strict industrial scale ceiling limit of 100 members max per group.
    """
    # 1. Verify that the target channel actually exists
    channel_query = select(GroupChannel).where(GroupChannel.id == channel_id)
    channel_result = await db.execute(channel_query)
    channel = channel_result.scalars().first()
    if not channel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The targeted chat channel does not exist inside our records."
        )

    # 2. Check for an existing membership connection to prevent duplicates
    member_check = select(GroupMember).where(
        GroupMember.user_id == current_user_id,
        GroupMember.channel_id == channel_id
    )
    member_check_result = await db.execute(member_check)
    if member_check_result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already an active registered member of this group channel."
        )

    # 3. Scale Ceiling Guard: Enforce our strict max limit of 100 members per room
    count_query = select(func.count(GroupMember.id)).where(GroupMember.channel_id == channel_id)
    count_result = await db.execute(count_query)
    current_member_count = count_result.scalar() or 0

    if current_member_count >= 100:
        logger.warning(f"Join rejected: Channel {channel_id} has reached its performance limit of 100 members.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This group channel has reached its industrial scaling capacity ceiling limit of 100 members."
        )

    # 4. Save the secure membership link
    new_membership = GroupMember(user_id=current_user_id, channel_id=channel_id)
    db.add(new_membership)
    
    logger.info(f"User ID {current_user_id} has joined Channel ID {channel_id} (Current occupancy: {current_member_count + 1}/100)")
    return {"message": "Successfully joined the group channel.", "channel_id": channel_id}

# =========================================================================
# STATEFUL CORE: REAL-TIME WEBSOCKET ROUTE
# =========================================================================

@router.websocket("/ws/{channel_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    channel_id: int,
    token: str
):
    """
    Stateful Duplex WebSocket Gateway.
    Authenticates incoming streaming pipes, checks channel roster permissions,
    and handles high-concurrency real-time message routing.
    """
    # 1. Stateless Identity Authentication Handshake
    try:
        payload = AuthService.verify_access_token(token)
        user_id = int(payload.get("sub"))
    except Exception:
        # WebSockets cannot use traditional HTTP exceptions, they must close the frame directly
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(f"WebSocket handshake aborted: Malformed or expired security token.")
        return

    # 2. Stateful Authorization Guard: Roster Membership ACL Check
    # We open a dedicated connection block to verify membership from PostgreSQL
    async for db in get_db_session():
        membership_query = select(GroupMember).where(
            GroupMember.user_id == user_id,
            GroupMember.channel_id == channel_id
        )
        membership_result = await db.execute(membership_query)
        is_member = membership_result.scalars().first()
        
        if not is_member:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            logger.warning(f"WebSocket entry blocked: User ID {user_id} lacks access rights to Channel {channel_id}")
            return
        break # Break out cleanly once our contextual transaction yields the check

    # 3. Connection Authorization and Registration
    await manager.connect(user_id=user_id, websocket=websocket)

    # 4. Continuous Real-Time Duplex Network Processing Loop
    try:
        while True:
            # Continuously monitor the TCP pipe for incoming text payloads
            raw_data = await websocket.receive_text()
            
            try:
                parsed_json = json.loads(raw_data)
                message_content = parsed_json.get("text", "").strip()
            except json.JSONDecodeError:
                logger.warning(f"Discarding corrupt non-JSON frame dropped by User ID {user_id}")
                continue

            if not message_content:
                continue

            # 5. Fetch an Atomic Sequence ID from Redis to maintain chronological tracking
            sequence_id = await cache_service.generate_next_sequence_id(channel_id=channel_id)

            # 6. Build the Outbound Message Frame
            outbound_payload = {
                "channel_id": channel_id,
                "sender_id": user_id,
                "sequence_id": sequence_id,
                "text": message_content
            }
            serialized_payload = json.dumps(outbound_payload)

            # 7. Route and Broadcast the Frame
            # At our current local node layout, we find everyone connected to this server instance
            # In a distributed cluster, this triggers our NoSQL storage pipeline and Pub/Sub mechanism
            async for db in get_db_session():
                # Find all members belonging to this room
                roster_query = select(GroupMember.user_id).where(GroupMember.channel_id == channel_id)
                roster_result = await db.execute(roster_query)
                channel_members = roster_result.scalars().all()

                # Broadcast to every active target connection on this machine
                for member_id in channel_members:
                    await manager.broadcast_to_local_user(user_id=member_id, payload=serialized_payload)
                break

    except WebSocketDisconnect:
        # Handle clean socket disconnects (e.g., app closed, tab killed)
        await manager.disconnect(user_id=user_id, websocket=websocket)
        logger.info(f"Clean socket teardown finalized for User ID {user_id}")
        
    except Exception as runtime_error:
        # Catch unexpected socket failures or hardware drops safely
        logger.error(f"Force breaking crashed socket for User ID {user_id}: {str(runtime_error)}")
        await manager.disconnect(user_id=user_id, websocket=websocket)