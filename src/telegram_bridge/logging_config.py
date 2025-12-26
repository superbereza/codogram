"""Structured logging configuration for telegram_bridge."""
import logging

def setup_logging():
    """Configure logging for telegram_bridge."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

# Module-level logger
logger = logging.getLogger("telegram_bridge")
