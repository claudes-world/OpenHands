"""Database-backed storage implementations for multi-user support."""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, select
from sqlalchemy.orm import Session

from features.multiuser.db.models import (
    ConversationMetadata as DBConversationMetadata,
)
from features.multiuser.db.models import (
    UserSecret,
    UserSetting,
)
from openhands.core.config.openhands_config import OpenHandsConfig
from openhands.storage.conversation.conversation_store import ConversationStore
from openhands.storage.data_models.conversation_metadata import ConversationMetadata
from openhands.storage.data_models.conversation_metadata_result_set import (
    ConversationMetadataResultSet,
)
from openhands.storage.data_models.settings import Settings
from openhands.storage.data_models.user_secrets import UserSecrets
from openhands.storage.secrets.secrets_store import SecretsStore
from openhands.storage.settings.settings_store import SettingsStore
from openhands.utils.search_utils import offset_to_page_id, page_id_to_offset


@dataclass
class DatabaseConversationStore(ConversationStore):
    """Database-backed conversation store with user isolation."""

    db_session: Session
    user_id: str

    async def save_metadata(self, metadata: ConversationMetadata) -> None:
        """Store conversation metadata in database."""
        # Ensure user_id is set
        metadata.user_id = self.user_id

        # Check if conversation already exists
        existing = self.db_session.execute(
            select(DBConversationMetadata).where(
                DBConversationMetadata.conversation_id == metadata.conversation_id
            )
        ).scalar_one_or_none()

        if existing:
            # Update existing conversation
            existing.title = metadata.title
            existing.last_updated_at = metadata.last_updated_at or datetime.utcnow()
            existing.accumulated_cost = metadata.accumulated_cost
            existing.prompt_tokens = metadata.prompt_tokens
            existing.completion_tokens = metadata.completion_tokens
            existing.total_tokens = metadata.total_tokens
            existing.status = getattr(metadata, 'status', None)
        else:
            # Create new conversation
            db_metadata = DBConversationMetadata(
                conversation_id=metadata.conversation_id,
                user_id=self.user_id,
                title=metadata.title,
                created_at=metadata.created_at or datetime.utcnow(),
                last_updated_at=metadata.last_updated_at or datetime.utcnow(),
                accumulated_cost=metadata.accumulated_cost,
                prompt_tokens=metadata.prompt_tokens,
                completion_tokens=metadata.completion_tokens,
                total_tokens=metadata.total_tokens,
                status=getattr(metadata, 'status', None),
            )
            self.db_session.add(db_metadata)

        self.db_session.commit()

    async def get_metadata(self, conversation_id: str) -> ConversationMetadata:
        """Load conversation metadata from database."""
        db_metadata = self.db_session.execute(
            select(DBConversationMetadata).where(
                and_(
                    DBConversationMetadata.conversation_id == conversation_id,
                    DBConversationMetadata.user_id == self.user_id,
                )
            )
        ).scalar_one_or_none()

        if not db_metadata:
            raise FileNotFoundError(f'Conversation {conversation_id} not found')

        return ConversationMetadata(
            conversation_id=db_metadata.conversation_id,
            title=db_metadata.title,
            created_at=db_metadata.created_at,
            last_updated_at=db_metadata.last_updated_at,
            accumulated_cost=db_metadata.accumulated_cost,
            prompt_tokens=db_metadata.prompt_tokens,
            completion_tokens=db_metadata.completion_tokens,
            total_tokens=db_metadata.total_tokens,
            user_id=db_metadata.user_id,
        )

    async def delete_metadata(self, conversation_id: str) -> None:
        """Delete conversation metadata from database."""
        result = self.db_session.execute(
            delete(DBConversationMetadata).where(
                and_(
                    DBConversationMetadata.conversation_id == conversation_id,
                    DBConversationMetadata.user_id == self.user_id,
                )
            )
        )

        if result.rowcount == 0:
            raise FileNotFoundError(f'Conversation {conversation_id} not found')

        self.db_session.commit()

    async def exists(self, conversation_id: str) -> bool:
        """Check if conversation exists for the user."""
        result = self.db_session.execute(
            select(DBConversationMetadata.conversation_id).where(
                and_(
                    DBConversationMetadata.conversation_id == conversation_id,
                    DBConversationMetadata.user_id == self.user_id,
                )
            )
        ).scalar_one_or_none()

        return result is not None

    async def search(
        self,
        page_id: str | None = None,
        limit: int = 20,
    ) -> ConversationMetadataResultSet:
        """Search conversations for the specific user."""
        # Get total count
        total_count = (
            self.db_session.execute(
                select(DBConversationMetadata).where(
                    DBConversationMetadata.user_id == self.user_id
                )
            )
            .scalars()
            .all()
        )
        total_count = len(total_count)

        # Calculate offset
        start = page_id_to_offset(page_id)
        end = min(limit + start, total_count)

        # Get conversations with pagination
        db_conversations = (
            self.db_session.execute(
                select(DBConversationMetadata)
                .where(DBConversationMetadata.user_id == self.user_id)
                .order_by(DBConversationMetadata.created_at.desc())
                .offset(start)
                .limit(limit)
            )
            .scalars()
            .all()
        )

        # Convert to ConversationMetadata objects
        conversations = []
        for db_conv in db_conversations:
            conversations.append(
                ConversationMetadata(
                    conversation_id=db_conv.conversation_id,
                    title=db_conv.title,
                    created_at=db_conv.created_at,
                    last_updated_at=db_conv.last_updated_at,
                    accumulated_cost=db_conv.accumulated_cost,
                    prompt_tokens=db_conv.prompt_tokens,
                    completion_tokens=db_conv.completion_tokens,
                    total_tokens=db_conv.total_tokens,
                    user_id=db_conv.user_id,
                )
            )

        next_page_id = offset_to_page_id(end, end < total_count)
        return ConversationMetadataResultSet(conversations, next_page_id)

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> 'DatabaseConversationStore':
        """Get a user-specific conversation store instance."""
        if not user_id:
            raise ValueError('user_id is required for DatabaseConversationStore')

        # TODO: Get database session from dependency injection
        # This is a placeholder implementation
        raise NotImplementedError('Database session dependency not configured')


