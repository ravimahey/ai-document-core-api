from abc import ABC, abstractmethod
import logging
from pathlib import Path
import shutil
from typing import Any, BinaryIO

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import Settings, get_settings
from app.core.exceptions import StorageError, StorageNotFoundError

logger = logging.getLogger(__name__)


class BaseStorageService(ABC):
    @property
    @abstractmethod
    def bucket_name(self) -> str:
        """Return the target bucket or root directory name."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the storage provider identifier."""
        pass

    @abstractmethod
    def ensure_bucket_exists(self) -> None:
        """Verify bucket exists or create it if permitted."""
        pass

    @abstractmethod
    def upload_file(
        self,
        file_obj: BinaryIO,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Upload file content to object storage."""
        pass

    @abstractmethod
    def download_file(self, object_key: str, destination_path: str) -> None:
        """Download object to local filesystem destination."""
        pass

    @abstractmethod
    def object_exists(self, object_key: str) -> bool:
        """Check whether object exists in storage."""
        pass

    @abstractmethod
    def delete_object(self, object_key: str) -> bool:
        """Delete an object from storage."""
        pass

    @abstractmethod
    def get_object_metadata(self, object_key: str) -> dict[str, Any]:
        """Get object metadata including size and content type."""
        pass

    @abstractmethod
    def generate_presigned_url(
        self, object_key: str, expiration_seconds: int = 3600
    ) -> str:
        """Generate a temporary presigned URL for downloading the object."""
        pass


class S3StorageService(BaseStorageService):
    """Reusable S3-compatible storage service supporting MinIO and Amazon S3."""

    def __init__(self, settings: Settings):
        self._settings = settings
        is_minio = settings.object_storage_provider == "minio"

        self._provider = "minio" if is_minio else "s3"
        self._bucket = (
            settings.minio_bucket_name
            if is_minio
            else settings.aws_s3_bucket_name
        )

        boto_config = Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"} if is_minio else {},
            retries={"max_attempts": 3, "mode": "standard"},
        )

        client_kwargs: dict[str, Any] = {
            "service_name": "s3",
            "config": boto_config,
        }

        if is_minio:
            client_kwargs["endpoint_url"] = settings.minio_endpoint_url
            client_kwargs["aws_access_key_id"] = settings.minio_access_key
            client_kwargs["aws_secret_access_key"] = settings.minio_secret_key
            client_kwargs["region_name"] = settings.minio_region
            client_kwargs["use_ssl"] = settings.minio_secure
        else:
            client_kwargs["region_name"] = settings.aws_region
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                client_kwargs["aws_secret_access_key"] = (
                    settings.aws_secret_access_key
                )

        self._client = boto3.client(**client_kwargs)

    @property
    def bucket_name(self) -> str:
        return self._bucket

    @property
    def provider_name(self) -> str:
        return self._provider

    def ensure_bucket_exists(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                try:
                    logger.info(
                        "Bucket '%s' does not exist. Creating...", self._bucket
                    )
                    create_args: dict[str, Any] = {"Bucket": self._bucket}
                    region = self._settings.minio_region if self._provider == "minio" else self._settings.aws_region
                    if region and region != "us-east-1":
                        create_args["CreateBucketConfiguration"] = {
                            "LocationConstraint": region
                        }
                    self._client.create_bucket(**create_args)
                except ClientError as create_exc:
                    logger.error(
                        "Failed to create bucket '%s': %s", self._bucket, create_exc
                    )
                    raise StorageError(
                        f"Failed to create bucket '{self._bucket}'."
                    ) from create_exc
            else:
                logger.error(
                    "Error verifying bucket '%s': %s", self._bucket, exc
                )
                raise StorageError(
                    f"Storage connection failed for bucket '{self._bucket}'."
                ) from exc

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        extra_args: dict[str, Any] = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata

        try:
            file_obj.seek(0)
            self._client.upload_fileobj(
                Fileobj=file_obj,
                Bucket=self._bucket,
                Key=object_key,
                ExtraArgs=extra_args,
            )
        except ClientError as exc:
            logger.error("Failed uploading object '%s': %s", object_key, exc)
            raise StorageError("Object upload failed.") from exc

    def download_file(self, object_key: str, destination_path: str) -> None:
        try:
            dest = Path(destination_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            self._client.download_file(
                Bucket=self._bucket,
                Key=object_key,
                Filename=str(dest),
            )
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise StorageNotFoundError(
                    f"Object '{object_key}' not found."
                ) from exc
            logger.error("Failed downloading object '%s': %s", object_key, exc)
            raise StorageError("Object download failed.") from exc

    def object_exists(self, object_key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                return False
            raise StorageError("Failed checking object existence.") from exc

    def delete_object(self, object_key: str) -> bool:
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)
            return True
        except ClientError as exc:
            logger.error("Failed deleting object '%s': %s", object_key, exc)
            raise StorageError("Failed deleting object from storage.") from exc

    def get_object_metadata(self, object_key: str) -> dict[str, Any]:
        try:
            resp = self._client.head_object(
                Bucket=self._bucket, Key=object_key
            )
            return {
                "content_length": resp.get("ContentLength", 0),
                "content_type": resp.get("ContentType", ""),
                "etag": resp.get("ETag", "").strip('"'),
                "last_modified": resp.get("LastModified"),
                "metadata": resp.get("Metadata", {}),
            }
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchKey"):
                raise StorageNotFoundError(
                    f"Object '{object_key}' not found."
                ) from exc
            raise StorageError("Failed retrieving object metadata.") from exc

    def generate_presigned_url(
        self, object_key: str, expiration_seconds: int = 3600
    ) -> str:
        try:
            return self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expiration_seconds,
            )
        except ClientError as exc:
            logger.error(
                "Failed generating presigned URL for '%s': %s", object_key, exc
            )
            raise StorageError("Failed generating presigned URL.") from exc


class LocalStorageService(BaseStorageService):
    """Local filesystem storage service for development and testing environments."""

    def __init__(self, base_path: str = "./data/storage"):
        self._base_path = Path(base_path).resolve()
        self._base_path.mkdir(parents=True, exist_ok=True)

    @property
    def bucket_name(self) -> str:
        return "local"

    @property
    def provider_name(self) -> str:
        return "local"

    def ensure_bucket_exists(self) -> None:
        self._base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, object_key: str) -> Path:
        normalized = Path(object_key.lstrip("/"))
        resolved = (self._base_path / normalized).resolve()
        if not str(resolved).startswith(str(self._base_path)):
            raise StorageError("Path traversal detected.")
        return resolved

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_key: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        target = self._resolve_path(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        file_obj.seek(0)
        with open(target, "wb") as f:
            shutil.copyfileobj(file_obj, f)

    def download_file(self, object_key: str, destination_path: str) -> None:
        target = self._resolve_path(object_key)
        if not target.exists():
            raise StorageNotFoundError(f"Object '{object_key}' not found.")
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, dest)

    def object_exists(self, object_key: str) -> bool:
        return self._resolve_path(object_key).exists()

    def delete_object(self, object_key: str) -> bool:
        target = self._resolve_path(object_key)
        if target.exists():
            target.unlink()
            return True
        return False

    def get_object_metadata(self, object_key: str) -> dict[str, Any]:
        target = self._resolve_path(object_key)
        if not target.exists():
            raise StorageNotFoundError(f"Object '{object_key}' not found.")
        stat = target.stat()
        return {
            "content_length": stat.st_size,
            "content_type": "application/octet-stream",
            "last_modified": stat.st_mtime,
            "metadata": {},
        }

    def generate_presigned_url(
        self, object_key: str, expiration_seconds: int = 3600
    ) -> str:
        return f"file://{self._resolve_path(object_key)}"


def get_storage_service(
    settings: Settings | None = None,
) -> BaseStorageService:
    settings = settings or get_settings()
    if settings.object_storage_provider in ("minio", "s3"):
        return S3StorageService(settings)
    return LocalStorageService(settings.local_storage_path)
