"""AWS Secrets Manager wrapper for adviser portal credentials."""

from __future__ import annotations

import json
import logging

import boto3

from config import settings

log = logging.getLogger(__name__)


class CredentialVault:
    def __init__(self):
        self._client = boto3.client(
            "secretsmanager",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id or None,
            aws_secret_access_key=settings.aws_secret_access_key or None,
        )

    def get(self, secret_ref: str) -> dict:
        """Fetch credentials from Secrets Manager.

        Returns dict with at least 'username' and 'password' keys.
        """
        log.info("Fetching credentials from %s", secret_ref)
        resp = self._client.get_secret_value(SecretId=secret_ref)
        return json.loads(resp["SecretString"])
