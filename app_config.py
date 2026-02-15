import os
from datetime import timedelta


class Config:
    """Base configuration"""

    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-key"

    # Session configuration - persistent sessions
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(days=365)  # Sessions last 1 year
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent JavaScript access to session cookie
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection

    # Database configuration - auto-detect environment
    # Check if running on Heroku (Heroku sets DYNO environment variable)
    is_heroku = os.environ.get("DYNO") is not None

    if is_heroku:
        # Running on Heroku: Use HEROKU_DATABASE_CONN
        database_url = os.environ.get("HEROKU_DATABASE_CONN")
        if database_url:
            # Fix Heroku postgres:// URL to postgresql://
            if database_url.startswith("postgres://"):
                database_url = database_url.replace("postgres://", "postgresql://", 1)
            SQLALCHEMY_DATABASE_URI = database_url
        else:
            # Fallback if HEROKU_DATABASE_CONN not set
            SQLALCHEMY_DATABASE_URI = "sqlite:///autocart.db"
    else:
        # Running locally: Use LOCAL_DATABASE_CONN or default to SQLite
        local_db = os.environ.get("LOCAL_DATABASE_CONN")
        if local_db:
            SQLALCHEMY_DATABASE_URI = local_db
        else:
            # Default: SQLite
            SQLALCHEMY_DATABASE_URI = "sqlite:///autocart.db"

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Kroger API configuration
    CLIENT_ID = os.environ.get("CLIENT_ID")
    CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
    OAUTH2_BASE_URL = os.environ.get("OAUTH2_BASE_URL")

    # Auto-detect redirect URL based on environment
    if is_heroku:
        # Production: Use Heroku redirect URL
        REDIRECT_URL = os.environ.get("HEROKU_REDIRECT_URL") or os.environ.get(
            "REDIRECT_URL"
        )
    else:
        # Local development: Use local redirect URL
        REDIRECT_URL = (
            os.environ.get("LOCAL_REDIRECT_URL")
            or os.environ.get("REDIRECT_URL")
            or "http://localhost:5000/callback"
        )

    # Mail configuration
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or 587)
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "true").lower() in ["true", "on", "1"]
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER")


class DevelopmentConfig(Config):
    """Development configuration"""

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""

    DEBUG = False
    SESSION_COOKIE_SECURE = True  # Enable secure cookies in production (HTTPS only)


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
