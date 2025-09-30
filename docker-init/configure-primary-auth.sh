#!/bin/bash
# Configure authentication for primary database

echo "Configuring primary database authentication..."

# Wait for PostgreSQL to start
sleep 5

# Add entries to pg_hba.conf to allow connections from host
cat >> /var/lib/postgresql/data/pg_hba.conf << EOF

# Allow connections from application (Docker network and host)
host    all             testuser        0.0.0.0/0               scram-sha-256
host    replication     testuser        0.0.0.0/0               scram-sha-256
EOF

# Reload PostgreSQL configuration
psql -U testuser -d testdb -c "SELECT pg_reload_conf();"

echo "Primary database authentication configured!"