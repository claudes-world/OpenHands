"""User-aware file storage implementations."""

import json
import os
from dataclasses import dataclass
from pathlib import Path

from features.multiuser.config.multi_user_config import MultiUserConfig
from openhands.core.config.openhands_config import OpenHandsConfig
from openhands.storage import get_file_store
from openhands.storage.conversation.file_conversation_store import FileConversationStore
from openhands.storage.data_models.conversation_metadata import ConversationMetadata
from openhands.storage.data_models.conversation_metadata_result_set import (
    ConversationMetadataResultSet,
)
from openhands.storage.data_models.settings import Settings
from openhands.storage.data_models.user_secrets import UserSecrets
from openhands.storage.secrets.secrets_store import SecretsStore
from openhands.storage.settings.settings_store import SettingsStore
from openhands.utils.async_utils import call_sync_from_async
from openhands.utils.search_utils import offset_to_page_id, page_id_to_offset


@dataclass
class UserFileConversationStore(FileConversationStore):
    """File-based conversation store with user isolation."""

    user_id: str

    def get_conversation_metadata_dir(self) -> str:
        """Get user-specific conversation metadata directory."""
        return f'users/{self.user_id}/conversations'

    def get_conversation_metadata_filename(self, conversation_id: str) -> str:
        """Get user-specific conversation metadata filename."""
        return f'users/{self.user_id}/conversations/{conversation_id}/metadata.json'

    async def validate_metadata(self, conversation_id: str, user_id: str) -> bool:
        """Validate that conversation belongs to the current user."""
        # Since we're already scoped to the user, just check if it exists
        return self.user_id == user_id and await self.exists(conversation_id)

    async def search(
        self,
        page_id: str | None = None,
        limit: int = 20,
    ) -> ConversationMetadataResultSet:
        """Search conversations for the specific user."""
        conversations: list[ConversationMetadata] = []
        metadata_dir = self.get_conversation_metadata_dir()

        try:
            conversation_paths = self.file_store.list(metadata_dir)
            conversation_ids = [
                path.split('/')[-2]  # Extract conversation_id from path
                for path in conversation_paths
                if path.endswith('/metadata.json')
            ]
        except FileNotFoundError:
            return ConversationMetadataResultSet([])

        num_conversations = len(conversation_ids)
        start = page_id_to_offset(page_id)
        end = min(limit + start, num_conversations)

        conversations = []
        for conversation_id in conversation_ids:
            try:
                metadata = await self.get_metadata(conversation_id)
                # Ensure user_id is set for validation
                if not metadata.user_id:
                    metadata.user_id = self.user_id
                conversations.append(metadata)
            except Exception:
                # Skip invalid conversations
                continue

        # Sort by creation time (newest first)
        conversations.sort(key=lambda c: c.created_at or '', reverse=True)
        conversations = conversations[start:end]

        next_page_id = offset_to_page_id(end, end < num_conversations)
        return ConversationMetadataResultSet(conversations, next_page_id)

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> 'UserFileConversationStore':
        """Get a user-specific conversation store instance."""
        if not user_id:
            raise ValueError('user_id is required for UserFileConversationStore')

        file_store = get_file_store(
            config.file_store,
            config.file_store_path,
            config.file_store_web_hook_url,
            config.file_store_web_hook_headers,
        )

        return cls(file_store=file_store, user_id=user_id)


@dataclass
class UserFileSettingsStore(SettingsStore):
    """File-based settings store with user isolation."""

    user_id: str
    config: MultiUserConfig

    def __post_init__(self):
        """Initialize the file store."""
        # Create user-specific file store
        user_base_path = os.path.join(self.config.user_workspace_base, self.user_id)
        Path(user_base_path).mkdir(parents=True, exist_ok=True)

        # For now, use local file store - can be extended to use configured store
        from openhands.storage.files.local_file_store import LocalFileStore

        self.file_store = LocalFileStore(base_path=user_base_path)
        self.path = 'settings.json'

    async def load(self) -> Settings | None:
        """Load user-specific settings."""
        try:
            json_str = await call_sync_from_async(self.file_store.read, self.path)
            kwargs = json.loads(json_str)
            settings = Settings(**kwargs)
            return settings
        except FileNotFoundError:
            return None

    async def store(self, settings: Settings) -> None:
        """Store user-specific settings."""
        json_str = settings.model_dump_json(context={'expose_secrets': True})
        await call_sync_from_async(self.file_store.write, self.path, json_str)

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> 'UserFileSettingsStore':
        """Get a user-specific settings store instance."""
        if not user_id:
            raise ValueError('user_id is required for UserFileSettingsStore')

        # Create multi-user config from OpenHandsConfig
        multi_user_config = MultiUserConfig(
            user_workspace_base=config.file_store_path or '/tmp/openhands/users'
        )

        return cls(user_id=user_id, config=multi_user_config)


@dataclass
class UserFileSecretsStore(SecretsStore):
    """File-based secrets store with user isolation and encryption."""

    user_id: str
    config: MultiUserConfig

    def __post_init__(self):
        """Initialize the file store."""
        # Create user-specific file store
        user_base_path = os.path.join(self.config.user_workspace_base, self.user_id)
        Path(user_base_path).mkdir(parents=True, exist_ok=True)

        # For now, use local file store - can be extended to use configured store
        from openhands.storage.files.local_file_store import LocalFileStore

        self.file_store = LocalFileStore(base_path=user_base_path)
        self.path = 'secrets.json'

    async def load(self) -> UserSecrets | None:
        """Load user-specific secrets."""
        try:
            json_str = await call_sync_from_async(self.file_store.read, self.path)
            kwargs = json.loads(json_str)
            secrets = UserSecrets(**kwargs)
            return secrets
        except FileNotFoundError:
            return None

    async def store(self, secrets: UserSecrets) -> None:
        """Store user-specific secrets."""
        # TODO: Add encryption for sensitive data
        json_str = secrets.model_dump_json()
        await call_sync_from_async(self.file_store.write, self.path, json_str)

    @classmethod
    async def get_instance(
        cls, config: OpenHandsConfig, user_id: str | None
    ) -> 'UserFileSecretsStore':
        """Get a user-specific secrets store instance."""
        if not user_id:
            raise ValueError('user_id is required for UserFileSecretsStore')

        # Create multi-user config from OpenHandsConfig
        multi_user_config = MultiUserConfig(
            user_workspace_base=config.file_store_path or '/tmp/openhands/users'
        )

        return cls(user_id=user_id, config=multi_user_config)
