-- Replica database initialization script
-- This runs automatically when the replica PostgreSQL container starts

-- Create the same table structure (schema is not replicated)
CREATE TABLE IF NOT EXISTS test_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Wait a moment for primary to be ready, then create subscription
-- Note: This will be created by a separate script since subscriptions need the primary to be running