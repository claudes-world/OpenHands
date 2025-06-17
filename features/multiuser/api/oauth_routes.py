"""OAuth authentication routes for multi-user support."""

import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from features.multiuser.auth.jwt_user_auth import JWTUserAuth
from features.multiuser.auth.oauth_providers import get_oauth_provider
from features.multiuser.config.multi_user_config import MultiUserConfig

router = APIRouter(prefix='/api/auth/oauth', tags=['oauth'])


class OAuthAuthorizeRequest(BaseModel):
    provider: str  # 'github' or 'google'
    redirect_uri: str


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    provider: str
    code: str
    state: str
    redirect_uri: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int
    user_id: str
    email: str
    full_name: Optional[str] = None


# Dependencies (placeholders - should be replaced with proper DI)
async def get_db_session() -> Session:
    """Get database session."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail='Database session dependency not configured',
    )


async def get_config() -> MultiUserConfig:
    """Get multi-user configuration."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail='Multi-user configuration dependency not configured',
    )


@router.post('/authorize', response_model=OAuthAuthorizeResponse)
async def oauth_authorize(
    request: OAuthAuthorizeRequest,
    config: MultiUserConfig = Depends(get_config),
):
    """Get OAuth authorization URL for the specified provider."""
    # Check if multi-user is enabled
    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='OAuth authentication is not enabled',
        )

    # Validate provider
    if request.provider not in ['github', 'google']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported OAuth provider'
        )

    try:
        # Get OAuth provider
        provider = get_oauth_provider(request.provider, config)

        # Generate state parameter for CSRF protection
        state = secrets.token_urlsafe(32)

        # Get authorization URL
        authorization_url = provider.get_authorization_url(
            redirect_uri=request.redirect_uri, state=state
        )

        return OAuthAuthorizeResponse(authorization_url=authorization_url, state=state)

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post('/callback', response_model=TokenResponse)
async def oauth_callback(
    request_obj: Request,
    callback_req: OAuthCallbackRequest,
    db: Session = Depends(get_db_session),
    config: MultiUserConfig = Depends(get_config),
):
    """Handle OAuth callback and create user session."""
    # Check if multi-user is enabled
    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='OAuth authentication is not enabled',
        )

    # Validate provider
    if callback_req.provider not in ['github', 'google']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Unsupported OAuth provider'
        )

    try:
        # Get OAuth provider
        provider = get_oauth_provider(callback_req.provider, config)

        # Exchange code for access token
        access_token = await provider.exchange_code_for_token(
            callback_req.code, callback_req.redirect_uri
        )

        # Get or create user
        user = await provider.get_or_create_user(access_token, db)

        # Create JWT token
        auth = JWTUserAuth(request_obj, config, db)
        jwt_token = auth.create_access_token(user)

        return TokenResponse(
            access_token=jwt_token,
            expires_in=config.jwt_expiration_hours * 3600,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='OAuth authentication failed',
        )


@router.get('/providers')
async def get_oauth_providers(
    config: MultiUserConfig = Depends(get_config),
):
    """Get list of available OAuth providers."""
    if not config.enabled:
        return {'providers': []}

    providers = []

    # Check GitHub configuration
    if config.github_client_id and config.github_client_secret:
        providers.append({'name': 'github', 'display_name': 'GitHub', 'icon': 'github'})

    # Check Google configuration
    if config.google_client_id and config.google_client_secret:
        providers.append({'name': 'google', 'display_name': 'Google', 'icon': 'google'})

    return {'providers': providers}
