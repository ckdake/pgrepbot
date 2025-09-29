#!/bin/bash

echo "Setting up LocalStack services for PostgreSQL Replication Manager..."

# Wait for LocalStack to be ready
sleep 10

# Create test secrets in Secrets Manager
echo "Creating test secrets..."
awslocal secretsmanager create-secret \
  --name "test/postgres/primary" \
  --secret-string '{"username":"testuser","password":"testpass","host":"postgres-primary","port":"5432","database":"testdb"}'

awslocal secretsmanager create-secret \
  --name "test/postgres/replica" \
  --secret-string '{"username":"testuser","password":"testpass","host":"postgres-replica","port":"5432","database":"testdb"}'

awslocal secretsmanager create-secret \
  --name "test/auth/admin" \
  --secret-string '{"username":"admin","password":"admin123"}'

echo "LocalStack setup complete!"
echo "Services available:"
echo "- Secrets Manager: http://localhost:4566"
echo "- Redis: Direct connection on localhost:6379"
echo "- PostgreSQL Primary: localhost:5432"
echo "- PostgreSQL Replica: localhost:5433"