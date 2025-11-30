from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional


class S3Unavailable(RuntimeError):
    pass


def _boto3():
    try:
        import boto3  # type: ignore
        return boto3
    except Exception as e:  # pragma: no cover - optional dependency
        raise S3Unavailable("boto3 is required for S3 artifact store. Install 'boto3'.") from e


@dataclass
class S3ArtifactStore:
    bucket: str
    prefix: str = "manifests/"
    region: Optional[str] = None
    endpoint_url: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None

    def _client(self):
        boto3 = _boto3()
        kwargs = {}
        if self.region:
            kwargs["region_name"] = self.region
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.access_key_id and self.secret_access_key:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key
        return boto3.client("s3", **kwargs)

    def _key(self, manifest_key: str) -> str:
        p = self.prefix or ""
        if not p.endswith("/"):
            p += "/"
        return f"{p}manifest-{manifest_key}.json"

    def put_manifest(self, data: Dict[str, Any]) -> str:
        key = uuid.uuid4().hex
        body = json.dumps(data).encode("utf-8")
        c = self._client()
        c.put_object(Bucket=self.bucket, Key=self._key(key), Body=body, ContentType="application/json")
        return key

    def get_manifest(self, key: str) -> Dict[str, Any]:
        c = self._client()
        resp = c.get_object(Bucket=self.bucket, Key=self._key(key))
        body = resp["Body"].read().decode("utf-8")
        return json.loads(body)

