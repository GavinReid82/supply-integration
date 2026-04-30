"""
Supply Integration — daily ELT pipeline.

Task graph:
    extract (group)
        extract_mko  ──┐
        extract_xdc  ──┘  (no-op when XDC_BASE_URL is not set)
            │
    transform (group)
        dbt_seed ──> dbt_run ──> dbt_test
        (dbt_seed is skipped when seed CSVs are unchanged)
"""
import hashlib
import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from airflow.decorators import dag, task
from airflow.utils.task_group import TaskGroup
from pendulum import datetime as pendulum_datetime

PROJECT_ROOT = "/usr/local/project"
DBT_DIR = f"{PROJECT_ROOT}/dbt_project"
_SEED_HASH_KEY = "state/seed_hash"

log = logging.getLogger(__name__)


def _seeds_hash() -> str:
    """MD5 of all seed CSV files, sorted for stability."""
    seed_dir = Path(DBT_DIR) / "seeds"
    h = hashlib.md5()
    for f in sorted(seed_dir.rglob("*.csv")):
        h.update(f.read_bytes())
    return h.hexdigest()


def _read_stored_hash(bucket: str) -> str | None:
    try:
        obj = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-south-2")).get_object(
            Bucket=bucket, Key=_SEED_HASH_KEY
        )
        return obj["Body"].read().decode()
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def _write_stored_hash(bucket: str, hash_val: str) -> None:
    boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-south-2")).put_object(
        Bucket=bucket, Key=_SEED_HASH_KEY, Body=hash_val.encode()
    )


@dag(
    dag_id="supply_integration",
    schedule="@daily",
    start_date=pendulum_datetime(2025, 1, 1),
    catchup=False,
    tags=["supply_integration"],
    doc_md=__doc__,
)
def supply_integration():

    with TaskGroup("extract") as extract_group:

        @task
        def extract_mko():
            sys.path.insert(0, PROJECT_ROOT)
            from extractor.base import SupplierConfig
            from extractor.mko import MkoExtractor

            config = SupplierConfig(
                name="mko",
                base_url=os.environ["MKO_BASE_URL"],
                endpoints={
                    "product":     os.environ["MKO_URL_SUFFIX_PRODUCT"],
                    "price":       os.environ["MKO_URL_SUFFIX_PRICE"],
                    "stock":       os.environ["MKO_URL_SUFFIX_STOCK"],
                    "print":       os.environ["MKO_URL_SUFFIX_PRINT"],
                    "print_price": os.environ["MKO_URL_SUFFIX_PRINT_PRICE"],
                },
            )
            MkoExtractor(config, os.environ["S3_BUCKET"]).run(date.today().isoformat())
            log.info("MKO extraction complete.")

        @task
        def extract_xdc():
            if not os.environ.get("XDC_BASE_URL"):
                log.info("XDC_BASE_URL not set — skipping XDC extraction.")
                return

            sys.path.insert(0, PROJECT_ROOT)
            from extractor.base import SupplierConfig
            from extractor.xdc import XdcExtractor

            base = os.environ["XDC_BASE_URL"]
            config = SupplierConfig(
                name="xdc",
                endpoints={
                    "product":            f"{base}/{os.environ['XDC_URL_SUFFIX_PRODUCT']}",
                    "product_price":      f"{base}/{os.environ['XDC_URL_SUFFIX_PRODUCT_PRICE']}",
                    "print_option":       f"{base}/{os.environ['XDC_URL_SUFFIX_PRINT_OPTION']}",
                    "print_option_price": f"{base}/{os.environ['XDC_URL_SUFFIX_PRINT_OPTION_PRICE']}",
                    "stock":              f"{base}/{os.environ['XDC_URL_SUFFIX_STOCK']}",
                },
            )
            XdcExtractor(config, os.environ["S3_BUCKET"]).run(date.today().isoformat())
            log.info("XDC extraction complete.")

        [extract_mko(), extract_xdc()]

    with TaskGroup("transform") as transform_group:

        @task
        def dbt_seed():
            bucket = os.environ["S3_BUCKET"]
            current = _seeds_hash()
            if current == _read_stored_hash(bucket):
                log.info("Seed files unchanged — skipping dbt seed.")
                return
            _dbt("seed")
            _write_stored_hash(bucket, current)
            log.info("Seed hash updated.")

        @task
        def dbt_run():
            _dbt("run")

        @task
        def dbt_test():
            _dbt("test")

        dbt_seed() >> dbt_run() >> dbt_test()

    extract_group >> transform_group


def _dbt(command: str) -> None:
    run_date = date.today().isoformat()
    result = subprocess.run(
        ["dbt", command, "--project-dir", DBT_DIR, "--profiles-dir", DBT_DIR,
         "--vars", f"{{run_date: {run_date}}}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        log.info(result.stdout)
    if result.stderr:
        log.warning(result.stderr)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)


supply_integration()
