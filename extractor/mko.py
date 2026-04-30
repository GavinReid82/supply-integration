import logging
from datetime import date as date_type, timedelta

from extractor.base import SupplierConfig, SupplierExtractor
from extractor.endpoints import (
    fetch_print,
    fetch_print_price,
    fetch_price,
    fetch_products,
    fetch_stock,
)
from extractor.loader import delete_partition, upload_dataframe

logger = logging.getLogger(__name__)


class MkoExtractor(SupplierExtractor):
    """Adapter for the Makito (MKO) supplier API."""

    def run(self, date: str) -> None:
        cfg = self.config
        sup = cfg.name  # "mko"
        logger.info(f"Extracting supplier: {sup}")

        # S3 layout: {supplier}/raw/{feed}/{date}/{file}.parquet
        products_df, variants_df, images_df = fetch_products(
            cfg.base_url, cfg.endpoints["product"]
        )
        upload_dataframe(products_df, self.bucket, f"{sup}/raw/product/{date}/products.parquet")
        upload_dataframe(variants_df, self.bucket, f"{sup}/raw/product/{date}/variants.parquet")
        upload_dataframe(images_df,   self.bucket, f"{sup}/raw/product/{date}/images.parquet")

        price_df = fetch_price(cfg.base_url, cfg.endpoints["price"])
        upload_dataframe(price_df, self.bucket, f"{sup}/raw/price/{date}/price.parquet")

        print_df = fetch_print(cfg.base_url, cfg.endpoints["print"])
        upload_dataframe(print_df, self.bucket, f"{sup}/raw/print/{date}/print.parquet")

        print_price_df = fetch_print_price(cfg.base_url, cfg.endpoints["print_price"])
        upload_dataframe(print_price_df, self.bucket, f"{sup}/raw/print/{date}/print_price.parquet")

        stock_df = fetch_stock(cfg.base_url, cfg.endpoints["stock"])
        upload_dataframe(stock_df, self.bucket, f"{sup}/raw/stock/{date}/stock.parquet")

        self._delete_old_partition(sup, date)
        logger.info(f"Extraction complete: {sup}")

    def _delete_old_partition(self, sup: str, today: str) -> None:
        """Remove the partition from 2 days ago, keeping only today + yesterday."""
        stale = (date_type.fromisoformat(today) - timedelta(days=2)).isoformat()
        for feed in ("product", "price", "print", "stock"):
            delete_partition(self.bucket, f"{sup}/raw/{feed}/{stale}/")
