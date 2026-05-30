from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class UserRegisterRequest(BaseModel):
    """
    Inbound validation gate for account registration.
    Enforces strict string limitations and proper formatting on boot.
    """
    username: str = Field(
        ..., 
        min_length=3, 
        max_length=50, 
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Alphanumeric username with optional underscores or hyphens"
    )
    email: EmailStr = Field(..., description="RFC-compliant validated email address string")
    password: str = Field(..., min_length=8, max_length=128, description="Plaintext password before secure hashing")

    model_config = ConfigDict(str_strip_whitespace=True)


class UserLoginRequest(BaseModel):
    """
    Inbound validation gate for account login authentication.
    """
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


class UserResponse(BaseModel):
    """
    Outbound data filter.
    Guarantees sensitive data like password hashes can NEVER be leaked over public network endpoints.
    """
    id: int
    username: str
    email: str
    is_active: bool
    created_at: datetime

    # Tells Pydantic v2 to automatically extract data out of arbitrary ORM models (SQLAlchemy objects)
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """
    Outbound wrapper containing a successful user identity security pass.
    """
    access_token: str = Field(..., description="Signed JSON Web Token string")
    token_type: str = Field(default="bearer", description="Token authentication scheme")