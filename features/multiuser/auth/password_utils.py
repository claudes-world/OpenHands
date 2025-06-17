"""Password hashing and verification utilities."""

import bcrypt


def hash_password(password: str) -> str:
    """Hash a password using bcrypt with a cost factor of 12."""
    # Generate salt and hash password
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False


def is_strong_password(password: str) -> tuple[bool, list[str]]:
    """Check if password meets strength requirements.

    Returns:
        tuple: (is_valid, list_of_errors)
    """
    errors = []

    if len(password) < 8:
        errors.append('Password must be at least 8 characters long')

    if not any(c.isupper() for c in password):
        errors.append('Password must contain at least one uppercase letter')

    if not any(c.islower() for c in password):
        errors.append('Password must contain at least one lowercase letter')

    if not any(c.isdigit() for c in password):
        errors.append('Password must contain at least one digit')

    # Check for special characters
    special_chars = '!@#$%^&*()_+-=[]{}|;:,.<>?'
    if not any(c in special_chars for c in password):
        errors.append('Password must contain at least one special character')

    return len(errors) == 0, errors
