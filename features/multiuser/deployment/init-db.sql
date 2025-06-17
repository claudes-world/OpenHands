-- Database initialization script for multi-user OpenHands
-- This script is automatically executed when PostgreSQL starts

-- Create extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Set timezone
SET timezone = 'UTC';

-- Create initial admin user (optional)
-- Password: admin123! (change this in production)
INSERT INTO users (
    id,
    email,
    password_hash,
    full_name,
    is_active,
    is_admin,
    created_at,
    updated_at
) VALUES (
    uuid_generate_v4(),
    'admin@localhost',
    '$2b$12$ZYvQqS8pTqZKqj.9X8QwZOzP4TFqyQw8nVH5Y1J0q7.Vg8ZQ2Q4SG', -- admin123!
    'System Administrator',
    true,
    true,
    NOW(),
    NOW()
) ON CONFLICT (email) DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_users_email_active ON users(email, is_active);
CREATE INDEX IF NOT EXISTS idx_conversation_metadata_user_created ON conversation_metadata(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_expires ON user_sessions(user_id, expires_at);

-- Grant necessary permissions
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO openhands;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO openhands;
