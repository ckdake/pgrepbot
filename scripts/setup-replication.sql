-- Setup script for PostgreSQL logical replication
-- This script sets up a test publication and subscription between primary and replica

-- Connect to primary database (localhost:5432)
\echo 'Setting up primary database...'

-- Create a test table
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

\echo 'Primary database setup complete!'
\echo 'Publication created: test_publication'
\echo 'Test data inserted into test_users table'