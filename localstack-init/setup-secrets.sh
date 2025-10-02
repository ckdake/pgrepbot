#!/bin/bash
# LocalStack initialization script to set up Secrets Manager secrets for development

echo "Setting up Secrets Manager secrets in LocalStack..."

# Create primary database credentials secret
awslocal secretsmanager create-secret \
  --name "primary-db-creds" \
  --description "Primary database credentials for replication testing" \
  --secret-string '{
    "username": "testuser",
    "password": "testpass",
    "host": "localhost",
    "port": 5432,
    "dbname": "testdb"
  }'

# Create replica database credentials secret  
awslocal secretsmanager create-secret \
  --name "replica-db-creds" \
  --description "Replica database credentials for replication testing" \
  --secret-string '{
    "username": "testuser", 
    "password": "testpass",
    "host": "localhost",
    "port": 5433,
    "dbname": "testdb"
  }'

# Create physical replica database credentials secret
awslocal secretsmanager create-secret \
  --name "physical-replica-db-creds" \
  --description "Physical replica database credentials for replication testing" \
  --secret-string '{
    "username": "testuser",
    "password": "testpass", 
    "host": "localhost",
    "port": 5434,
    "dbname": "testdb"
  }'

echo "✅ Secrets Manager secrets created successfully"
echo "   - primary-db-creds: Primary database credentials"
echo "   - replica-db-creds: Replica database credentials"
echo "   - physical-replica-db-creds: Physical replica database credentials"