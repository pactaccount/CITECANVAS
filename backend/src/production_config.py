"""Configuration validation for Evid's persistent production storage."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ProductionStorageConfig:
    database_url: str
    bucket: str
    endpoint_url: str
    region: str
    access_key_id: str
    secret_access_key: str

    @classmethod
    def from_env(cls):
        values = {
            "database_url": os.getenv("DATABASE_URL", ""),
            "bucket": os.getenv("S3_BUCKET", ""),
            "endpoint_url": os.getenv("S3_ENDPOINT_URL", ""),
            "region": os.getenv("S3_REGION", "auto"),
            "access_key_id": os.getenv("S3_ACCESS_KEY_ID", ""),
            "secret_access_key": os.getenv("S3_SECRET_ACCESS_KEY", ""),
        }
        missing = [name for name, value in values.items() if not value and name != "region"]
        if missing:
            raise RuntimeError("Production storage is not configured: " + ", ".join(missing))
        return cls(**values)

    def document_key(self, workspace_id: str, document_id: str) -> str:
        """Keep anonymous browser workspaces physically separate in R2."""
        return f"workspaces/{workspace_id}/documents/{document_id}/original.pdf"

    def page_key(self, workspace_id: str, document_id: str, page: int) -> str:
        return f"workspaces/{workspace_id}/documents/{document_id}/pages/{page:04d}.png"
