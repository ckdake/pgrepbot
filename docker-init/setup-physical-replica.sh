#!/bin/bash
# Script to set up physical replication

echo "Setting up physical replica..."

# Wait for primary to be ready
echo "Waiting for primary database to be ready..."
until PGPASSWORD=testpass psql -h postgres-primary -U testuser -d testdb -c '\q' 2>/dev/null; do
  echo "Primary database not ready, waiting..."
  sleep 2
done

echo "Primary database is ready!"

# Check if this is already a replica
if [ -f /var/lib/postgresql/data/standby.signal ]; then
  echo "Already configured as physical replica"
  exec gosu postgres postgres
fi

# Initialize as postgres user
echo "Initializing physical replica..."

# Create data directory if it doesn't exist
mkdir -p /var/lib/postgresql/data
chown postgres:postgres /var/lib/postgresql/data

# Switch to postgres user for the rest of the setup
exec gosu postgres bash -c '
# Create base backup from primary
echo "Creating base backup from primary..."
PGPASSWORD=testpass pg_basebackup \
  -h postgres-primary \
  -D /var/lib/postgresql/data \
  -U testuser \
  -v -P -X stream -R

# Fix permissions
chmod 700 /var/lib/postgresql/data

# Configure pg_hba.conf to allow connections from Docker networks
echo "Configuring pg_hba.conf for Docker networks..."
cp /pg_hba.conf /var/lib/postgresql/data/pg_hba.conf
chmod 600 /var/lib/postgresql/data/pg_hba.conf

echo "Physical replica setup complete!"
echo "Starting PostgreSQL in standby mode..."

# Start PostgreSQL
exec postgres
'