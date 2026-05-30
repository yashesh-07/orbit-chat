import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database.connection import get_db_session
from app.database.models import User
from app.schemas.auth import UserRegisterRequest, UserLoginRequest, UserResponse, TokenResponse
from app.services.auth_service import AuthService

# Initialize isolated domain router and logger
router = APIRouter(prefix="/v1/auth", tags=["Authentication"])
logger = logging.getLogger("orbitchat.auth_router")

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    payload: UserRegisterRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """
    HTTP POST Endpoint to register new user entities.
    Enforces strict username and email uniqueness constraints via async execution.
    """
    # 1. Check for existing conflicts (Username or Email)
    query = select(User).where((User.username == payload.username) | (User.email == payload.email))
    result = await db.execute(query)
    existing_user = result.scalar()  # Safe extraction from scalar results

    if existing_user:
        logger.warning(f"Registration rejected: Identity collision on username/email.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account with this username or email already exists inside our systems."
        )

    # 2. Convert plain text password into a secure, salted bcrypt cryptographic hash
    hashed_pass = AuthService.hash_password(payload.password)

    # 3. Instantiate and persist the structural User model
    new_user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hashed_pass
    )
    
    db.add(new_user)
    # The session flush commits changes to the database lifecycle transaction block
    await db.flush() 
    
    logger.info(f"Successfully generated new profile entity for user: {new_user.username}")
    return new_user


@router.post("/login", response_model=TokenResponse)
async def login_user(
    payload: UserLoginRequest, 
    db: AsyncSession = Depends(get_db_session)
):
    """
    HTTP POST Endpoint to verify credentials and issue a stateless JWT access token.
    """
    # 1. Lookup user by unique indexed username
    query = select(User).where(User.username == payload.username)
    result = await db.execute(query)
    user = result.scalar()

    # 2. Run constant-time validation checks
    if not user or not AuthService.verify_password(payload.password, user.password_hash):
        logger.warning(f"Authentication failure: Invalid check attempt for user target '{payload.username}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password validation credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(f"Authentication failure: Attempted entry into locked account '{payload.username}'")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This user account has been disabled or locked out by administrative control systems."
        )

    # 3. Generate the cryptographically signed JWT token payload
    token_claims = {
        "sub": str(user.id),
        "username": user.username
    }
    access_token = AuthService.create_access_token(data=token_claims)

    logger.info(f"Successful identity validation token release issued for account user ID: {user.id}")
    return TokenResponse(access_token=access_token)


# Helper utility extension for SQLAlchemy result parsing scalar safety compatibility
def scalar_off_preferred(self):
    return self.scalars().first()
setattr(type(select(User)), 'scalar_off_preferred', scalar_off_preferred)