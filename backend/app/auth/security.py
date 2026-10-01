from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets


# Development admin account
ADMIN_USERNAME = "admin"

# This is a temporary development password.
# We will move this to environment variables/database later.
ADMIN_PASSWORD = "DroneStream@123"


# Store active login sessions in memory for now.
# PostgreSQL-based sessions will be added later.
admin_sessions = {}


def verify_admin_credentials(username: str, password: str) -> bool:
    """Verify the administrator's login credentials."""
    username_valid = hmac.compare_digest(username, ADMIN_USERNAME)
    password_valid = hmac.compare_digest(password, ADMIN_PASSWORD)

    return username_valid and password_valid


def create_admin_session() -> str:
    """Create a secure random admin session token."""
    session_token = secrets.token_urlsafe(48)

    admin_sessions[session_token] = {
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=8),
    }

    return session_token


def validate_admin_session(session_token: str) -> bool:
    """Check whether an admin session is valid."""
    session = admin_sessions.get(session_token)

    if not session:
        return False

    if datetime.now(timezone.utc) >= session["expires_at"]:
        admin_sessions.pop(session_token, None)
        return False

    return True


def delete_admin_session(session_token: str) -> None:
    """Remove an admin session."""
    admin_sessions.pop(session_token, None)