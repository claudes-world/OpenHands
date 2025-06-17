"""Database models for multi-user support."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """User model for authentication and authorization."""

    __tablename__ = 'users'

    id = Column(String(36), primary_key=True)  # UUID as string
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=True)  # Nullable for OAuth-only users
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_login_at = Column(DateTime, nullable=True)

    # OAuth fields
    github_id = Column(String(255), nullable=True, unique=True)
    google_id = Column(String(255), nullable=True, unique=True)

    # Usage tracking
    total_conversations = Column(Integer, default=0, nullable=False)
    storage_used_mb = Column(Integer, default=0, nullable=False)

    # Relationships
    conversations = relationship('ConversationMetadata', back_populates='user')
    settings = relationship('UserSetting', back_populates='user')
    secrets = relationship('UserSecret', back_populates='user')


class UserSetting(Base):
    """User-specific settings storage."""

    __tablename__ = 'user_settings'

    id = Column(String(36), primary_key=True)  # UUID as string
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user = relationship('User', back_populates='settings')

    # Composite unique constraint
    __table_args__ = ({'sqlite_ignore_check': True},)  # For SQLite compatibility


class UserSecret(Base):
    """User-specific secrets storage (encrypted)."""

    __tablename__ = 'user_secrets'

    id = Column(String(36), primary_key=True)  # UUID as string
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    key = Column(String(255), nullable=False)
    encrypted_value = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    user = relationship('User', back_populates='secrets')


class ConversationMetadata(Base):
    """Extended conversation metadata with user ownership."""

    __tablename__ = 'conversation_metadata'

    conversation_id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Metrics
    accumulated_cost = Column(
        String(50), nullable=True
    )  # Store as string for precision
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)

    # Status
    status = Column(String(50), nullable=True)

    # Relationships
    user = relationship('User', back_populates='conversations')


class UserSession(Base):
    """User session tracking for JWT tokens."""

    __tablename__ = 'user_sessions'

    id = Column(String(36), primary_key=True)  # UUID as string
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    token_jti = Column(String(255), nullable=False, unique=True, index=True)  # JWT ID
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_revoked = Column(Boolean, default=False, nullable=False)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 compatible

    # Relationships
    user = relationship('User')
