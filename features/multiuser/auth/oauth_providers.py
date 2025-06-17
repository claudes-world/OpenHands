"""OAuth provider integrations for multi-user authentication."""

import uuid
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.models import User


class GitHubOAuthProvider:
    """GitHub OAuth authentication provider."""

    def __init__(self, config: MultiUserConfig):
        self.config = config
        self.client_id = config.github_client_id
        self.client_secret = config.github_client_secret

        if not self.client_id or not self.client_secret:
            raise ValueError('GitHub OAuth credentials not configured')

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get the GitHub OAuth authorization URL."""
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'scope': 'user:email',
            'state': state,
        }

        query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
        return f'https://github.com/login/oauth/authorize?{query_string}'

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> str:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://github.com/login/oauth/access_token',
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'redirect_uri': redirect_uri,
                },
                headers={
                    'Accept': 'application/json',
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Failed to exchange code for token',
                )

            data = response.json()
            access_token = data.get('access_token')

            if not access_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='No access token received from GitHub',
                )

            return access_token

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user information from GitHub API."""
        async with httpx.AsyncClient() as client:
            # Get user profile
            user_response = await client.get(
                'https://api.github.com/user',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/vnd.github.v3+json',
                },
            )

            if user_response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Failed to get user info from GitHub',
                )

            user_data = user_response.json()

            # Get user emails
            emails_response = await client.get(
                'https://api.github.com/user/emails',
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'Accept': 'application/vnd.github.v3+json',
                },
            )

            emails_data = []
            if emails_response.status_code == 200:
                emails_data = emails_response.json()

            # Find primary email
            primary_email = user_data.get('email')
            if not primary_email and emails_data:
                for email_info in emails_data:
                    if email_info.get('primary'):
                        primary_email = email_info.get('email')
                        break

            return {
                'id': str(user_data.get('id')),
                'email': primary_email,
                'name': user_data.get('name'),
                'login': user_data.get('login'),
                'avatar_url': user_data.get('avatar_url'),
            }

    async def get_or_create_user(self, access_token: str, db_session: Session) -> User:
        """Get or create user from GitHub OAuth token."""
        user_info = await self.get_user_info(access_token)

        github_id = user_info['id']
        email = user_info['email']

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='GitHub account must have a public email address',
            )

        # Check if user exists by GitHub ID
        user = db_session.execute(
            select(User).where(User.github_id == github_id)
        ).scalar_one_or_none()

        if user:
            # Update last login
            user.last_login_at = datetime.utcnow()
            db_session.commit()
            return user

        # Check if user exists by email
        user = db_session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user:
            # Link GitHub account to existing user
            user.github_id = github_id
            user.last_login_at = datetime.utcnow()
            db_session.commit()
            return user

        # Create new user
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=user_info.get('name'),
            github_id=github_id,
            is_active=True,
            created_at=datetime.utcnow(),
            last_login_at=datetime.utcnow(),
        )

        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        return user


class GoogleOAuthProvider:
    """Google OAuth authentication provider."""

    def __init__(self, config: MultiUserConfig):
        self.config = config
        self.client_id = config.google_client_id
        self.client_secret = config.google_client_secret

        if not self.client_id or not self.client_secret:
            raise ValueError('Google OAuth credentials not configured')

    def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get the Google OAuth authorization URL."""
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'scope': 'openid email profile',
            'response_type': 'code',
            'state': state,
        }

        query_string = '&'.join([f'{k}={v}' for k, v in params.items()])
        return f'https://accounts.google.com/o/oauth2/v2/auth?{query_string}'

    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> str:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                    'code': code,
                    'grant_type': 'authorization_code',
                    'redirect_uri': redirect_uri,
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Failed to exchange code for token',
                )

            data = response.json()
            access_token = data.get('access_token')

            if not access_token:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='No access token received from Google',
                )

            return access_token

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """Get user information from Google API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                'https://www.googleapis.com/oauth2/v2/userinfo',
                headers={
                    'Authorization': f'Bearer {access_token}',
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Failed to get user info from Google',
                )

            user_data = response.json()

            return {
                'id': user_data.get('id'),
                'email': user_data.get('email'),
                'name': user_data.get('name'),
                'given_name': user_data.get('given_name'),
                'family_name': user_data.get('family_name'),
                'picture': user_data.get('picture'),
            }

    async def get_or_create_user(self, access_token: str, db_session: Session) -> User:
        """Get or create user from Google OAuth token."""
        user_info = await self.get_user_info(access_token)

        google_id = user_info['id']
        email = user_info['email']

        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Google account must have an email address',
            )

        # Check if user exists by Google ID
        user = db_session.execute(
            select(User).where(User.google_id == google_id)
        ).scalar_one_or_none()

        if user:
            # Update last login
            user.last_login_at = datetime.utcnow()
            db_session.commit()
            return user

        # Check if user exists by email
        user = db_session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if user:
            # Link Google account to existing user
            user.google_id = google_id
            user.last_login_at = datetime.utcnow()
            db_session.commit()
            return user

        # Create new user
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=user_info.get('name'),
            google_id=google_id,
            is_active=True,
            created_at=datetime.utcnow(),
            last_login_at=datetime.utcnow(),
        )

        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        return user


def get_oauth_provider(provider_name: str, config: MultiUserConfig):
    """Get OAuth provider instance by name."""
    if provider_name == 'github':
        return GitHubOAuthProvider(config)
    elif provider_name == 'google':
        return GoogleOAuthProvider(config)
    else:
        raise ValueError(f'Unsupported OAuth provider: {provider_name}')
