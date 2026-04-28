from unittest.mock import MagicMock, call, patch

import pandas as pd

from extractor.base import SupplierConfig
from extractor.mko import MkoExtractor

CONFIG = SupplierConfig(
    name="mko",
    base_url="http://example.com",
    endpoints={
        "product": "/products",
        "price": "/price",
        "stock": "/stock",
        "print": "/print",
        "print_price": "/print_price",
    },
)

EMPTY_DF = pd.DataFrame()


@patch("extractor.mko.upload_dataframe")
@patch("extractor.mko.fetch_stock", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_products", return_value=(EMPTY_DF, EMPTY_DF, EMPTY_DF))
def test_mko_run_calls_all_fetch_functions(
    mock_products, mock_price, mock_print, mock_print_price, mock_stock, mock_upload
):
    MkoExtractor(config=CONFIG, bucket="test-bucket").run("2024-01-15")

    mock_products.assert_called_once_with("http://example.com", "/products")
    mock_price.assert_called_once_with("http://example.com", "/price")
    mock_print.assert_called_once_with("http://example.com", "/print")
    mock_print_price.assert_called_once_with("http://example.com", "/print_price")
    mock_stock.assert_called_once_with("http://example.com", "/stock")


@patch("extractor.mko.upload_dataframe")
@patch("extractor.mko.fetch_stock", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_products", return_value=(EMPTY_DF, EMPTY_DF, EMPTY_DF))
def test_mko_run_uploads_correct_s3_keys(
    mock_products, mock_price, mock_print, mock_print_price, mock_stock, mock_upload
):
    MkoExtractor(config=CONFIG, bucket="test-bucket").run("2024-01-15")

    uploaded_keys = [c[0][2] for c in mock_upload.call_args_list]
    assert "mko/raw/product/2024-01-15/products.parquet" in uploaded_keys
    assert "mko/raw/product/2024-01-15/variants.parquet" in uploaded_keys
    assert "mko/raw/product/2024-01-15/images.parquet" in uploaded_keys
    assert "mko/raw/price/2024-01-15/price.parquet" in uploaded_keys
    assert "mko/raw/print/2024-01-15/print.parquet" in uploaded_keys
    assert "mko/raw/print/2024-01-15/print_price.parquet" in uploaded_keys
    assert "mko/raw/stock/2024-01-15/stock.parquet" in uploaded_keys


@patch("extractor.mko.upload_dataframe")
@patch("extractor.mko.fetch_stock", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_products", return_value=(EMPTY_DF, EMPTY_DF, EMPTY_DF))
def test_mko_run_uploads_to_correct_bucket(
    mock_products, mock_price, mock_print, mock_print_price, mock_stock, mock_upload
):
    MkoExtractor(config=CONFIG, bucket="test-bucket").run("2024-01-15")

    buckets = [c[0][1] for c in mock_upload.call_args_list]
    assert all(b == "test-bucket" for b in buckets)


@patch("extractor.mko.upload_dataframe")
@patch("extractor.mko.fetch_stock", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_print", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_price", return_value=EMPTY_DF)
@patch("extractor.mko.fetch_products", return_value=(EMPTY_DF, EMPTY_DF, EMPTY_DF))
def test_mko_run_total_upload_count(
    mock_products, mock_price, mock_print, mock_print_price, mock_stock, mock_upload
):
    MkoExtractor(config=CONFIG, bucket="test-bucket").run("2024-01-15")
    assert mock_upload.call_count == 7
