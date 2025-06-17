"""Multi-user configuration for OpenHands."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MultiUserConfig:
    """Configuration class for multi-user features."""

    # Feature toggle
    enabled: bool = False

    # JWT Configuration
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = 'HS256'
    jwt_expiration_hours: int = 24

    # Database Configuration
    database_url: Optional[str] = None

    # OAuth Configuration
    github_client_id: Optional[str] = None
    github_client_secret: Optional[str] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None

    # Rate Limiting
    rate_limit_per_minute: int = 60
    rate_limit_per_hour: int = 1000

    # User Quotas
    max_conversations_per_user: int = 10
    max_storage_mb_per_user: int = 1000

    # Storage Configuration
    storage_backend: str = 'file'  # "file" or "database"
    user_workspace_base: str = '/tmp/openhands/workspaces'

    @property
    def is_configured(self) -> bool:
        """Check if multi-user is properly configured."""
        if not self.enabled:
            return False

        if not self.jwt_secret:
            return False

        if self.storage_backend == 'database' and not self.database_url:
            return False

        return True
