# OpenHands Multi-User Integration Guide

This document provides comprehensive guidance on integrating the multi-user feature into the main OpenHands application.

## Architecture Overview

The multi-user implementation leverages OpenHands' existing extensibility points:

- **UserAuth Framework**: Custom JWT-based authentication
- **Storage Interfaces**: User-aware conversation, settings, and secrets storage
- **Runtime System**: Enhanced Docker runtime with user isolation
- **API Layer**: RESTful endpoints for user management
- **Middleware**: Rate limiting and quota enforcement

## Integration Steps

### 1. Install Dependencies

Add required Python packages to `pyproject.toml`:

```toml
[tool.poetry.dependencies]
# Existing dependencies...

# Multi-user support
bcrypt = "^4.0.1"
PyJWT = "^2.8.0"
sqlalchemy = "^2.0.0"
psycopg2-binary = "^2.9.7"
redis = {extras = ["hiredis"], version = "^4.6.0"}
httpx = "^0.24.1"

# Optional for testing
pytest-asyncio = {version = "^0.21.1", optional = true}
```

### 2. Configuration Integration

Add multi-user configuration to `openhands/core/config/openhands_config.py`:

```python
from features.multiuser.config.multi_user_config import MultiUserConfig

class OpenHandsConfig:
    # Existing configuration...

    multi_user: MultiUserConfig = MultiUserConfig()

    @classmethod
    def from_dict(cls, config_dict: dict) -> "OpenHandsConfig":
        # Existing logic...

        # Add multi-user config
        if "multi_user" in config_dict:
            multi_user_config = MultiUserConfig(**config_dict["multi_user"])
        else:
            multi_user_config = MultiUserConfig()

        return cls(
            # existing parameters...
            multi_user=multi_user_config
        )
```

### 3. Server Application Integration

Update `openhands/server/app.py` to include multi-user routes and middleware:

```python
from fastapi import FastAPI
from features.multiuser.api.auth_routes import router as auth_router
from features.multiuser.api.oauth_routes import router as oauth_router
from features.multiuser.middleware.rate_limiter import RateLimitMiddleware
from features.multiuser.db.connection import initialize_database

def create_app(config: OpenHandsConfig) -> FastAPI:
    app = FastAPI()

    # Initialize multi-user database if enabled
    if config.multi_user.enabled:
        initialize_database(config.multi_user)

        # Add rate limiting middleware
        app.add_middleware(RateLimitMiddleware, config=config.multi_user)

        # Add authentication routes
        app.include_router(auth_router)
        app.include_router(oauth_router)

    # Existing routes...

    return app
```

### 4. Dependency Injection Setup

Create dependency providers in `openhands/server/shared.py`:

```python
from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.connection import get_database_manager, get_db_session_sync

# Global instances
multi_user_config: MultiUserConfig = None
db_manager = None

def init_multi_user(config: OpenHandsConfig):
    """Initialize multi-user components."""
    global multi_user_config, db_manager

    multi_user_config = config.multi_user

    if multi_user_config.enabled:
        db_manager = get_database_manager(multi_user_config)

async def get_multi_user_config() -> MultiUserConfig:
    """Dependency to get multi-user configuration."""
    return multi_user_config

async def get_db_session():
    """Dependency to get database session."""
    if db_manager:
        return db_manager.get_session_sync()
    raise HTTPException(
        status_code=503,
        detail="Database not available"
    )
```

### 5. Storage Class Registration

Update storage class selection in conversation manager:

```python
from features.multiuser.storage.user_file_stores import UserFileConversationStore
from features.multiuser.storage.db_stores import DatabaseConversationStore

def get_conversation_store_class(config: OpenHandsConfig, user_id: str | None):
    """Get appropriate conversation store class based on configuration."""
    if not config.multi_user.enabled:
        # Use default single-user stores
        return FileConversationStore

    if config.multi_user.storage_backend == "database":
        return DatabaseConversationStore
    else:
        return UserFileConversationStore
```

### 6. Runtime Integration

Update runtime initialization to use multi-user runtime:

```python
from features.multiuser.runtime.multi_user_docker_runtime import MultiUserDockerRuntime

def create_runtime(
    config: OpenHandsConfig,
    event_stream: EventStream,
    sid: str,
    user_id: str | None = None,
    **kwargs
) -> Runtime:
    """Create appropriate runtime based on configuration."""

    if config.multi_user.enabled and user_id:
        return MultiUserDockerRuntime(
            config=config,
            event_stream=event_stream,
            sid=sid,
            user_id=user_id,
            **kwargs
        )
    else:
        return DockerRuntime(
            config=config,
            event_stream=event_stream,
            sid=sid,
            **kwargs
        )
```

