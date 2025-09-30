"""
AWS Secrets Manager integration service.

This module provides functionality for retrieving and caching database credentials
from AWS Secrets Manager with automatic credential rotation support.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class SecretsManagerError(Exception):
    """Exception raised for Secrets Manager operations."""

    pass


class SecretsManagerClient:
    """
    AWS Secrets Manager client with credential retrieval and caching.

    Provides secure credential retrieval with automatic caching and rotation support.
    """

    def __init__(self, region_name: str = "us-east-1", endpoint_url: str | None = None):
        """
        Initialize Secrets Manager client.

        Args:
            region_name: AWS region name
            endpoint_url: Optional endpoint URL for LocalStack testing
        """
        self.region_name = region_name
        self.endpoint_url = endpoint_url
        self._client = None
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_ttl = timedelta(minutes=15)  # Cache credentials for 15 minutes

    @property
    def client(self):
        """Lazy initialization of boto3 client."""
        if self._client is None:
            try:
                self._client = boto3.client(
                    "secretsmanager",
                    region_name=self.region_name,
                    endpoint_url=self.endpoint_url,
                )
            except Exception as e:
                logger.error(f"Failed to initialize Secrets Manager client: {e}")
                raise SecretsManagerError(f"Failed to initialize client: {e}") from e
        return self._client

    async def get_secret(self, secret_name: str, force_refresh: bool = False) -> dict[str, Any]:
        """
        Retrieve secret from AWS Secrets Manager with caching.

        Args:
            secret_name: Name or ARN of the secret
            force_refresh: Force refresh from AWS, bypassing cache

        Returns:
            Dictionary containing secret data

        Raises:
            SecretsManagerError: If secret retrieval fails
        """
        # Check cache first (unless force refresh)
        if not force_refresh and secret_name in self._cache:
            cached_entry = self._cache[secret_name]
            if datetime.now() < cached_entry["expires_at"]:
                logger.debug(f"Returning cached secret for {secret_name}")
                return cached_entry["data"]

        try:
            logger.info(f"Retrieving secret {secret_name} from AWS Secrets Manager")
            response = self.client.get_secret_value(SecretId=secret_name)

            # Parse secret string as JSON
            secret_data = json.loads(response["SecretString"])

            # Cache the result
            self._cache[secret_name] = {
                "data": secret_data,
                "expires_at": datetime.now() + self._cache_ttl,
                "retrieved_at": datetime.now(),
            }

            logger.info(f"Successfully retrieved and cached secret {secret_name}")
            return secret_data

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceNotFoundException":
                raise SecretsManagerError(f"Secret {secret_name} not found") from e
            elif error_code == "InvalidRequestException":
                raise SecretsManagerError(f"Invalid request for secret {secret_name}") from e
            elif error_code == "InvalidParameterException":
                raise SecretsManagerError(f"Invalid parameter for secret {secret_name}") from e
            elif error_code == "DecryptionFailureException":
                raise SecretsManagerError(f"Failed to decrypt secret {secret_name}") from e
            elif error_code == "InternalServiceErrorException":
                raise SecretsManagerError(f"AWS internal service error for secret {secret_name}") from e
            else:
                raise SecretsManagerError(f"AWS error retrieving secret {secret_name}: {error_code}") from e
        except json.JSONDecodeError as e:
            raise SecretsManagerError(f"Failed to parse secret {secret_name} as JSON") from e
        except Exception as e:
            logger.error(f"Unexpected error retrieving secret {secret_name}: {e}")
            raise SecretsManagerError(f"Unexpected error retrieving secret {secret_name}: {e}") from e

    async def get_database_credentials(self, secret_name: str) -> dict[str, str]:
        """
        Retrieve database credentials from Secrets Manager.

        Expected secret format:
        {
            "username": "db_user",
            "password": "db_password",
            "host": "db_host",
            "port": 5432,
            "dbname": "database_name"
        }

        Args:
            secret_name: Name or ARN of the database secret

        Returns:
            Dictionary with database connection parameters

        Raises:
            SecretsManagerError: If credentials are invalid or missing required fields
        """
        secret_data = await self.get_secret(secret_name)

        # Validate required fields
        required_fields = ["username", "password", "host", "port", "dbname"]
        missing_fields = [field for field in required_fields if field not in secret_data]

        if missing_fields:
            raise SecretsManagerError(f"Database secret {secret_name} missing required fields: {missing_fields}")

        return {
            "username": str(secret_data["username"]),
            "password": str(secret_data["password"]),
            "host": str(secret_data["host"]),
            "port": int(secret_data["port"]),
            "dbname": str(secret_data["dbname"]),
        }

    def clear_cache(self, secret_name: str | None = None) -> None:
        """
        Clear cached secrets.

        Args:
            secret_name: Specific secret to clear, or None to clear all
        """
        if secret_name:
            self._cache.pop(secret_name, None)
            logger.info(f"Cleared cache for secret {secret_name}")
        else:
            self._cache.clear()
            logger.info("Cleared all cached secrets")

    def get_cache_info(self) -> dict[str, Any]:
        """
        Get information about cached secrets.

        Returns:
            Dictionary with cache statistics and entries
        """
        now = datetime.now()
        cache_info = {
            "total_entries": len(self._cache),
            "cache_ttl_minutes": self._cache_ttl.total_seconds() / 60,
            "entries": {},
        }

        for secret_name, entry in self._cache.items():
            cache_info["entries"][secret_name] = {
                "retrieved_at": entry["retrieved_at"].isoformat(),
                "expires_at": entry["expires_at"].isoformat(),
                "is_expired": now >= entry["expires_at"],
                "time_to_expiry_seconds": (entry["expires_at"] - now).total_seconds(),
            }

        return cache_info
