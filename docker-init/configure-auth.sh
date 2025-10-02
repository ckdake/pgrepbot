#!/bin/bash
# Configure authentication for all databases

echo "Configuring database authentication..."

# Wait for all databases to be ready
echo "Waiting for primary database..."
until PGPASSWORD=testpass psql -h postgres-primary -U testuser -d testdb -c '\q' 2>/dev/null; do
  sleep 2
done

echo "Waiting for replica database..."
until PGPASSWORD=testpass psql -h postgres-replica -U testuser -d testdb -c '\q' 2>/dev/null; do
  sleep 2
done

echo "Waiting for physical replica database..."
until PGPASSWORD=testpass psql -h postgres-physical-replica -U testuser -d testdb -c '\q' 2>/dev/null; do
  sleep 2
done

# Configure primary database
echo "Configuring primary database authentication..."
docker exec postgres-replication-primary bash -c "
cat >> /var/lib/postgresql/data/pg_hba.conf << 'EOF'

# Allow connections from application (Docker network and host)
host    all             testuser        0.0.0.0/0               scram-sha-256
host    replication     testuser        0.0.0.0/0               scram-sha-256
EOF
"

# Configure replica database
echo "Configuring replica database authentication..."
docker exec postgres-replication-replica bash -c "
cat >> /var/lib/postgresql/data/pg_hba.conf << 'EOF'

# Allow connections from application (Docker network and host)
host    all             testuser        0.0.0.0/0               scram-sha-256
host    replication     testuser        0.0.0.0/0               scram-sha-256
EOF
"

# Reload configurations
echo "Reloading database configurations..."
PGPASSWORD=testpass psql -h postgres-primary -U testuser -d testdb -c "SELECT pg_reload_conf();"
PGPASSWORD=testpass psql -h postgres-replica -U testuser -d testdb -c "SELECT pg_reload_conf();"

echo "Database authentication configured!"