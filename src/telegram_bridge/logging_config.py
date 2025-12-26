"""Structured logging configuration for telegram_bridge."""
import logging
import os

def setup_logging():
    """Configure logging for telegram_bridge.

    Level controlled by LOG_LEVEL env var (default: DEBUG).
    Set LOG_LEVEL=INFO for less verbose output.
    """
    level_name = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set level for our logger
    logger = logging.getLogger("telegram_bridge")
    logger.setLevel(level)

    return logger

# Module-level logger
logger = logging.getLogger("telegram_bridge")
