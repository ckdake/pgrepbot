#!/bin/bash
# Script to set up subscription after both databases are running

echo "Waiting for primary database to be ready..."
until PGPASSWORD=testpass psql -h postgres-primary -U testuser -d testdb -c '\q' 2>/dev/null; do
  echo "Primary database not ready, waiting..."
  sleep 2
done

echo "Waiting for replica database to be ready..."
until PGPASSWORD=testpass psql -h postgres-replica -U testuser -d testdb -c '\q' 2>/dev/null; do
  echo "Replica database not ready, waiting..."
  sleep 2
done

echo "Setting up subscription on replica..."

# Drop subscription if it exists (this can run in a transaction)
PGPASSWORD=testpass psql -h postgres-replica -U testuser -d testdb -c "DROP SUBSCRIPTION IF EXISTS test_subscription;"

# Create subscription (this must run outside a transaction)
PGPASSWORD=testpass psql -h postgres-replica -U testuser -d testdb -c "CREATE SUBSCRIPTION test_subscription CONNECTION 'host=postgres-primary port=5432 dbname=testdb user=testuser password=testpass' PUBLICATION test_publication WITH (create_slot = true);"

echo "Replication setup complete!"
echo "✅ Publication: test_publication (on primary)"
echo "✅ Subscription: test_subscription (on replica)"
echo "✅ Test table: test_users with sample data"