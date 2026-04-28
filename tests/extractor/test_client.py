from unittest.mock import MagicMock, patch

import pytest
import requests

from extractor.client import get_with_retry


@patch("extractor.client.requests.Session")
def test_get_with_retry_returns_content(mock_session_cls):
    mock_response = MagicMock()
    mock_response.content = b"<data/>"
    mock_session_cls.return_value.get.return_value = mock_response

    result = get_with_retry("http://example.com/feed")

    assert result == b"<data/>"
    mock_session_cls.return_value.get.assert_called_once_with(
        "http://example.com/feed", timeout=30, stream=False
    )


@patch("extractor.client.requests.Session")
def test_get_with_retry_raises_on_http_error(mock_session_cls):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError("500")
    mock_session_cls.return_value.get.return_value = mock_response

    with pytest.raises(requests.exceptions.HTTPError):
        get_with_retry("http://example.com/feed")


@patch("extractor.client.urlopen")
@patch("extractor.client.requests.Session")
def test_get_with_retry_chunked_encoding_falls_back_to_urllib(mock_session_cls, mock_urlopen):
    mock_session_cls.return_value.get.side_effect = (
        requests.exceptions.ChunkedEncodingError("chunked")
    )
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_cm)
    mock_cm.__exit__ = MagicMock(return_value=False)
    mock_cm.read.return_value = b"<fallback/>"
    mock_urlopen.return_value = mock_cm

    result = get_with_retry("http://example.com/feed")

    assert result == b"<fallback/>"
    mock_urlopen.assert_called_once_with("http://example.com/feed")


@patch("extractor.client.requests.Session")
def test_get_with_retry_reraises_non_chunked_errors(mock_session_cls):
    mock_session_cls.return_value.get.side_effect = requests.exceptions.ConnectionError("down")

    with pytest.raises(requests.exceptions.ConnectionError):
        get_with_retry("http://example.com/feed")
