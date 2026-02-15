"""Sample Python file for testing."""

import os
import json
from pathlib import Path
from typing import Optional


def helper_function(x: int) -> int:
    """A simple helper."""
    return x * 2


class UserService:
    """Manages user operations."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.users: list[dict] = []

    def get_user(self, user_id: str) -> Optional[dict]:
        """Get a user by ID."""
        for user in self.users:
            if user.get("id") == user_id:
                return user
        return None

    def create_user(self, name: str, email: str) -> dict:
        """Create a new user."""
        user = {"id": str(len(self.users)), "name": name, "email": email}
        self.users.append(user)
        return user


async def fetch_data(url: str) -> dict:
    """Fetch data from URL."""
    return {"url": url, "data": "sample"}
