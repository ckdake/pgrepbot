#!/bin/bash

echo "Setting up LocalStack services for PostgreSQL Replication Manager..."

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
sleep 15

# Function to create secret with retry
create_secret_with_retry() {
    local name=$1
    local secret_string=$2
    local max_attempts=3
    local attempt=1
    
    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Creating secret ${name} (attempt ${attempt}/${max_attempts})..."
        if awslocal secretsmanager create-secret \
            --name "${name}" \
            --secret-string "${secret_string}" 2>/dev/null; then
            echo "✅ Successfully created secret: ${name}"
            return 0
        else
            echo "⚠️  Failed to create secret ${name}, retrying..."
            sleep 2
            ((attempt++))
        fi
    done
    
    echo "❌ Failed to create secret ${name} after ${max_attempts} attempts"
    return 1
}

# Create test secrets in Secrets Manager
echo "Creating test secrets..."

create_secret_with_retry \
    "primary-db-creds" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5432,"dbname":"testdb"}'

create_secret_with_retry \
    "replica-db-creds" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5433,"dbname":"testdb"}'

create_secret_with_retry \
    "physical-replica-db-creds" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5434,"dbname":"testdb"}'

create_secret_with_retry \
    "test/auth/admin" \
    '{"username":"admin","password":"admin123"}'

create_secret_with_retry \
    "test/postgres/primary" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5432,"dbname":"testdb"}'

# Verify secrets were created
echo ""
echo "Verifying secrets..."
awslocal secretsmanager list-secrets --query 'SecretList[].Name' --output table

echo ""
echo "✅ LocalStack setup complete!"
echo ""
echo "🔧 Services available:"
echo "  - Secrets Manager: http://localhost:4566"
echo "  - Redis: localhost:6379 (direct connection)"
echo "  - PostgreSQL Primary: localhost:5432"
echo "  - PostgreSQL Replica: localhost:5433"
echo ""
echo "🧪 Test AWS integrations:"
echo "  curl http://localhost:8000/api/aws/test"