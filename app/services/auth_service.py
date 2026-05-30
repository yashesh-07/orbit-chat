import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from passlib.context import CryptContext
import jwt
from fastapi import HTTPException, status
from app.config.settings import settings

# Setup isolated security logger
logger = logging.getLogger("orbitchat.security")

# 1. Initialize the Cryptographic Password Context
# We use bcrypt with a default work factor (rounds) of 12 for industrial hardness
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """
    Enterprise Identity & Security Subsystem.
    Manages one-way password hashing and stateless JWT lifecycle operations.
    """

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Generates a secure, salted one-way hash of a plaintext password.
        """
        return pwd_context.hash(password)

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verifies a plaintext password against a secured database hash.
        Prevents timing-attack vulnerabilities via constant-time comparison.
        """
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """
        Generates a cryptographically signed asymmetric HS256 JSON Web Token.
        """
        to_encode = data.copy()
        
        # Calculate strict expiration boundary
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        # Inject structural JWT claims
        to_encode.update({
            "exp": expire,
            "iat": datetime.utcnow(),
            "iss": "orbitchat-auth-core"
        })
        
        try:
            encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
            return encoded_jwt
        except Exception as error:
            logger.error(f"Critical token encoding failure: {str(error)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Security subsystem failed to clear token generation signature."
            )

    @staticmethod
    def verify_access_token(token: str) -> Dict[str, Any]:
        """
        Decodes and cryptographically verifies an incoming JWT signature.
        Fails fast if the token has been tampered with or is expired.
        """
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], issuer="orbitchat-auth-core")
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Stateless validation rejected: Token signature has expired.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Provided access token has expired. Request re-authentication.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as error:
            logger.warning(f"Stateless validation rejected: Tampered or malformed signature detected: {str(error)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials or signature is broken.",
                headers={"WWW-Authenticate": "Bearer"},
            )