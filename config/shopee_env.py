"""Load Shopee credentials from .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class ShopeeCredentials:
    """Shopee login credentials."""

    username: str
    password: str


def get_shopee_credentials() -> ShopeeCredentials:
    """Load Shopee credentials from environment variables.

    Returns:
        ShopeeCredentials with username and password

    Raises:
        ValueError: If credentials are not set
    """
    username = os.environ.get("SHOPEE_USERNAME", "")
    password = os.environ.get("SHOPEE_PASSWORD", "")
    if not username or not password:
        raise ValueError("SHOPEE_USERNAME and SHOPEE_PASSWORD must be set in .env")
    return ShopeeCredentials(username=username, password=password)
