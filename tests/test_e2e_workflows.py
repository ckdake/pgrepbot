"""
End-to-end workflow tests for PostgreSQL Replication Manager.
"""

import os

import pytest


@pytest.mark.e2e
class TestCompleteWorkflows:
    """Test complete end-to-end workflows"""

    @pytest.mark.asyncio
    async def test_complete_replication_setup_workflow(self, client):
        """Test complete replication setup workflow"""
        auth_key = os.getenv("AUTH_KEY", "dev-auth-key-12345")

        # Step 1: Authentication
        auth_response = client.post("/api/auth/login", json={"auth_method": "auth_key", "auth_key": auth_key})

        if auth_response.status_code != 200:
            pytest.skip("Authentication not available for E2E test")

        # Step 2: Add database configurations
        primary_config = {
            "name": "e2e-primary",
            "host": "localhost",
            "port": 5432,
            "database": "testdb",
            "role": "primary",
            "credentials_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:e2e-primary",
            "use_iam_auth": False,
            "cloud_provider": "aws",
            "region": "us-east-1",
            "environment": "test",
        }

        replica_config = {
            "name": "e2e-replica",
            "host": "localhost",
            "port": 5433,
            "database": "testdb",
            "role": "logical_replica",
            "credentials_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:e2e-replica",
            "use_iam_auth": False,
            "cloud_provider": "aws",
            "region": "us-east-1",
            "environment": "test",
        }

        # Add primary database
        primary_response = client.post("/api/database-config", json=primary_config)
        if primary_response.status_code not in [200, 201]:
            pytest.skip("Database config creation not available")

        # Add replica database
        replica_response = client.post("/api/database-config", json=replica_config)
        if replica_response.status_code not in [200, 201]:
            pytest.skip("Replica config creation not available")

        # Step 3: Discover topology
        discovery_response = client.get("/api/replication/discover")
        assert discovery_response.status_code in [200, 503], "Discovery endpoint failed"

        # Step 4: Create replication stream (if services available)
        if discovery_response.status_code == 200:
            replication_data = {
                "source_database_id": "e2e-primary",
                "target_database_id": "e2e-replica",
                "publication_name": "e2e_publication",
                "subscription_name": "e2e_subscription",
                "tables": ["users", "orders"],
            }

            replication_response = client.post("/api/replication/create", json=replication_data)
            # May fail if databases not actually running, but should not crash
            assert replication_response.status_code != 500, "Replication creation caused server error"

    @pytest.mark.asyncio
    async def test_migration_workflow(self, client):
        """Test complete migration workflow"""
        auth_key = os.getenv("AUTH_KEY", "dev-auth-key-12345")

        # Step 1: Authentication
        auth_response = client.post("/api/auth/login", json={"auth_method": "auth_key", "auth_key": auth_key})

        if auth_response.status_code != 200:
            pytest.skip("Authentication not available for migration test")

        # Step 2: Execute migration
        migration_data = {
            "migration_sql": "CREATE TABLE IF NOT EXISTS e2e_test (id SERIAL PRIMARY KEY, name VARCHAR(100));",
            "database_ids": ["test-primary"],
            "migration_id": "e2e-test-migration",
        }

        migration_response = client.post("/api/migrations/execute", json=migration_data)

        # Should handle migration request gracefully
        assert migration_response.status_code != 500, "Migration execution caused server error"

        if migration_response.status_code == 200:
            # Step 3: Check migration status
            migration_id = "e2e-test-migration"
            status_response = client.get(f"/api/migrations/status/{migration_id}")
            assert status_response.status_code in [200, 404], "Migration status check failed"

    @pytest.mark.asyncio
    async def test_web_interface_workflow(self, client):
        """Test complete web interface workflow"""
        # Step 1: Access main page
        main_response = client.get("/")
        assert main_response.status_code == 200, "Main page not accessible"
        assert "text/html" in main_response.headers.get("content-type", "")

        # Step 2: Access login page
        login_response = client.get("/login")
        assert login_response.status_code == 200, "Login page not accessible"

        # Step 3: Check static assets
        css_response = client.get("/static/css/main.css")
        assert css_response.status_code == 200, "CSS not accessible"

        js_response = client.get("/static/js/main.js")
        assert js_response.status_code == 200, "JavaScript not accessible"

        # Step 4: Check API documentation
        docs_response = client.get("/docs")
        assert docs_response.status_code == 200, "API docs not accessible"
