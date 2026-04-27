import logging
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

DBT = str(Path(sys.executable).parent / "dbt")

from dotenv import load_dotenv

from extractor.base import SupplierConfig
from extractor.mko import MkoExtractor

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
logger = logging.getLogger(__name__)

BUCKET = os.environ["S3_BUCKET"]
TODAY = date.today().isoformat()

SUPPLIERS = [
    SupplierConfig(
        name="mko",
        base_url=os.environ["MKO_BASE_URL"],
        endpoints={
            "product":     os.environ["MKO_URL_SUFFIX_PRODUCT"],
            "price":       os.environ["MKO_URL_SUFFIX_PRICE"],
            "stock":       os.environ["MKO_URL_SUFFIX_STOCK"],
            "print":       os.environ["MKO_URL_SUFFIX_PRINT"],
            "print_price": os.environ["MKO_URL_SUFFIX_PRINT_PRICE"],
        },
    ),
]

EXTRACTOR_REGISTRY = {
    "mko": MkoExtractor,
}


def extract():
    logger.info("=== EXTRACT ===")
    for config in SUPPLIERS:
        EXTRACTOR_REGISTRY[config.name](config, BUCKET).run(TODAY)
    logger.info("Extract complete.")


def transform():
    logger.info("=== TRANSFORM ===")
    for cmd in ["seed", "run", "test"]:
        subprocess.run(
            [DBT, cmd, "--project-dir", "dbt_project", "--profiles-dir", "dbt_project"],
            check=True,
        )
        logger.info(f"dbt {cmd} complete.")


if __name__ == "__main__":
    extract()
    transform()
