from __future__ import annotations

import mimetypes
from pathlib import Path

from azure.core.exceptions import ResourceExistsError
from azure.identity import AzureCliCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from backend.core.config import settings


class BlobArtifactStore:
    def __init__(self) -> None:
        credential = (
            settings.azure_storage_account_key
            if settings.azure_storage_account_key
            else AzureCliCredential()
        )
        self._client = BlobServiceClient(
            account_url=settings.azure_blob_account_url,
            credential=credential,
        )
        self.container_name = settings.azure_storage_container

    def ensure_container(self) -> None:
        try:
            self._client.create_container(self.container_name)
        except ResourceExistsError:
            return

    def upload_file(
        self,
        path: Path,
        *,
        blob_name: str,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, str]:
        self.ensure_container()
        blob_client = self._client.get_blob_client(container=self.container_name, blob=blob_name)
        content_type, _ = mimetypes.guess_type(path.name)
        content_settings = ContentSettings(content_type=content_type or "application/octet-stream")
        with path.open("rb") as handle:
            blob_client.upload_blob(
                handle,
                overwrite=True,
                metadata=metadata,
                content_settings=content_settings,
            )
        return {
            "blob_name": blob_name,
            "blob_url": blob_client.url,
            "content_type": content_settings.content_type or "application/octet-stream",
        }

    def download_bytes(self, blob_name: str) -> tuple[bytes, str]:
        blob_client = self._client.get_blob_client(container=self.container_name, blob=blob_name)
        downloader = blob_client.download_blob()
        properties = blob_client.get_blob_properties()
        content_type = (
            properties.content_settings.content_type if properties.content_settings else None
        ) or "application/octet-stream"
        return downloader.readall(), content_type

    def delete_blob(self, blob_name: str) -> None:
        blob_client = self._client.get_blob_client(container=self.container_name, blob=blob_name)
        blob_client.delete_blob(delete_snapshots="include")


def build_blob_artifact_store() -> BlobArtifactStore | None:
    if not settings.azure_blob_storage_enabled:
        return None
    return BlobArtifactStore()
