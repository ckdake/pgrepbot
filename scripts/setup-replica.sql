-- Setup script for replica database
-- This script sets up the subscription on the replica

\echo 'Setting up replica database...'

-- Create the same table structure (schema is not replicated)
CREATE TABLE IF NOT EXISTS test_users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create subscription to the primary
CREATE SUBSCRIPTION test_subscription 
    CONNECTION 'host=postgres-primary port=5432 dbname=testdb user=testuser password=testpass' 
    PUBLICATION test_publication;

\echo 'Replica database setup complete!'
\echo 'Subscription created: test_subscription'
\echo 'Connected to publication: test_publication'