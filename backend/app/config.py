"""
NAVISCAPE Configuration
Centralized settings management using environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""
    
    # Application
    APP_NAME: str = "NAVISCAPE"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    
    # Database (resolve path relative to backend root)
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(os.path.dirname(os.path.dirname(__file__)), 'naviscape.db')}"
    )

    
    # JWT Authentication
    SECRET_KEY: str = os.getenv("SECRET_KEY", "naviscape-super-secret-key-change-in-production-2024")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
    
    # CORS
    CORS_ORIGINS: list = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]
    
    # ML Model Paths
    ML_MODELS_DIR: str = os.getenv("ML_MODELS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml", "models"))
    ML_DATA_DIR: str = os.getenv("ML_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml", "data"))
    
    # External APIs
    TOMTOM_API_KEY: str = os.getenv("TOMTOM_API_KEY", "")

    # Map defaults (Bangalore, India)
    DEFAULT_LAT: float = 12.9716
    DEFAULT_LNG: float = 77.5946
    DEFAULT_ZOOM: int = 12


settings = Settings()
