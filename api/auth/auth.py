import json
from pathlib import Path

USERS_FILE = Path(__file__).parent / "users.json"


def get_users():
    with open(USERS_FILE, "r") as file:
        return json.load(file)


def authenticate_user(email: str, password: str):
    users = get_users()

    for user in users:
        if user["email"] == email and user["password"] == password:
            return user

    return None