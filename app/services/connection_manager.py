import logging
from typing import Dict, Set
from fastapi import WebSocket
from app.services.cache_service import cache_service

logger = logging.getLogger("orbitchat.connection_manager")

class ConnectionManager:
    """
    Stateful Connection Hub.
    Manages direct live TCP/IP WebSocket pipes, matching authenticated User IDs 
    to physical connection instances residing on this node.
    """
    def __init__(self):
        # Memory Matrix: Maps User ID -> Set of active WebSocket connections
        # Supports multi-device logins (e.g., Laptop, iPad, and Phone online simultaneously)
        self.active_connections: Dict[int, Set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        """
        Accepts an inbound stateful connection, registers it in local memory,
        and synchronizes the user's online availability state inside Redis.
        """
        # Accept the low-level handshake protocol
        await websocket.accept()

        # Add connection instance to our localized multi-device map
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

        # Broadcast presence status globally via our in-memory cache layer
        await cache_service.set_user_online(user_id=user_id, heartbeat_seconds=60)
        
        logger.info(f"TCP/IP Pipeline locked: User ID {user_id} added. Total devices active: {len(self.active_connections[user_id])}")

    async def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        """
        Cleans up memory references when a client drops their connection pipe,
        and scrubs presence flags if no other active devices remain online.
        """
        if user_id in self.active_connections:
            # Safely remove this specific device pipe from the set
            self.active_connections[user_id].discard(websocket)
            
            # If no other device pipes exist for this user, completely clear their room
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
                # Scrub presence flag from Redis hot cache layer
                await cache_service.set_user_offline(user_id=user_id)
                logger.info(f"Presence Offline: User ID {user_id} has disconnected all active devices.")
            else:
                logger.info(f"Device disconnected for User ID {user_id}. {len(self.active_connections[user_id])} devices remain.")

    async def send_personal_message(self, message: str, websocket: WebSocket) -> None:
        """
        Direct frame injection targeting a single distinct network interface pipe.
        """
        await websocket.send_text(message)

    async def broadcast_to_local_user(self, user_id: int, payload: str) -> None:
        """
        Broadcasts a data payload to EVERY device instance owned by a specific user 
        that is currently routed to this specific application server node.
        """
        connections = self.active_connections.get(user_id)
        if connections:
            for socket in connections:
                try:
                    await socket.send_text(payload)
                except Exception as error:
                    # Catch dangling or broken sockets that didn't clean up correctly
                    logger.error(f"Failed to inject frame down broken socket for User {user_id}: {str(error)}")

# Instantiate a global connection manager singleton for this application node
manager = ConnectionManager()