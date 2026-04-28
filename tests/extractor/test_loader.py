from unittest.mock import MagicMock, patch

import pandas as pd
import pyarrow.parquet as pq
import io

from extractor.loader import upload_dataframe


@patch("extractor.loader.boto3")
def test_upload_dataframe_calls_put_object(mock_boto3):
    mock_s3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    df = pd.DataFrame([{"id": 1, "name": "test"}])

    upload_dataframe(df, "my-bucket", "mko/raw/product/2024-01-15/products.parquet")

    mock_s3.put_object.assert_called_once()
    call_kwargs = mock_s3.put_object.call_args[1]
    assert call_kwargs["Bucket"] == "my-bucket"
    assert call_kwargs["Key"] == "mko/raw/product/2024-01-15/products.parquet"


@patch("extractor.loader.boto3")
def test_upload_dataframe_body_is_valid_parquet(mock_boto3):
    mock_s3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    df = pd.DataFrame([{"ref": "ABC123", "price": 9.99}])

    upload_dataframe(df, "my-bucket", "mko/raw/price/2024-01-15/price.parquet")

    body = mock_s3.put_object.call_args[1]["Body"]
    result = pq.read_table(io.BytesIO(body)).to_pandas()
    assert list(result["ref"]) == ["ABC123"]


@patch("extractor.loader.boto3")
def test_upload_dataframe_uses_env_region(mock_boto3):
    mock_boto3.client.return_value = MagicMock()
    df = pd.DataFrame([{"x": 1}])

    upload_dataframe(df, "bucket", "key/file.parquet")

    mock_boto3.client.assert_called_once_with("s3", region_name="eu-south-2")
