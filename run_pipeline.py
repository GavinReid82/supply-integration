import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

DBT = str(Path(sys.executable).parent / "dbt")

from dotenv import load_dotenv

from extractor.endpoints import fetch_price, fetch_products, fetch_stock
from extractor.loader import upload_dataframe

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

BUCKET = os.environ["S3_BUCKET"]
BASE_URL = os.environ["MKO_BASE_URL"]
TODAY = date.today().isoformat()


def extract():
    logger.info("=== EXTRACT ===")

    # Product catalog XML → products / variants / images
    products_df, variants_df, images_df = fetch_products(BASE_URL, os.environ["MKO_URL_SUFFIX_PRODUCT"])
    upload_dataframe(products_df, BUCKET, f"mko/raw/product/{TODAY}/products.parquet")
    upload_dataframe(variants_df, BUCKET, f"mko/raw/product/{TODAY}/variants.parquet")
    upload_dataframe(images_df,   BUCKET, f"mko/raw/product/{TODAY}/images.parquet")

    # Price XML
    price_df = fetch_price(BASE_URL, os.environ["MKO_URL_SUFFIX_PRICE"])
    upload_dataframe(price_df, BUCKET, f"mko/raw/price/{TODAY}/price.parquet")

    # Stock XML
    stock_df = fetch_stock(BASE_URL, os.environ["MKO_URL_SUFFIX_STOCK"])
    upload_dataframe(stock_df, BUCKET, f"mko/raw/stock/{TODAY}/stock.parquet")

    logger.info("Extract complete.")


def transform():
    logger.info("=== TRANSFORM ===")
    result = subprocess.run(
        [DBT, "run", "--project-dir", "dbt_project", "--profiles-dir", "dbt_project"],
        check=True,
    )
    logger.info("dbt run complete.")

    subprocess.run(
        [DBT, "test", "--project-dir", "dbt_project", "--profiles-dir", "dbt_project"],
        check=True,
    )
    logger.info("dbt test complete.")


if __name__ == "__main__":
    extract()
    transform()
