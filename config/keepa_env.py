"""Load Keepa credentials from .env file."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


@dataclass(frozen=True)
class KeepaCredentials:
    """Keepa login credentials."""

    username: str
    password: str


def get_keepa_credentials() -> KeepaCredentials:
    """Load Keepa credentials from environment variables.

    Returns:
        KeepaCredentials with username and password

    Raises:
        ValueError: If credentials are not set
    """
    username = os.environ.get("KEEPA_USERNAME", "")
    password = os.environ.get("KEEPA_PASSWORD", "")
    if not username or not password:
        raise ValueError("KEEPA_USERNAME and KEEPA_PASSWORD must be set in .env")
    return KeepaCredentials(username=username, password=password)
