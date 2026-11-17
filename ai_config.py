"""
NEXUS AI OS - AI Configuration & Security Module
Securely reads and validates AI provider, model, and API key configuration
from environment variables without exposing secrets to frontend or logs.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

# Load environment variables from .env if present (without overriding existing environment)
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH, override=False)

def reload_ai_config():
    """Reloads environment variables from .env file if it exists."""
    if ENV_PATH.exists():
        load_dotenv(dotenv_path=ENV_PATH, override=True)

def get_ai_provider() -> str:
    """Returns the configured AI provider name, or 'not_configured'."""
    provider = os.getenv("AI_PROVIDER", "").strip()
    if not provider or provider.lower() == "not_configured":
        return "not_configured"
    return provider

def get_ai_model() -> str | None:
    """Returns the configured AI model name, or None."""
    model = os.getenv("AI_MODEL", "").strip()
    return model if model else None

def get_ai_api_key() -> str:
    """
    Returns the raw AI API key for internal backend use only.
    SECURITY: NEVER log, print, or return this value to the frontend.
    """
    return os.getenv("AI_API_KEY", "").strip().strip("'\"")

def is_ai_configured() -> bool:
    """
    Checks if an AI provider and non-empty API key are properly configured.
    """
    api_key = get_ai_api_key()
    provider = get_ai_provider()
    return bool(api_key and provider != "not_configured")

def get_ai_status() -> dict:
    """
    Returns the AI configuration status payload for the frontend and API endpoints.
    SECURITY: Never includes the API key or any secrets.
    """
    configured = is_ai_configured()
    provider = get_ai_provider()
    model = get_ai_model()

    if configured:
        return {
            "configured": True,
            "provider": provider,
            "model": model,
            "message": "AI configuration is ready."
        }
    else:
        return {
            "configured": False,
            "provider": "not_configured",
            "model": None,
            "message": "AI provider is not configured yet."
        }
