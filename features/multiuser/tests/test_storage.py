"""Tests for storage functionality."""

import os
import tempfile
import uuid
from unittest.mock import Mock

import pytest

from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.storage.user_file_stores import (
    UserFileConversationStore,
    UserFileSecretsStore,
    UserFileSettingsStore,
)
from openhands.storage.data_models.settings import Settings
from openhands.storage.data_models.user_secrets import UserSecrets


class TestUserFileConversationStore:
    """Test user-specific file conversation store."""

    @pytest.fixture
    def test_user_id(self):
        """Create test user ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def mock_file_store(self):
        """Create mock file store."""
        return Mock()

    @pytest.fixture
    def conversation_store(self, mock_file_store, test_user_id):
        """Create conversation store instance."""
        return UserFileConversationStore(
            file_store=mock_file_store, user_id=test_user_id
        )

    def test_get_conversation_metadata_dir(self, conversation_store, test_user_id):
        """Test conversation metadata directory path."""
        expected = f'users/{test_user_id}/conversations'
        assert conversation_store.get_conversation_metadata_dir() == expected

    def test_get_conversation_metadata_filename(self, conversation_store, test_user_id):
        """Test conversation metadata filename path."""
        conversation_id = 'test_conversation_123'
        expected = f'users/{test_user_id}/conversations/{conversation_id}/metadata.json'
        assert (
            conversation_store.get_conversation_metadata_filename(conversation_id)
            == expected
        )

    def test_validate_metadata_success(self, conversation_store, test_user_id):
        """Test successful metadata validation."""
        conversation_id = 'test_conversation_123'

        # Mock exists method to return True
        conversation_store.exists = Mock(return_value=True)

        result = conversation_store.validate_metadata(conversation_id, test_user_id)
        assert result is True

    def test_validate_metadata_wrong_user(self, conversation_store, test_user_id):
        """Test metadata validation with wrong user."""
        conversation_id = 'test_conversation_123'
        wrong_user_id = str(uuid.uuid4())

        result = conversation_store.validate_metadata(conversation_id, wrong_user_id)
        assert result is False


class TestUserFileSettingsStore:
    """Test user-specific file settings store."""

    @pytest.fixture
    def test_user_id(self):
        """Create test user ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield MultiUserConfig(enabled=True, user_workspace_base=temp_dir)

    @pytest.fixture
    def settings_store(self, temp_config, test_user_id):
        """Create settings store instance."""
        return UserFileSettingsStore(user_id=test_user_id, config=temp_config)

    def test_user_directory_creation(self, settings_store, temp_config, test_user_id):
        """Test that user directory is created."""
        expected_path = os.path.join(temp_config.user_workspace_base, test_user_id)
        assert os.path.exists(expected_path)
        assert os.path.isdir(expected_path)

    @pytest.mark.asyncio
    async def test_store_and_load_settings(self, settings_store):
        """Test storing and loading settings."""
        # Create test settings
        test_settings = Settings(
            llm_model='gpt-4',
            agent='CodeActAgent',
            language='en',
            confirmation_mode=False,
        )

        # Store settings
        await settings_store.store(test_settings)

        # Load settings
        loaded_settings = await settings_store.load()

        assert loaded_settings is not None
        assert loaded_settings.llm_model == test_settings.llm_model
        assert loaded_settings.agent == test_settings.agent
        assert loaded_settings.language == test_settings.language
        assert loaded_settings.confirmation_mode == test_settings.confirmation_mode

    @pytest.mark.asyncio
    async def test_load_nonexistent_settings(self, settings_store):
        """Test loading settings that don't exist."""
        loaded_settings = await settings_store.load()
        assert loaded_settings is None


class TestUserFileSecretsStore:
    """Test user-specific file secrets store."""

    @pytest.fixture
    def test_user_id(self):
        """Create test user ID."""
        return str(uuid.uuid4())

    @pytest.fixture
    def temp_config(self):
        """Create temporary configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield MultiUserConfig(enabled=True, user_workspace_base=temp_dir)

    @pytest.fixture
    def secrets_store(self, temp_config, test_user_id):
        """Create secrets store instance."""
        return UserFileSecretsStore(user_id=test_user_id, config=temp_config)

    @pytest.mark.asyncio
    async def test_store_and_load_secrets(self, secrets_store):
        """Test storing and loading secrets."""
        # Create test secrets
        test_secrets = UserSecrets(
            openai_api_key='test_openai_key',
            github_token='test_github_token',
        )

        # Store secrets
        await secrets_store.store(test_secrets)

        # Load secrets
        loaded_secrets = await secrets_store.load()

        assert loaded_secrets is not None
        assert loaded_secrets.openai_api_key == test_secrets.openai_api_key
        assert loaded_secrets.github_token == test_secrets.github_token

    @pytest.mark.asyncio
    async def test_load_nonexistent_secrets(self, secrets_store):
        """Test loading secrets that don't exist."""
        loaded_secrets = await secrets_store.load()
        assert loaded_secrets is None

    def test_user_directory_isolation(self, temp_config):
        """Test that different users have isolated directories."""
        user_id_1 = str(uuid.uuid4())
        user_id_2 = str(uuid.uuid4())

        UserFileSecretsStore(user_id=user_id_1, config=temp_config)
        UserFileSecretsStore(user_id=user_id_2, config=temp_config)

        # Check that different base paths are used
        path_1 = os.path.join(temp_config.user_workspace_base, user_id_1)
        path_2 = os.path.join(temp_config.user_workspace_base, user_id_2)

        assert path_1 != path_2
        assert os.path.exists(path_1)
        assert os.path.exists(path_2)


if __name__ == '__main__':
    pytest.main([__file__])
