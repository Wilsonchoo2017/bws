"""Load Facebook credentials from .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class FacebookCredentials:
    """Facebook login credentials."""

    email: str
    password: str


def get_facebook_credentials() -> FacebookCredentials:
    """Load Facebook credentials from environment variables.

    Returns:
        FacebookCredentials with email and password

    Raises:
        ValueError: If credentials are not set
    """
    email = os.environ.get("FACEBOOK_EMAIL", "")
    password = os.environ.get("FACEBOOK_PASSWORD", "")
    if not email or not password:
        raise ValueError("FACEBOOK_EMAIL and FACEBOOK_PASSWORD must be set in .env")
    return FacebookCredentials(email=email, password=password)
