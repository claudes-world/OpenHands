"""Database connection and session management for multi-user support."""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from features.multiuser.config.multi_user_config import MultiUserConfig
from features.multiuser.db.models import Base


class DatabaseManager:
    """Manages database connections and sessions for multi-user support."""

    def __init__(self, config: MultiUserConfig):
        self.config = config
        self._engine = None
        self._session_maker = None

    @property
    def engine(self):
        """Get the database engine, creating it if necessary."""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_maker(self):
        """Get the session maker, creating it if necessary."""
        if self._session_maker is None:
            self._session_maker = sessionmaker(bind=self.engine)
        return self._session_maker

    def _create_engine(self):
        """Create the database engine based on configuration."""
        database_url = self.config.database_url

        if not database_url:
            # Default to SQLite for development
            database_url = 'sqlite:///./openhands_multiuser.db'

        # Configure engine based on database type
        if database_url.startswith('sqlite'):
            # SQLite configuration
            engine = create_engine(
                database_url,
                poolclass=StaticPool,
                connect_args={
                    'check_same_thread': False,
                    'timeout': 30,
                },
                echo=False,  # Set to True for SQL debugging
            )
        else:
            # PostgreSQL or other database configuration
            engine = create_engine(
                database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                echo=False,  # Set to True for SQL debugging
            )

        return engine

    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self):
        """Drop all database tables. Use with caution!"""
        Base.metadata.drop_all(bind=self.engine)

    def execute_schema_file(self, schema_file_path: str):
        """Execute SQL schema file for initial setup."""
        if not os.path.exists(schema_file_path):
            raise FileNotFoundError(f'Schema file not found: {schema_file_path}')

        with open(schema_file_path, 'r') as f:
            schema_sql = f.read()

        # Split into individual statements
        statements = [stmt.strip() for stmt in schema_sql.split(';') if stmt.strip()]

        with self.get_session() as session:
            for statement in statements:
                try:
                    session.execute(text(statement))
                except Exception as e:
                    print(f'Warning: Failed to execute statement: {statement[:100]}...')
                    print(f'Error: {e}')
            session.commit()

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        session = self.session_maker()
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session_sync(self) -> Session:
        """Get a database session (caller responsible for cleanup)."""
        return self.session_maker()

    def close(self):
        """Close the database engine."""
        if self._engine:
            self._engine.dispose()
            self._engine = None
        self._session_maker = None


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_database_manager(config: MultiUserConfig | None = None) -> DatabaseManager:
    """Get the global database manager instance."""
    global _db_manager

    if _db_manager is None:
        if config is None:
            raise ValueError(
                'Database manager not initialized. Provide config parameter.'
            )
        _db_manager = DatabaseManager(config)

    return _db_manager


def initialize_database(config: MultiUserConfig, create_tables: bool = True):
    """Initialize the database with the given configuration."""
    global _db_manager

    _db_manager = DatabaseManager(config)

    if create_tables:
        _db_manager.create_tables()

    return _db_manager


@contextmanager
def get_db_session(
    config: MultiUserConfig | None = None,
) -> Generator[Session, None, None]:
    """Get a database session with automatic cleanup."""
    db_manager = get_database_manager(config)
    with db_manager.get_session() as session:
        yield session


def get_db_session_sync(config: MultiUserConfig | None = None) -> Session:
    """Get a database session (caller responsible for cleanup)."""
    db_manager = get_database_manager(config)
    return db_manager.get_session_sync()
