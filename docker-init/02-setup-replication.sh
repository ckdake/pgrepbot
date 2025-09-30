#!/bin/bash
# Setup replication configuration for primary database

echo "Configuring primary database for replication..."

# Copy custom pg_hba.conf
cp /docker-entrypoint-initdb.d/pg_hba.conf /var/lib/postgresql/data/pg_hba.conf

# Reload configuration
pg_ctl reload -D /var/lib/postgresql/data

echo "Primary database replication configuration complete!"