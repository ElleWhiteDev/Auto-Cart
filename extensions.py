"""
Flask extensions initialization.

This module centralizes all Flask extension instances to avoid circular imports
and make dependency injection easier.
"""

from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO
from flask_talisman import Talisman
from flask_migrate import Migrate

# Initialize extensions
bcrypt = Bcrypt()
db = SQLAlchemy()
mail = Mail()
migrate = Migrate()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

# Caching configuration
cache = Cache(config={
    'CACHE_TYPE': 'simple',  # Use 'redis' in production
    'CACHE_DEFAULT_TIMEOUT': 300
})

# Rate limiting configuration
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",  # Use redis:// in production
)

# Security headers configuration
talisman = Talisman()


def init_extensions(app):
    """
    Initialize all Flask extensions with the app instance.
    
    Args:
        app: Flask application instance
    """
    bcrypt.init_app(app)
    db.init_app(app)
    mail.init_app(app)
    migrate.init_app(app, db)
    cache.init_app(app)
    limiter.init_app(app)
    socketio.init_app(app)
    
    # Only enable Talisman in production
    if not app.config.get('DEBUG', False):
        talisman.init_app(
            app,
            content_security_policy={
                'default-src': "'self'",
                'script-src': [
                    "'self'",
                    "'unsafe-inline'",  # Required for inline scripts
                    "cdn.jsdelivr.net",
                    "cdnjs.cloudflare.com"
                ],
                'style-src': [
                    "'self'",
                    "'unsafe-inline'",  # Required for inline styles
                    "cdn.jsdelivr.net",
                    "cdnjs.cloudflare.com"
                ],
                'img-src': ["'self'", "data:", "https:"],
                'font-src': ["'self'", "cdn.jsdelivr.net", "cdnjs.cloudflare.com"],
            },
            force_https=True,
            strict_transport_security=True,
            strict_transport_security_max_age=31536000,
        )

