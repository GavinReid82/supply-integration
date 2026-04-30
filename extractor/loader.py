import io
import logging
import os

import boto3
import pandas as pd

logger = logging.getLogger(__name__)


def _s3():
    return boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-south-2"))


def upload_bytes(content: bytes, bucket: str, key: str) -> None:
    _s3().put_object(Body=content, Bucket=bucket, Key=key)
    logger.info(f"Uploaded raw file → s3://{bucket}/{key}")


def upload_dataframe(df: pd.DataFrame, bucket: str, key: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    _s3().put_object(Body=buf.getvalue(), Bucket=bucket, Key=key)
    logger.info(f"Uploaded parquet ({len(df)} rows) → s3://{bucket}/{key}")


def delete_partition(bucket: str, prefix: str) -> None:
    """Delete all S3 objects under prefix (e.g. 'mko/raw/stock/2026-04-28/')."""
    client = _s3()
    paginator = client.get_paginator("list_objects_v2")
    keys = [
        {"Key": obj["Key"]}
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix)
        for obj in page.get("Contents", [])
    ]
    if not keys:
        return
    client.delete_objects(Bucket=bucket, Delete={"Objects": keys})
    logger.info(f"Deleted {len(keys)} object(s) under s3://{bucket}/{prefix}")
