#!/bin/bash

echo "Setting up LocalStack services for PostgreSQL Replication Manager..."

# Wait for LocalStack to be ready
echo "Waiting for LocalStack to be ready..."
sleep 15

# Function to create or update secret with retry
create_or_update_secret() {
    local name=$1
    local secret_string=$2
    local max_attempts=3
    local attempt=1
    
    while [[ "${attempt}" -le "${max_attempts}" ]]; do
        echo "Creating/updating secret ${name} (attempt ${attempt}/${max_attempts})..."
        
        # Try to create the secret first
        if awslocal secretsmanager create-secret \
            --name "${name}" \
            --secret-string "${secret_string}" 2>/dev/null; then
            echo "✅ Successfully created secret: ${name}"
            return 0
        else
            # If create fails, try to update existing secret
            if awslocal secretsmanager update-secret \
                --secret-id "${name}" \
                --secret-string "${secret_string}" 2>/dev/null; then
                echo "✅ Successfully updated secret: ${name}"
                return 0
            else
                echo "⚠️  Failed to create/update secret ${name}, retrying..."
                sleep 2
                ((attempt++))
            fi
        fi
    done
    
    echo "❌ Failed to create/update secret ${name} after ${max_attempts} attempts"
    return 1
}

# Create test secrets in Secrets Manager
echo "Creating test secrets..."

create_or_update_secret \
    "primary-db-creds" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5432,"dbname":"testdb"}'

create_or_update_secret \
    "replica-db-creds" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5433,"dbname":"testdb"}'

create_or_update_secret \
    "physical-replica-db-creds" \
    '{"username":"testuser","password":"testpass","host":"localhost","port":5434,"dbname":"testdb"}'

create_or_update_secret \
    "test/auth/admin" \
    '{"username":"admin","password":"admin123"}'

create_or_update_secret \
    "test/postgres/primary" \
    '{"username":"testuser","password":"testpass","host":"postgres-primary","port":5432,"dbname":"testdb"}'

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