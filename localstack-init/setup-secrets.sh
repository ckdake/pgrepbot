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
    "host": "postgres-primary",
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
    "host": "postgres-replica",
    "port": 5432,
    "dbname": "testdb"
  }'

echo "✅ Secrets Manager secrets created successfully"
echo "   - primary-db-creds: Primary database credentials"
echo "   - replica-db-creds: Replica database credentials"