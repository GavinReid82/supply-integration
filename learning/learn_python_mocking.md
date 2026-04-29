# Python Testing with unittest.mock

## Overview

The extraction layer does two things that should not happen in tests:

1. **Makes HTTP requests** to the Makito API (network, credentials, slow, flaky)
2. **Writes to AWS S3** (real money, real state, credentials required)

Tests must be fast, isolated, and runnable anywhere — including CI servers with no
network access and no AWS credentials. The solution: **replace** the HTTP and S3 calls
with fake objects that behave predictably. This is called **mocking**.

## Everyday analogy

A flight simulator replaces a real plane. The pilot practises the same procedures, presses
the same buttons, and the cockpit responds realistically — but no real aircraft moves
and no passengers are at risk. Mocking works the same way: the production code exercises
its real logic, but the I/O boundaries (network, disk, external services) are replaced
with simulators.

---

## Core concepts

### `unittest.mock.patch()`

`patch()` temporarily replaces a named object in a module's namespace with a mock.

```python
from unittest.mock import patch

@patch("extractor.endpoints.get_with_retry", return_value=b"<catalog>...</catalog>")
def test_fetch_products(mock_get):
    products, variants, images = fetch_products("http://example.com", "/products")
    assert products.iloc[0]["product_ref"] == "ABC123"
```

For the duration of `test_fetch_products`, every call to `get_with_retry` inside
`extractor.endpoints` returns `b"<catalog>...</catalog>"` instead of making a real
HTTP request. After the test returns, the original function is restored automatically.

### `MagicMock`

`MagicMock` is an object that accepts any attribute access and any method call without
raising an error. It records every call made to it.

```python
from unittest.mock import MagicMock

mock_s3 = MagicMock()
mock_s3.put_object(Body=b"...", Bucket="my-bucket", Key="some/key.parquet")

# Inspect what it was called with
mock_s3.put_object.assert_called_once()
args = mock_s3.put_object.call_args  # inspect the arguments
```

`MagicMock` is what `patch()` creates by default when you don't supply a
`return_value`.

---

## The import site rule

This is the most common mistake when learning mocking.

`patch()` must target where the name is **used**, not where it is **defined**.

```python
# extractor/client.py
def get_with_retry(url):  # DEFINED here
    ...

# extractor/endpoints.py
from extractor.client import get_with_retry  # IMPORTED (used) here

def fetch_products(base_url, suffix):
    raw = get_with_retry(base_url + suffix)  # CALLED here
    ...
```

When `endpoints.py` runs `from extractor.client import get_with_retry`, Python creates
a new name `get_with_retry` **in the `extractor.endpoints` namespace** that points to the
same function. After that, `endpoints.py` holds its own reference.

If you patch `extractor.client.get_with_retry`, you replace the original in `client.py`,
but `endpoints.py` still holds its own reference to the old function. The patch has no
effect on the code you are testing.

```python
# WRONG — patches the definition site; endpoints.py still uses the old function
@patch("extractor.client.get_with_retry", return_value=PRODUCTS_XML)

# CORRECT — patches the name in the module that actually calls it
@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
```

**Rule:** Always patch `module_under_test.name`, not `module_where_defined.name`.

---

## In the project

### `tests/extractor/test_endpoints.py`

Tests for the XML parsing functions in `extractor/endpoints.py`. The real network call
is replaced by returning fixture XML bytes directly.

```python
PRODUCTS_XML = b"""<?xml version="1.0" encoding="utf-8"?>
<catalog>
  <product>
    <ref>ABC123</ref>
    <name>Test Product</name>
    <variants>
      <variant>
        <matnr>12345</matnr>
        <colour>Red</colour>
        <size>M</size>
      </variant>
    </variants>
  </product>
</catalog>"""

@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_product_fields(mock_get):
    products, variants, images = fetch_products("http://example.com", "/products")
    assert products.iloc[0]["product_ref"] == "ABC123"
    assert products.iloc[0]["product_name"] == "Test Product"
```

`PRODUCTS_XML` is defined as a **module-level constant**, not inside the test. This
avoids repeating it across tests and makes the fixture easy to read alongside the test
that uses it.

### `tests/extractor/test_loader.py`

Tests for `upload_dataframe()` in `extractor/loader.py`. The `boto3` module is patched
entirely — not just one function.

```python
@patch("extractor.loader.boto3")
def test_upload_dataframe_body_is_valid_parquet(mock_boto3):
    # Set up the mock: boto3.client("s3") returns a mock S3 client
    mock_s3 = MagicMock()
    mock_boto3.client.return_value = mock_s3

    # Run the real code
    df = pd.DataFrame([{"ref": "ABC123", "price": 9.99}])
    upload_dataframe(df, "my-bucket", "mko/raw/price/2024-01-15/price.parquet")

    # Assert: put_object was called, and the body bytes are valid Parquet
    body = mock_s3.put_object.call_args[1]["Body"]
    result = pq.read_table(io.BytesIO(body)).to_pandas()
    assert list(result["ref"]) == ["ABC123"]
```

This test does more than check that `put_object` was called — it extracts the `Body`
argument (the bytes sent to S3) and deserialises it with `pyarrow`. If the serialisation
logic were broken, the Parquet read would fail or the values would be wrong. This tests
the real work, not just the method call.

### `tests/extractor/test_mko.py`

