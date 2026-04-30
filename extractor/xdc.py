import io
import logging
from datetime import date as date_type, timedelta

import pandas as pd

from extractor.base import SupplierConfig, SupplierExtractor
from extractor.client import get_with_retry
from extractor.loader import delete_partition, upload_dataframe

logger = logging.getLogger(__name__)

_XDC_FEEDS = ("product", "product_price", "print_option", "print_option_price", "stock")


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

        self._delete_old_partition(sup, date)
        logger.info(f"Extraction complete: {sup}")

    def _delete_old_partition(self, sup: str, today: str) -> None:
        """Remove the partition from 2 days ago, keeping only today + yesterday."""
        stale = (date_type.fromisoformat(today) - timedelta(days=2)).isoformat()
        for feed in _XDC_FEEDS:
            delete_partition(self.bucket, f"{sup}/raw/{feed}/{stale}/")
