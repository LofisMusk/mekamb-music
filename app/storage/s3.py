from pathlib import Path


class S3Storage:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        access_key_id: str,
        secret_access_key: str,
        bucket: str,
        region: str,
    ) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
        )

    @classmethod
    def from_settings(cls, settings: object) -> "S3Storage":
        return cls(
            endpoint_url=getattr(settings, "s3_endpoint_url"),
            access_key_id=getattr(settings, "s3_access_key_id"),
            secret_access_key=getattr(settings, "s3_secret_access_key"),
            bucket=getattr(settings, "s3_bucket"),
            region=getattr(settings, "s3_region"),
        )

    def put_file(self, source: Path, key: str) -> str:
        self.client.upload_file(str(source), self.bucket, key)
        return key

    def get_file(self, key: str, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(target))
        return target

    def delete_file(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
