"""Quota management system for multi-user support."""

import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.models import ConversationMetadata, User


@dataclass
class UserQuota:
    """User quota information."""

    user_id: str
    conversations_used: int
    conversations_limit: int
    storage_used_mb: int
    storage_limit_mb: int

    @property
    def conversations_available(self) -> int:
        """Get available conversation quota."""
        return max(0, self.conversations_limit - self.conversations_used)

    @property
    def storage_available_mb(self) -> int:
        """Get available storage quota in MB."""
        return max(0, self.storage_limit_mb - self.storage_used_mb)

    @property
    def conversations_percentage_used(self) -> float:
        """Get percentage of conversation quota used."""
        if self.conversations_limit == 0:
            return 0.0
        return (self.conversations_used / self.conversations_limit) * 100

    @property
    def storage_percentage_used(self) -> float:
        """Get percentage of storage quota used."""
        if self.storage_limit_mb == 0:
            return 0.0
        return (self.storage_used_mb / self.storage_limit_mb) * 100

    @property
    def is_conversations_quota_exceeded(self) -> bool:
        """Check if conversation quota is exceeded."""
        return self.conversations_used >= self.conversations_limit

    @property
    def is_storage_quota_exceeded(self) -> bool:
        """Check if storage quota is exceeded."""
        return self.storage_used_mb >= self.storage_limit_mb


class QuotaManager:
    """Manages user quotas and usage tracking."""

    def __init__(self, config: MultiUserConfig, db_session: Session):
        self.config = config
        self.db_session = db_session

    async def get_user_quota(self, user_id: str) -> UserQuota:
        """Get current quota information for a user."""
        # Get user from database
        user = self.db_session.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

        if not user:
            raise ValueError(f'User {user_id} not found')

        # Count active conversations
        conversations_count = (
            self.db_session.execute(
                select(func.count(ConversationMetadata.conversation_id)).where(
                    ConversationMetadata.user_id == user_id
                )
            ).scalar()
            or 0
        )

        # Calculate storage usage
        storage_used_mb = await self._calculate_storage_usage(user_id)

        return UserQuota(
            user_id=user_id,
            conversations_used=conversations_count,
            conversations_limit=self.config.max_conversations_per_user,
            storage_used_mb=storage_used_mb,
            storage_limit_mb=self.config.max_storage_mb_per_user,
        )

    async def check_conversation_quota(self, user_id: str) -> bool:
        """Check if user can create a new conversation."""
        quota = await self.get_user_quota(user_id)
        return not quota.is_conversations_quota_exceeded

    async def check_storage_quota(self, user_id: str, additional_mb: int = 0) -> bool:
        """Check if user has enough storage quota."""
        quota = await self.get_user_quota(user_id)
        return (quota.storage_used_mb + additional_mb) <= quota.storage_limit_mb

    async def increment_conversation_count(self, user_id: str) -> bool:
        """Increment user's conversation count if quota allows."""
        if not await self.check_conversation_quota(user_id):
            return False

        # Update user's conversation count
        user = self.db_session.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

        if user:
            user.total_conversations += 1
            self.db_session.commit()

        return True

    async def decrement_conversation_count(self, user_id: str):
        """Decrement user's conversation count."""
        user = self.db_session.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

        if user and user.total_conversations > 0:
            user.total_conversations -= 1
            self.db_session.commit()

    async def update_storage_usage(self, user_id: str):
        """Update user's storage usage in the database."""
        storage_used_mb = await self._calculate_storage_usage(user_id)

        user = self.db_session.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

        if user:
            user.storage_used_mb = storage_used_mb
            self.db_session.commit()

    async def _calculate_storage_usage(self, user_id: str) -> int:
        """Calculate actual storage usage for a user in MB."""
        user_workspace_base = self.config.user_workspace_base
        user_workspace = os.path.join(user_workspace_base, user_id)

        if not os.path.exists(user_workspace):
            return 0

        total_size = 0
        try:
            for dirpath, dirnames, filenames in os.walk(user_workspace):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total_size += os.path.getsize(filepath)
        except (OSError, PermissionError):
            # If we can't access the directory, return 0
            return 0

        # Convert bytes to MB
        return int(total_size / (1024 * 1024))

    async def get_quota_usage_stats(self, user_id: str) -> dict[str, Any]:
        """Get detailed quota usage statistics for a user."""
        quota = await self.get_user_quota(user_id)

        return {
            'user_id': user_id,
            'conversations': {
                'used': quota.conversations_used,
                'limit': quota.conversations_limit,
                'available': quota.conversations_available,
                'percentage_used': quota.conversations_percentage_used,
                'exceeded': quota.is_conversations_quota_exceeded,
            },
            'storage': {
                'used_mb': quota.storage_used_mb,
                'limit_mb': quota.storage_limit_mb,
                'available_mb': quota.storage_available_mb,
                'percentage_used': quota.storage_percentage_used,
                'exceeded': quota.is_storage_quota_exceeded,
            },
            'status': {
                'can_create_conversation': not quota.is_conversations_quota_exceeded,
                'can_upload_files': not quota.is_storage_quota_exceeded,
                'quota_healthy': not (
                    quota.is_conversations_quota_exceeded
                    or quota.is_storage_quota_exceeded
                ),
            },
        }

    async def cleanup_user_data(
        self, user_id: str, dry_run: bool = True
    ) -> dict[str, Any]:
        """Clean up user data to free up quota space."""
        user_workspace = os.path.join(self.config.user_workspace_base, user_id)

        cleanup_stats = {
            'files_to_delete': [],
            'conversations_to_archive': [],
            'estimated_space_freed_mb': 0,
        }

        if not os.path.exists(user_workspace):
            return cleanup_stats

        # Find large files and old files that can be cleaned up
        try:
            for dirpath, dirnames, filenames in os.walk(user_workspace):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        file_size = os.path.getsize(filepath)
                        file_size_mb = file_size / (1024 * 1024)

                        # Files larger than 10MB or temporary files
                        if (
                            file_size_mb > 10
                            or filename.startswith('temp_')
                            or filename.endswith('.tmp')
                        ):
                            cleanup_stats['files_to_delete'].append(
                                {
                                    'path': filepath,
                                    'size_mb': file_size_mb,
                                    'reason': 'large_file'
                                    if file_size_mb > 10
                                    else 'temporary_file',
                                }
                            )
                            cleanup_stats['estimated_space_freed_mb'] += file_size_mb

                            # Actually delete if not dry run
                            if not dry_run:
                                try:
                                    os.remove(filepath)
                                except OSError:
                                    pass

        except (OSError, PermissionError):
            pass

        return cleanup_stats


class QuotaMiddleware:
    """FastAPI middleware for quota enforcement."""

    def __init__(self, config: MultiUserConfig):
        self.config = config

    async def __call__(self, request, call_next):
        """Process request with quota enforcement."""
        # Skip quota checking if not enabled
        if not self.config.enabled:
            return await call_next(request)

        # Extract user ID from request
        user_id = getattr(request.state, 'user_id', None)

        if not user_id:
            # No user ID - skip quota checking
            return await call_next(request)

        # Check if this is a conversation creation request
        if request.method == 'POST' and request.url.path.startswith(
            '/api/conversations'
        ):
            # TODO: Add database session to check quota
            # This would need proper dependency injection
            # For now, just proceed
            pass

        return await call_next(request)
