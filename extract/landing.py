"""Where raw files land.

LANDING=./data           -> files under a local folder
LANDING=r2://my-bucket   -> objects in a Cloudflare R2 bucket (via the S3 API)

Extractors call `land(key, data)` and don't care which one is configured, so
switching from local to R2 is a one-line .env change.
"""

import os
from pathlib import Path


def _r2_client():
    import boto3

    account = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        # R2 speaks the S3 API; only the endpoint differs from AWS.
        endpoint_url=f"https://{account}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def land(key: str, data: bytes) -> str:
    """Write `data` at `key` (e.g. 'raw/app_store/sales_daily/report_date=2026-04-02/sales.tsv.gz').
    Overwrites any existing file at that key, which is what makes re-runs idempotent."""
    target = os.environ.get("LANDING", "./data")
    if target.startswith("r2://"):
        bucket = target.removeprefix("r2://")
        _r2_client().put_object(Bucket=bucket, Key=key, Body=data)
        return f"r2://{bucket}/{key}"
    path = Path(target).expanduser() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return str(path)
