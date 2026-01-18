# tests/conftest.py
"""Pytest configuration and fixtures."""
import os

# Set mock environment variables BEFORE any imports that might trigger settings load
os.environ.setdefault("TELEGRAM_TOKEN", "test-token-12345")
os.environ.setdefault("ADMIN_IDS", "123456789")
os.environ.setdefault("BASE_DIR", "/tmp/test-codogram")
