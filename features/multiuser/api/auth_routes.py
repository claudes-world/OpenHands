"""Authentication API routes for multi-user support."""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from features.multiuser.auth.jwt_user_auth import JWTUserAuth
from features.multiuser.auth.password_utils import (
    hash_password,
    is_strong_password,
    verify_password,
)
from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.models import User

router = APIRouter(prefix='/api/auth', tags=['authentication'])


# Request/Response models
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    expires_in: int
    user_id: str
    email: str
    full_name: Optional[str] = None


class UserProfile(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    created_at: datetime
    total_conversations: int
    storage_used_mb: int


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


# Dependency to get database session
async def get_db_session() -> Session:
    """Get database session. TODO: Implement proper dependency injection."""
    # This is a placeholder - should be replaced with proper DI
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail='Database session dependency not configured',
    )


# Dependency to get multi-user config
async def get_config() -> MultiUserConfig:
    """Get multi-user configuration. TODO: Implement proper dependency injection."""
    # This is a placeholder - should be replaced with proper DI
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail='Multi-user configuration dependency not configured',
    )


@router.post('/register', response_model=TokenResponse)
async def register(
    request: Request,
    register_req: RegisterRequest,
    db: Session = Depends(get_db_session),
    config: MultiUserConfig = Depends(get_config),
):
    """Register a new user."""
    # Check if multi-user is enabled
    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='User registration is not enabled',
        )

    # Validate password strength
    is_valid, errors = is_strong_password(register_req.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={'message': 'Password does not meet requirements', 'errors': errors},
        )

    # Check if user already exists
    existing_user = db.execute(
        select(User).where(User.email == register_req.email)
    ).scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail='User with this email already exists',
        )

    # Create new user
    user = User(
        id=str(uuid.uuid4()),
        email=register_req.email,
        password_hash=hash_password(register_req.password),
        full_name=register_req.full_name,
        is_active=True,
        created_at=datetime.utcnow(),
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    # Create access token
    auth = JWTUserAuth(request, config, db)
    access_token = auth.create_access_token(user)

    return TokenResponse(
        access_token=access_token,
        expires_in=config.jwt_expiration_hours * 3600,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


@router.post('/login', response_model=TokenResponse)
async def login(
    request: Request,
    login_req: LoginRequest,
    db: Session = Depends(get_db_session),
    config: MultiUserConfig = Depends(get_config),
):
    """Authenticate user and return access token."""
    # Check if multi-user is enabled
    if not config.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='User authentication is not enabled',
        )

    # Find user by email
    user = db.execute(
        select(User).where(User.email == login_req.email, User.is_active)
    ).scalar_one_or_none()

    if not user or not user.password_hash:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid email or password'
        )

    # Verify password
    if not verify_password(login_req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid email or password'
        )

    # Update last login time
    user.last_login_at = datetime.utcnow()
    db.commit()

    # Create access token
    auth = JWTUserAuth(request, config, db)
    access_token = auth.create_access_token(user)

    return TokenResponse(
        access_token=access_token,
        expires_in=config.jwt_expiration_hours * 3600,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


@router.post('/logout')
async def logout(
    request: Request,
    auth: JWTUserAuth = Depends(JWTUserAuth.get_instance),
):
    """Logout user by revoking the access token."""
    token = auth._extract_token()
    if token:
        await auth.revoke_token(token)

    return {'message': 'Successfully logged out'}


@router.get('/profile', response_model=UserProfile)
async def get_profile(
    auth: JWTUserAuth = Depends(JWTUserAuth.get_instance),
):
    """Get current user profile."""
    user = await auth._get_current_user()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='User not authenticated'
        )

    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        created_at=user.created_at,
        total_conversations=user.total_conversations,
        storage_used_mb=user.storage_used_mb,
    )


@router.put('/profile', response_model=UserProfile)
async def update_profile(
    update_req: UpdateProfileRequest,
    auth: JWTUserAuth = Depends(JWTUserAuth.get_instance),
    db: Session = Depends(get_db_session),
):
    """Update current user profile."""
    user = await auth._get_current_user()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='User not authenticated'
        )

    # Update fields
    if update_req.full_name is not None:
        user.full_name = update_req.full_name

    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        created_at=user.created_at,
        total_conversations=user.total_conversations,
        storage_used_mb=user.storage_used_mb,
    )


@router.post('/change-password')
async def change_password(
    change_req: ChangePasswordRequest,
    auth: JWTUserAuth = Depends(JWTUserAuth.get_instance),
    db: Session = Depends(get_db_session),
):
    """Change user password."""
    user = await auth._get_current_user()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='User not authenticated'
        )

    # Verify current password
    if not user.password_hash or not verify_password(
        change_req.current_password, user.password_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Current password is incorrect',
        )

    # Validate new password strength
    is_valid, errors = is_strong_password(change_req.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                'message': 'New password does not meet requirements',
                'errors': errors,
            },
        )

    # Update password
    user.password_hash = hash_password(change_req.new_password)
    user.updated_at = datetime.utcnow()
    db.commit()

    return {'message': 'Password changed successfully'}


@router.get('/me')
async def get_current_user_info(
    auth: JWTUserAuth = Depends(JWTUserAuth.get_instance),
):
    """Get basic current user information."""
    user_id = await auth.get_user_id()
    user_email = await auth.get_user_email()

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='User not authenticated'
        )

    return {
        'user_id': user_id,
        'email': user_email,
        'authenticated': True,
    }
