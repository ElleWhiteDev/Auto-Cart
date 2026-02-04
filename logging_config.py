"""Logging configuration for the application."""

import logging
import sys
from typing import Optional


def setup_logging(app_name: str = "auto_cart", level: Optional[str] = None) -> logging.Logger:
    """
    Configure and return a logger for the application.
    
    Args:
        app_name: Name of the application/logger
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               If None, uses INFO for production, DEBUG for development
    
    Returns:
        Configured logger instance
    """
    # Determine log level
    if level is None:
        import os
        env = os.environ.get('FLASK_ENV', 'development')
        level = 'DEBUG' if env == 'development' else 'INFO'
    
    # Create logger
    logger = logging.getLogger(app_name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create console handler with formatting
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    return logger


# Create default logger instance
logger = setup_logging()

