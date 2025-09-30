-- Primary database initialization script
-- This runs automatically when the primary PostgreSQL container starts

-- Create a test table for replication
CREATE TABLE IF NOT EXISTS test_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create publication for all tables
CREATE PUBLICATION test_publication FOR ALL TABLES;

-- Insert some test data
INSERT INTO test_users (username, email) VALUES 
    ('alice', 'alice@example.com'),
    ('bob', 'bob@example.com'),
    ('charlie', 'charlie@example.com')
ON CONFLICT DO NOTHING;

-- Grant replication permissions
ALTER USER testuser REPLICATION;

-- Note: pg_hba.conf will be configured via Docker environment

-- Note: pg_hba.conf configuration is handled by Docker environment

-- Configure pg_hba.conf for replication (this needs to be done via Docker environment)
-- The following line should be added to pg_hba.conf:
-- host replication testuser all md5