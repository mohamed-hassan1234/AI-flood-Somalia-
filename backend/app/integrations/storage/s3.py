from typing import BinaryIO, cast

import boto3

from app.core.config import Settings


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    def put(self, key: str, body: BinaryIO, content_type: str) -> str:
        self.client.upload_fileobj(body, self.bucket, key, ExtraArgs={"ContentType": content_type})
        return f"s3://{self.bucket}/{key}"

    def open(self, key: str) -> BinaryIO:
        return cast(BinaryIO, self.client.get_object(Bucket=self.bucket, Key=key)["Body"])

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)
