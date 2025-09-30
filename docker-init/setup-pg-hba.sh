#!/bin/bash
# Script to set up pg_hba.conf with Docker-friendly network ranges

echo "Setting up pg_hba.conf for Docker networks..."

# Copy our custom pg_hba.conf
cp /docker-entrypoint-initdb.d/pg_hba.conf /var/lib/postgresql/data/pg_hba.conf

# Set proper ownership
chown postgres:postgres /var/lib/postgresql/data/pg_hba.conf
chmod 600 /var/lib/postgresql/data/pg_hba.conf

echo "pg_hba.conf configured for Docker networks"