Integration-style test for `MkoExtractor.run()`. All five `fetch_*` functions and
`upload_dataframe` are patched. The test verifies the correct S3 keys are used.

```python
@patch("extractor.mko.upload_dataframe")
@patch("extractor.mko.fetch_print_price", return_value=pd.DataFrame())
@patch("extractor.mko.fetch_print", return_value=(pd.DataFrame(),))
@patch("extractor.mko.fetch_stock", return_value=pd.DataFrame())
@patch("extractor.mko.fetch_price", return_value=pd.DataFrame())
@patch("extractor.mko.fetch_products", return_value=(pd.DataFrame(), pd.DataFrame(), pd.DataFrame()))
def test_mko_extractor_s3_keys(mock_products, mock_price, mock_stock,
                                mock_print, mock_print_price, mock_upload):
    extractor = MkoExtractor(config)
    extractor.run("2024-01-15")

    upload_keys = [call.args[2] for call in mock_upload.call_args_list]
    assert "mko/raw/product/2024-01-15/products.parquet"    in upload_keys
    assert "mko/raw/product/2024-01-15/variants.parquet"    in upload_keys
    assert "mko/raw/price/2024-01-15/prices.parquet"        in upload_keys
```

Multiple `@patch` decorators stack. The order of arguments to the test function is
**bottom-up** — the decorator closest to the function signature comes first in the
argument list.

### `call_args` — inspecting what a mock was called with

```python
mock_fn.call_args           # last call only
mock_fn.call_args_list      # list of all calls

# A call_args object has .args (positional) and .kwargs (keyword)
call = mock_fn.call_args
call.args[0]                # first positional argument
call.kwargs["Body"]         # keyword argument named "Body"
call[1]["Body"]             # older style: [0] for args, [1] for kwargs
```

### The `numpy.bool_` vs `bool` trap

This came up when testing image parsing. The test had:

```python
assert images.iloc[0]["main"] is True   # FAILS
```

The `main` column is populated with Python's `== "true"` comparison, but pandas stores
it as `numpy.bool_`. In Python, `numpy.bool_(True) is True` is `False` — they are
different objects, even though they represent the same value.

```python
assert images.iloc[0]["main"] is True    # FAILS — different objects
assert images.iloc[0]["main"] == True    # PASSES — same value
assert bool(images.iloc[0]["main"])      # also works
```

**Rule:** Use `is` only for identity checks (`is None`, `is not None`). Use `==` for
value equality.

---

## Glossary

| Term | Meaning |
|---|---|
| Mock | A fake object that stands in for a real one during a test |
| `patch()` | Temporarily replaces a named object in a module's namespace with a mock |
| `MagicMock` | A mock object that accepts any attribute access or method call; records all calls |
| `return_value` | What a mocked function returns when called |
| `call_args` | The arguments a mock was called with on its last call |
| `call_args_list` | All calls made to a mock, as a list |
| Import site | Where a name is imported into — the correct target for `patch()` |
| Fixture | Test data defined at module level (e.g. sample XML bytes) |
| `assert_called_once()` | Asserts the mock was called exactly once |
| `numpy.bool_` | NumPy's boolean type — looks like Python's `bool` but is not identical |

---

## Cheat sheet

```python
from unittest.mock import patch, MagicMock

# Patch a function — use as decorator
@patch("module_under_test.function_name", return_value=b"fake_response")
def test_something(mock_fn):
    result = function_that_calls_it()
    assert result == expected

# Patch a whole module (e.g. boto3)
@patch("module_under_test.boto3")
def test_s3_upload(mock_boto3):
    mock_s3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    upload_dataframe(df, "bucket", "key")
    mock_s3.put_object.assert_called_once()

# Multiple patches — arguments are bottom-up
@patch("mod.c")    # mock_c — last arg
@patch("mod.b")    # mock_b
@patch("mod.a")    # mock_a — first arg after self/cls
def test_multi(mock_a, mock_b, mock_c):
    ...

# Inspect call arguments
call = mock_fn.call_args
positional = call.args[0]
keyword = call.kwargs["key"]

# Check all calls
for call in mock_fn.call_args_list:
    print(call.args, call.kwargs)

# Value vs identity
assert result == True    # value equality — correct
assert result is True    # identity — breaks with numpy.bool_
assert result is None    # identity for None — correct
```

---

## Practice

**Questions:**

1. What problem does mocking solve? Give two specific reasons why you would not want
   real HTTP requests or S3 writes in a test suite.

2. Explain the import site rule. Why does patching `extractor.client.get_with_retry`
   not intercept calls inside `extractor.endpoints`?

3. In `test_upload_dataframe_body_is_valid_parquet`, the test extracts the `Body` bytes
   from `call_args` and reads them with `pyarrow`. Why is this more valuable than just
   calling `mock_s3.put_object.assert_called_once()`?

4. A test is written like this and always passes — even when you introduce a bug. What
   is wrong?

```python
@patch("extractor.client.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products(mock_get):
    products, _, _ = fetch_products("http://example.com", "/products")
    assert len(products) == 1
```

**Short tasks:**

5. Write a test for `fetch_price` that patches `get_with_retry` to return fixture XML
   with two price tiers. Assert that the returned DataFrame has 2 rows with correct
   `unit_price` values.

6. Write a test that verifies `upload_dataframe` uses the correct AWS region using
   `mock_boto3.client.assert_called_with(...)`.
