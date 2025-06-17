"""JWT-based user authentication implementation."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import HTTPException, Request, status
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session as SQLSession

from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.models import User, UserSession
from features.multiuser.storage.user_file_stores import (
    UserFileSecretsStore,
    UserFileSettingsStore,
)
from openhands.integrations.provider import PROVIDER_TOKEN_TYPE
from openhands.server.settings import Settings
from openhands.server.user_auth.user_auth import AuthType, UserAuth
from openhands.storage.data_models.user_secrets import UserSecrets
from openhands.storage.secrets.secrets_store import SecretsStore
from openhands.storage.settings.settings_store import SettingsStore


class JWTUserAuth(UserAuth):
    """JWT-based user authentication implementation."""

    def __init__(
        self, request: Request, config: MultiUserConfig, db_session: SQLSession
    ):
        self.request = request
        self.config = config
        self.db_session = db_session
        self._user: Optional[User] = None
        self._settings: Optional[Settings] = None
        self._token_payload: Optional[dict] = None

    async def get_user_id(self) -> str | None:
        """Get the unique identifier for the current user."""
        user = await self._get_current_user()
        return user.id if user else None

    async def get_user_email(self) -> str | None:
        """Get the email for the current user."""
        user = await self._get_current_user()
        return user.email if user else None

    async def get_access_token(self) -> SecretStr | None:
        """Get the access token for the current user."""
        token = self._extract_token()
        return SecretStr(token) if token else None

    async def get_provider_tokens(self) -> PROVIDER_TOKEN_TYPE | None:
        """Get the provider tokens for the current user."""
        # Load from user's secrets store
        secrets_store = await self.get_secrets_store()
        user_secrets = await secrets_store.load()

        if not user_secrets:
            return None

        provider_tokens = {}

        # GitHub token
        if hasattr(user_secrets, 'github_token') and user_secrets.github_token:
            provider_tokens['github'] = user_secrets.github_token

        # Add other provider tokens as needed

        return provider_tokens if provider_tokens else None

    async def get_user_settings_store(self) -> SettingsStore:
        """Get the settings store for the current user."""
        user_id = await self.get_user_id()
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='User not authenticated',
            )

        # For now, use file-based storage with user-specific paths
        # TODO: Add database-backed storage option
        return UserFileSettingsStore(user_id=user_id, config=self.config)

    async def get_secrets_store(self) -> SecretsStore:
        """Get secrets store for the current user."""
        user_id = await self.get_user_id()
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='User not authenticated',
            )

        # For now, use file-based storage with user-specific paths
        # TODO: Add database-backed storage option
        return UserFileSecretsStore(user_id=user_id, config=self.config)

    async def get_user_secrets(self) -> UserSecrets | None:
        """Get the user's secrets."""
        secrets_store = await self.get_secrets_store()
        return await secrets_store.load()

    def get_auth_type(self) -> AuthType | None:
        """Return the authentication type."""
        return AuthType.BEARER

    @classmethod
    async def get_instance(cls, request: Request) -> 'JWTUserAuth':
        """Get an instance of JWTUserAuth from the request."""
        # TODO: Get config and db_session from application context
        # For now, this is a placeholder - we'll need to set up proper dependency injection
        config = MultiUserConfig()  # This should come from app context
        db_session = None  # This should come from app context

        return cls(request, config, db_session)

    def _extract_token(self) -> Optional[str]:
        """Extract JWT token from request headers."""
        authorization = self.request.headers.get('Authorization')
        if not authorization:
            return None

        if not authorization.startswith('Bearer '):
            return None

        return authorization[7:]  # Remove 'Bearer ' prefix

    async def _get_current_user(self) -> Optional[User]:
        """Get the current authenticated user."""
        if self._user is not None:
            return self._user

        token = self._extract_token()
        if not token:
            return None

        try:
            # Decode JWT token
            payload = jwt.decode(
                token, self.config.jwt_secret, algorithms=[self.config.jwt_algorithm]
            )
            self._token_payload = payload

            # Get user from database
            user_id = payload.get('sub')
            if not user_id:
                return None

            # Check if session is still valid
            jti = payload.get('jti')
            if jti and self.db_session:
                session_stmt = select(UserSession).where(
                    UserSession.token_jti == jti,
                    not UserSession.is_revoked,
                    UserSession.expires_at > datetime.utcnow(),
                )
                session_result = self.db_session.execute(
                    session_stmt
                ).scalar_one_or_none()
                if not session_result:
                    return None

            # Get user from database
            if self.db_session:
                user_stmt = select(User).where(User.id == user_id, User.is_active)
                self._user = self.db_session.execute(user_stmt).scalar_one_or_none()

            return self._user

        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
        except Exception:
            return None

    def create_access_token(
        self, user: User, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create a new JWT access token for the user."""
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                hours=self.config.jwt_expiration_hours
            )

        # Generate unique token ID
        jti = str(uuid.uuid4())

        # Create token payload
        payload = {
            'sub': user.id,
            'email': user.email,
            'exp': expire,
            'iat': datetime.now(timezone.utc),
            'jti': jti,
        }

        # Create session record
        if self.db_session:
            session = UserSession(
                id=str(uuid.uuid4()),
                user_id=user.id,
                token_jti=jti,
                expires_at=expire,
                user_agent=self.request.headers.get('User-Agent'),
                ip_address=self._get_client_ip(),
            )
            self.db_session.add(session)
            self.db_session.commit()

        # Encode JWT
        token = jwt.encode(
            payload, self.config.jwt_secret, algorithm=self.config.jwt_algorithm
        )
        return token

    def _get_client_ip(self) -> Optional[str]:
        """Get the client IP address from the request."""
        # Check for forwarded headers first
        forwarded_for = self.request.headers.get('X-Forwarded-For')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()

        real_ip = self.request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        # Fallback to client host
        if hasattr(self.request, 'client') and self.request.client:
            return self.request.client.host

        return None

    async def revoke_token(self, token: str) -> bool:
        """Revoke a JWT token by marking the session as revoked."""
        try:
            payload = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm],
                options={'verify_exp': False},  # Allow expired tokens to be revoked
            )

            jti = payload.get('jti')
            if not jti or not self.db_session:
                return False

            # Mark session as revoked
            session_stmt = select(UserSession).where(UserSession.token_jti == jti)
            session = self.db_session.execute(session_stmt).scalar_one_or_none()

            if session:
                session.is_revoked = True
                self.db_session.commit()
                return True

            return False

        except jwt.InvalidTokenError:
            return False
