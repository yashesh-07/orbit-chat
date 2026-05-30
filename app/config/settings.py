import os
from pydantic_settings import BaseSettings, SettingsConfigDict 
from pydantic import Field 

class AppSettings(BaseSettings):
    """
    Enterprise Configuration Matrix.
    Injects and validates environment variables from the root .env file.
    """
    # System Metadata
    PROJECT_NAME: str = Field(default="OrbitChat Enterprise")
    API_ENV: str = Field(default="development")
    
    # Cryptographic Boundaries
    SECRET_KEY: str = Field(..., description="Cryptographic signing key for authorization signatures")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=1440)
    
    # Explicit Port Interception
    POSTGRES_PORT: int = Field(default=5432)
    REDIS_PORT: int = Field(default=6379)
    FASTAPI_PORT: int = Field(default=8000)
    
    # Engine Structural Connection Strings
    DATABASE_URL: str = Field(..., description="PostgreSQL async/sync database system link")
    REDIS_URL: str = Field(..., description="Redis hot cache and Pub/Sub cluster connection wire")

    # Configuration for Pydantic V2 to look up external environment mapping
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore" # Safely bypass extra environment variables on the local OS
    )

# Instantiate a singleton to be shared across all system modules
settings = AppSettings()