@dataclass
class DatabaseSettingsStore(SettingsStore):
    """Database-backed settings store with user isolation."""

    db_session: Session
    user_id: str

    async def load(self) -> Settings | None:
        """Load user-specific settings from database."""
        # Get all settings for the user
        user_settings = (
            self.db_session.execute(
                select(UserSetting).where(UserSetting.user_id == self.user_id)
            )
            .scalars()
            .all()
        )

        if not user_settings:
            return None

        # Convert to settings dictionary
        settings_dict = {}
        for setting in user_settings:
            try:
                # Try to parse as JSON first
                value = json.loads(setting.value) if setting.value else None
            except (json.JSONDecodeError, TypeError):
                # Use as string if not valid JSON
                value = setting.value

            settings_dict[setting.key] = value

        try:
            return Settings(**settings_dict)
        except Exception:
            return None

    async def store(self, settings: Settings) -> None:
        """Store user-specific settings in database."""
        settings_dict = settings.model_dump(context={'expose_secrets': True})

        # Delete existing settings for the user
        self.db_session.execute(
            delete(UserSetting).where(UserSetting.user_id == self.user_id)
        )

        # Insert new settings
        for key, value in settings_dict.items():
            # Convert value to JSON string
            value_str = json.dumps(value) if value is not None else None

            user_setting = UserSetting(
                id=str(uuid.uuid4()),
                user_id=self.user_id,
                key=key,
                value=value_str,
            )
            self.db_session.add(user_setting)

        self.db_session.commit()

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> 'DatabaseSettingsStore':
        """Get a user-specific settings store instance."""
        if not user_id:
            raise ValueError('user_id is required for DatabaseSettingsStore')

        # TODO: Get database session from dependency injection
        # This is a placeholder implementation
        raise NotImplementedError('Database session dependency not configured')


@dataclass
class DatabaseSecretsStore(SecretsStore):
    """Database-backed secrets store with user isolation and encryption."""

    db_session: Session
    user_id: str

    async def load(self) -> UserSecrets | None:
        """Load user-specific secrets from database."""
        # Get all secrets for the user
        user_secrets = (
            self.db_session.execute(
                select(UserSecret).where(UserSecret.user_id == self.user_id)
            )
            .scalars()
            .all()
        )

        if not user_secrets:
            return None

        # Convert to secrets dictionary
        secrets_dict = {}
        for secret in user_secrets:
            # TODO: Implement decryption for encrypted_value
            # For now, assume the value is stored as-is
            try:
                value = (
                    json.loads(secret.encrypted_value)
                    if secret.encrypted_value
                    else None
                )
            except (json.JSONDecodeError, TypeError):
                value = secret.encrypted_value

            secrets_dict[secret.key] = value

        try:
            return UserSecrets(**secrets_dict)
        except Exception:
            return None

    async def store(self, secrets: UserSecrets) -> None:
        """Store user-specific secrets in database with encryption."""
        secrets_dict = secrets.model_dump()

        # Delete existing secrets for the user
        self.db_session.execute(
            delete(UserSecret).where(UserSecret.user_id == self.user_id)
        )

        # Insert new secrets
        for key, value in secrets_dict.items():
            # TODO: Implement encryption for sensitive values
            # For now, store as JSON string
            encrypted_value = json.dumps(value) if value is not None else None

            user_secret = UserSecret(
                id=str(uuid.uuid4()),
                user_id=self.user_id,
                key=key,
                encrypted_value=encrypted_value,
            )
            self.db_session.add(user_secret)

        self.db_session.commit()

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> 'DatabaseSecretsStore':
        """Get a user-specific secrets store instance."""
        if not user_id:
            raise ValueError('user_id is required for DatabaseSecretsStore')

        # TODO: Get database session from dependency injection
        # This is a placeholder implementation
        raise NotImplementedError('Database session dependency not configured')
