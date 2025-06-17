"""Tests for authentication functionality."""

import uuid
from datetime import datetime
from unittest.mock import Mock

import pytest

from features.multiuser.auth.jwt_user_auth import JWTUserAuth
from features.multiuser.auth.password_utils import (
    hash_password,
    is_strong_password,
    verify_password,
)
from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.models import User


class TestPasswordUtils:
    """Test password utility functions."""

    def test_hash_password(self):
        """Test password hashing."""
        password = 'test_password_123'
        hashed = hash_password(password)

        assert hashed != password
        assert len(hashed) > 20  # bcrypt hashes are long
        assert hashed.startswith('$2b$')  # bcrypt identifier

    def test_verify_password_success(self):
        """Test successful password verification."""
        password = 'test_password_123'
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_failure(self):
        """Test failed password verification."""
        password = 'test_password_123'
        wrong_password = 'wrong_password'
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_invalid_hash(self):
        """Test password verification with invalid hash."""
        password = 'test_password_123'
        invalid_hash = 'invalid_hash'

        assert verify_password(password, invalid_hash) is False

    def test_is_strong_password_valid(self):
        """Test strong password validation - valid password."""
        password = 'MyStr0ng!P@ssw0rd'
        is_valid, errors = is_strong_password(password)

        assert is_valid is True
        assert len(errors) == 0

    def test_is_strong_password_too_short(self):
        """Test strong password validation - too short."""
        password = 'Short1!'
        is_valid, errors = is_strong_password(password)

        assert is_valid is False
        assert 'at least 8 characters' in errors[0]

    def test_is_strong_password_missing_requirements(self):
        """Test strong password validation - missing requirements."""
        password = 'nouppercase'
        is_valid, errors = is_strong_password(password)

        assert is_valid is False
        assert any('uppercase' in error for error in errors)
        assert any('digit' in error for error in errors)
        assert any('special character' in error for error in errors)


class TestJWTUserAuth:
    """Test JWT authentication functionality."""

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return MultiUserConfig(
            enabled=True,
            jwt_secret='test_secret_key_for_testing_purposes_only',
            jwt_algorithm='HS256',
            jwt_expiration_hours=24,
        )

    @pytest.fixture
    def mock_request(self):
        """Create mock request."""
        request = Mock()
        request.headers = {}
        request.client = Mock()
        request.client.host = '127.0.0.1'
        return request

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        return Mock()

    @pytest.fixture
    def test_user(self):
        """Create test user."""
        return User(
            id=str(uuid.uuid4()),
            email='test@example.com',
            full_name='Test User',
            is_active=True,
            created_at=datetime.utcnow(),
        )

    def test_create_access_token(
        self, config, mock_request, mock_db_session, test_user
    ):
        """Test JWT token creation."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        token = auth.create_access_token(test_user)

        assert isinstance(token, str)
        assert len(token) > 20  # JWT tokens are long

    def test_extract_token_bearer(self, config, mock_request, mock_db_session):
        """Test token extraction from Bearer header."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        # Test with Bearer token
        mock_request.headers = {'Authorization': 'Bearer test_token_123'}
        token = auth._extract_token()

        assert token == 'test_token_123'

    def test_extract_token_no_header(self, config, mock_request, mock_db_session):
        """Test token extraction with no Authorization header."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        # Test with no Authorization header
        mock_request.headers = {}
        token = auth._extract_token()

        assert token is None

    def test_extract_token_wrong_format(self, config, mock_request, mock_db_session):
        """Test token extraction with wrong header format."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        # Test with wrong format
        mock_request.headers = {'Authorization': 'Basic dGVzdDp0ZXN0'}
        token = auth._extract_token()

        assert token is None

    def test_get_client_ip_forwarded(self, config, mock_request, mock_db_session):
        """Test client IP extraction from X-Forwarded-For."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        mock_request.headers = {'X-Forwarded-For': '192.168.1.1, 10.0.0.1'}
        ip = auth._get_client_ip()

        assert ip == '192.168.1.1'

    def test_get_client_ip_real_ip(self, config, mock_request, mock_db_session):
        """Test client IP extraction from X-Real-IP."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        mock_request.headers = {'X-Real-IP': '192.168.1.1'}
        ip = auth._get_client_ip()

        assert ip == '192.168.1.1'

    def test_get_client_ip_fallback(self, config, mock_request, mock_db_session):
        """Test client IP extraction fallback to client.host."""
        auth = JWTUserAuth(mock_request, config, mock_db_session)

        mock_request.headers = {}
        mock_request.client.host = '127.0.0.1'
        ip = auth._get_client_ip()

        assert ip == '127.0.0.1'


if __name__ == '__main__':
    pytest.main([__file__])
