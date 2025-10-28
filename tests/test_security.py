"""
Security tests for PostgreSQL Replication Manager.
"""

import pytest


@pytest.mark.security
class TestInputValidation:
    """Test input validation and sanitization"""

    def test_sql_injection_prevention(self, client):
        """Test SQL injection prevention in API endpoints"""
        # Test malicious SQL in various endpoints
        malicious_inputs = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'/**/OR/**/1=1#",
            "1; DELETE FROM database_configs; --",
        ]

        for malicious_input in malicious_inputs:
            # Test database config endpoint
            response = client.post(
                "/api/database-config",
                json={
                    "name": malicious_input,
                    "host": "localhost",
                    "port": 5432,
                    "database": "testdb",
                    "role": "primary",
                    "credentials_arn": "arn:aws:secretsmanager:us-east-1:123456789012:secret:test",
                    "use_iam_auth": False,
                    "cloud_provider": "aws",
                    "region": "us-east-1",
                    "environment": "test",
                },
            )

            # Should either validate properly or return auth error, not 500
            assert response.status_code != 500, f"SQL injection caused server error: {malicious_input}"

    def test_xss_prevention(self, client):
        """Test XSS prevention in web interface"""
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "';alert('xss');//",
        ]

        for payload in xss_payloads:
            # Test login endpoint
            response = client.post("/api/auth/login", json={"auth_method": "auth_key", "auth_key": payload})

            # Should handle malicious input gracefully (200 is OK if it processes but rejects)
            assert response.status_code in [200, 400, 401, 422], f"XSS payload caused server error: {payload}"

            # Response should not contain unescaped payload
            if response.headers.get("content-type", "").startswith("text/html"):
                assert payload not in response.text, f"XSS payload reflected: {payload}"

    def test_unauthorized_access_prevention(self, client):
        """Test prevention of unauthorized access to protected endpoints"""
        protected_endpoints = [
            "/api/database-config",
            "/api/migrations/execute",
            "/api/alerts/",
        ]

        for endpoint in protected_endpoints:
            # Test GET requests
            response = client.get(endpoint)
            assert response.status_code in [401, 403, 302, 405], f"Unauthorized GET access allowed: {endpoint}"

            # Test POST requests
            response = client.post(endpoint, json={})
            assert response.status_code in [401, 403, 405, 422], f"Unauthorized POST access allowed: {endpoint}"

        # Note: /api/replication/discover is intentionally public for monitoring purposes


@pytest.mark.security
class TestDataProtection:
    """Test data protection and privacy measures"""

    def test_sensitive_data_not_logged(self, client):
        """Test that sensitive data is not logged or exposed"""
        # Test with credentials that should not appear in logs
        sensitive_data = [
            "password123",
            "secret-key-value",
            "arn:aws:secretsmanager:us-east-1:123456789012:secret:sensitive-data",
        ]

        for sensitive_value in sensitive_data:
            response = client.post("/api/auth/login", json={"auth_method": "auth_key", "auth_key": sensitive_value})

            # Response should not contain the sensitive value
            assert sensitive_value not in response.text, f"Sensitive data exposed: {sensitive_value}"

    def test_error_message_information_disclosure(self, client):
        """Test that error messages don't disclose sensitive information"""
        # Test various error conditions
        error_test_cases = [
            ("/api/database-config", {"invalid": "data"}),
            ("/api/auth/login", {"auth_method": "invalid"}),
            ("/api/migrations/execute", {"migration_sql": ""}),
        ]

        for endpoint, payload in error_test_cases:
            response = client.post(endpoint, json=payload)

            # Error responses should not contain sensitive system information
            sensitive_patterns = [
                "traceback",
                "exception",
                "/home/",
                "/usr/",
                "database password",
                "secret key",
                "internal server error",
            ]

            response_text = response.text.lower()
            for pattern in sensitive_patterns:
                assert pattern not in response_text, f"Sensitive info in error: {pattern} in {endpoint}"