### 7. Frontend Integration Points

The backend provides these endpoints for frontend integration:

**Authentication:**
- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/profile` - Get user profile
- `PUT /api/auth/profile` - Update user profile

**OAuth:**
- `POST /api/auth/oauth/authorize` - Get OAuth authorization URL
- `POST /api/auth/oauth/callback` - Handle OAuth callback
- `GET /api/auth/oauth/providers` - Get available OAuth providers

**User Management:**
- `GET /api/auth/me` - Get current user info

### 8. Environment Configuration

Add multi-user environment variables to config templates:

```toml
# config.toml

[multi_user]
enabled = false
jwt_secret = ""
database_url = ""
github_client_id = ""
github_client_secret = ""
google_client_id = ""
google_client_secret = ""
rate_limit_per_minute = 60
rate_limit_per_hour = 1000
max_conversations_per_user = 10
max_storage_mb_per_user = 1000
storage_backend = "file"
user_workspace_base = "/tmp/openhands/users"
```

## Feature Flags

The implementation uses feature flags to ensure backward compatibility:

```python
# Check if multi-user is enabled before using multi-user features
if config.multi_user.enabled:
    # Use multi-user logic
    user_id = await get_user_id(request)
    conversation_store = await get_user_conversation_store(user_id)
else:
    # Use single-user logic
    conversation_store = await get_conversation_store()
```

## Testing Integration

Run the multi-user tests:

```bash
# Install test dependencies
poetry install --with test

# Run multi-user tests
poetry run pytest features/multi-user/tests/ -v

# Run with coverage
poetry run pytest features/multi-user/tests/ --cov=features.multi_user --cov-report=html
```

## Database Migration

For existing installations, run database migrations:

```python
from features.multiuser.db.connection import initialize_database
from features.multiuser.config.multi_user_config import MultiUserConfig

# Initialize with migration support
config = MultiUserConfig(
    enabled=True,
    database_url="postgresql://user:pass@localhost/db"
)
db_manager = initialize_database(config, create_tables=True)

# Run schema file if needed
schema_path = "features/multi-user/db/schema.sql"
db_manager.execute_schema_file(schema_path)
```

## Deployment

Use the provided Docker Compose configuration:

```bash
cd features/multi-user/deployment
cp .env.example .env
# Edit .env with your configuration
docker compose up -d
```

## Security Considerations

1. **JWT Secrets**: Use strong, unique secrets for JWT signing
2. **Database Security**: Use encrypted connections and strong passwords
3. **Rate Limiting**: Configure appropriate limits for your use case
4. **User Isolation**: Ensure proper container and storage isolation
5. **OAuth Security**: Validate OAuth configurations and callback URLs

## Performance Optimization

1. **Database Indexing**: Ensure proper indexes on user-related queries
2. **Connection Pooling**: Configure appropriate pool sizes
3. **Caching**: Use Redis for session and rate limit data
4. **Resource Limits**: Set appropriate user quotas

## Monitoring

The implementation provides metrics for:
- User registration and authentication rates
- API usage per user
- Storage usage and quotas
- Error rates and performance

Integrate with existing monitoring systems or use the provided Prometheus/Grafana setup.

## Rollback Plan

If issues arise, disable multi-user mode:

1. Set `multi_user.enabled = false` in configuration
2. Restart the application
3. System will fall back to single-user mode
4. User data remains intact for future re-enablement

## Support and Maintenance

- **Documentation**: Comprehensive deployment and configuration guides
- **Testing**: Full test suite for all multi-user components
- **Logging**: Detailed logging for troubleshooting
- **Health Checks**: Service health monitoring
- **Backup**: Database and file storage backup procedures

## Next Steps

1. **Frontend UI**: Implement user registration and authentication UI
2. **Admin Interface**: Build admin panel for user management
3. **Advanced Features**: Add features like user groups, permissions, billing
4. **Scalability**: Optimize for large-scale deployments
5. **Integrations**: Add support for additional OAuth providers

This implementation provides a solid foundation for multi-user support while maintaining full backward compatibility with existing single-user deployments.
