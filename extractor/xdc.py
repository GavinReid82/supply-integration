import io
import logging

import pandas as pd

from extractor.base import SupplierConfig, SupplierExtractor
from extractor.client import get_with_retry
from extractor.loader import upload_dataframe

logger = logging.getLogger(__name__)


class XdcExtractor(SupplierExtractor):
    """Adapter for the Xindao (XDC) supplier — XLSX files at authenticated full URLs."""

    def run(self, date: str) -> None:
        cfg = self.config
        sup = cfg.name  # "xdc"
        logger.info(f"Extracting supplier: {sup}")

        feeds = [
            ("product",             f"{sup}/raw/product/{date}/product.parquet"),
            ("product_price",       f"{sup}/raw/product_price/{date}/product_price.parquet"),
            ("print_option",        f"{sup}/raw/print_option/{date}/print_option.parquet"),
            ("print_option_price",  f"{sup}/raw/print_option_price/{date}/print_option_price.parquet"),
            ("stock",               f"{sup}/raw/stock/{date}/stock.parquet"),
        ]

        for feed, s3_path in feeds:
            url = cfg.endpoints[feed]
            logger.info(f"Fetching {feed}")
            raw = get_with_retry(url)
            df = pd.read_excel(io.BytesIO(raw))
            # Normalise headers: lowercase, spaces → underscores
            df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
            upload_dataframe(df, self.bucket, s3_path)
            logger.info(f"Uploaded {len(df):,} rows → {s3_path}")

        logger.info(f"Extraction complete: {sup}")
