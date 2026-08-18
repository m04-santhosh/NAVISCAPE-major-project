"""
NAVISCAPE Configuration
Centralized settings management using environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require_env(key: str, fallback: str = None) -> str:
    """Return env variable or raise if missing in production."""
    value = os.getenv(key, fallback)
    if value is None:
        raise ValueError(
            f"[NAVISCAPE] Required environment variable '{key}' is not set. "
            f"Add it to backend/.env before starting the server."
        )
    return value


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

    # JWT Authentication — SECRET_KEY MUST come from environment
    # No hardcoded fallback. Server will refuse to start if this is missing.
    SECRET_KEY: str = _require_env(
        "SECRET_KEY",
        # Allow a development default ONLY when DEBUG=True to ease local setup
        "naviscape-dev-only-secret-key-do-not-use-in-production" if os.getenv("DEBUG", "True").lower() == "true" else None,
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

    # CORS — configurable via comma-separated CORS_ORIGINS env var (e.g. "https://app.naviscape.com,https://naviscape.vercel.app")
    # Wildcard '*' is disallowed for production security.
    CORS_ORIGINS: list = (
        [origin.strip() for origin in os.getenv("CORS_ORIGINS").split(",") if origin.strip() and origin.strip() != "*"]
        if os.getenv("CORS_ORIGINS")
        else [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # ML Model Paths
    ML_MODELS_DIR: str = os.getenv("ML_MODELS_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml", "models"))
    ML_DATA_DIR: str = os.getenv("ML_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "ml", "data"))

    # External APIs
    TOMTOM_API_KEY: str = os.getenv("TOMTOM_API_KEY", "")

    # Map defaults (Bangalore, India)
    DEFAULT_LAT: float = 12.9716
    DEFAULT_LNG: float = 77.5946
    DEFAULT_ZOOM: int = 12

    # -------------------------------------------------------------------------
    # Email / SMTP (Gmail SMTP with App Password)
    # -------------------------------------------------------------------------
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")  # Gmail App Password
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", os.getenv("SMTP_USERNAME", ""))
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "NAVISCAPE")

    # -------------------------------------------------------------------------
    # OTP Configuration
    # -------------------------------------------------------------------------
    OTP_EXPIRE_MINUTES: int = int(os.getenv("OTP_EXPIRE_MINUTES", "5"))
    OTP_MAX_ATTEMPTS: int = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    OTP_RESEND_COOLDOWN_SECONDS: int = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60"))
    OTP_MAX_PER_EMAIL_PER_HOUR: int = int(os.getenv("OTP_MAX_PER_EMAIL_PER_HOUR", "10"))
    OTP_MAX_PER_IP_PER_HOUR: int = int(os.getenv("OTP_MAX_PER_IP_PER_HOUR", "30"))

    # Verification / Reset token TTL (seconds)
    VERIFICATION_TOKEN_EXPIRE_SECONDS: int = int(os.getenv("VERIFICATION_TOKEN_EXPIRE_SECONDS", "600"))  # 10 min


settings = Settings()
