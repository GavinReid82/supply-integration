# Day 7 — README, Docker Hardening, and Unit Tests

## What I Did

I focused on three things that make the project credible as a portfolio piece rather
than just functional code: a proper README, a working Docker setup, and a full unit
test suite for the extraction layer.

---

## README

I wrote a README covering the architecture, feature set, stack, project structure,
local setup, Docker Compose instructions, the supplier extension pattern, and build
status.

During review, I caught a factual error: the "Adding a new supplier" section listed
four steps and stated that the canonical mart models require no changes. That is
incorrect — each canonical mart (e.g. `catalog.sql`) contains a UNION of all
intermediate models, so a new supplier requires adding
`UNION ALL select * from {{ ref('int_xyz_...') }}` to each of the five mart files.
The section now lists five steps.

---

## Docker

The Dockerfile and `docker-compose.yml` were already committed before this session.
On review, I found that `COPY . .` in the Dockerfile would pull in `.env`
(credentials), `.venv/` (several hundred MB), and `data/` (the DuckDB file) unless
excluded. I added a `.dockerignore` to prevent this.

The `docker-compose.yml` pattern is worth recording:

```yaml
ui:
  depends_on:
    pipeline:
      condition: service_completed_successfully
```

This ensures the UI container only starts after the pipeline container exits cleanly.
DuckDB is single-writer — if both containers tried to open the file simultaneously,
one would fail. The `service_completed_successfully` condition (not just
`service_started`) is the correct way to express this dependency in Docker Compose.

---

## Core Concept: Unit Testing with `unittest.mock`

The extraction layer makes HTTP requests and writes to AWS S3. Neither should happen
in tests. Python's `unittest.mock` module provides `patch()`, which replaces a named
object in a module's namespace for the duration of a test.

### The import site rule

The patch target must be where the name is *used*, not where it is *defined*.
`get_with_retry` is defined in `extractor.client` but imported into
`extractor.endpoints`. The correct patch target is therefore
`extractor.endpoints.get_with_retry`:

```python
@patch("extractor.endpoints.get_with_retry", return_value=PRODUCTS_XML)
def test_fetch_products_product_fields(mock_get):
    products, _, _ = fetch_products("http://example.com", "/products")
    assert products.iloc[0]["ref"] == "ABC123"
```

Patching `extractor.client.get_with_retry` would not intercept the call because
`endpoints.py` holds its own reference to the function after import.

### Fixture XML

Each test module defines minimal but structurally complete XML bytes as module-level
constants. The XML exercises the specific code paths being tested — including edge
cases like products with no stock rows, empty print job lists, and both namespaced
and non-namespaced price XML.

### Mocking boto3

`upload_dataframe` calls `boto3.client("s3", ...)`. Patching `extractor.loader.boto3`
replaces the entire boto3 module reference in that file. The test then asserts that
`put_object` was called with the correct bucket and key, and separately verifies that
the `Body` argument is valid Parquet (by deserialising it with
`pyarrow.parquet.read_table`):

```python
@patch("extractor.loader.boto3")
def test_upload_dataframe_body_is_valid_parquet(mock_boto3):
    mock_s3 = MagicMock()
    mock_boto3.client.return_value = mock_s3
    df = pd.DataFrame([{"ref": "ABC123", "price": 9.99}])

    upload_dataframe(df, "my-bucket", "mko/raw/price/2024-01-15/price.parquet")

    body = mock_s3.put_object.call_args[1]["Body"]
    result = pq.read_table(io.BytesIO(body)).to_pandas()
    assert list(result["ref"]) == ["ABC123"]
```

This tests the serialisation logic, not just that a function was called.

### Integration-style test for `MkoExtractor.run`

The `MkoExtractor` test patches all five `fetch_*` functions and `upload_dataframe`,
then runs `extractor.run("2024-01-15")` and asserts on the S3 keys used. This
confirms the correct date-partitioned layout
(`mko/raw/product/2024-01-15/products.parquet` etc.) without touching the network
or file system.

---

## Issues I Hit

### `is True` fails on a numpy boolean

The `main` column in the images DataFrame is populated with
`_t(image, "main") == "true"` — a Python boolean comparison. When stored in a pandas
DataFrame, the value becomes `numpy.bool_`, not Python's `bool`. The assertion
`assert images.iloc[0]["main"] is True` failed because
`numpy.bool_(True) is True` is `False` — they are not the same object. Fixed by
using `==` instead of `is`.

```python
# Fails: numpy.bool_ is not Python's True
assert images.iloc[0]["main"] is True

# Correct
assert images.iloc[0]["main"] == True  # noqa: E712
```

This is a general Python rule: use `==` for value equality, `is` only for identity
(e.g. `is None`). Booleans are the one case where this distinction catches people
out most often.

### Virtual environment with a broken shebang

The `.venv/` directory had been created when the project lived at
`supply_integration/` and was not recreated after the project was renamed to
`catalog_data_platform/`. The `pip` executable's shebang line still pointed to the
old path. The underlying Python symlink
(`python3.13 → /Library/Frameworks/.../python3.13`) was fine, which is why
`python -m pip` and `python -m pytest` worked but `pip` directly did not.

Fix: recreate the venv with `python3 -m venv .venv --clear`, then reinstall all
packages. The `--clear` flag removes existing contents before recreating.

---

## The Changes Made

| File | Change |
|---|---|
| `README.md` | Written: architecture, features, stack, project structure, setup, Docker, supplier extension pattern, build status |
| `.dockerignore` | New — excludes `.env`, `.venv/`, `data/`, `.git/`, `__pycache__/` from the Docker build context |
| `requirements.txt` | Added `pytest==8.3.5` |
| `tests/__init__.py` | New (empty) |
| `tests/extractor/__init__.py` | New (empty) |
| `tests/extractor/test_endpoints.py` | New — 17 tests covering all five fetch functions |
| `tests/extractor/test_client.py` | New — 4 tests covering `get_with_retry` |
| `tests/extractor/test_loader.py` | New — 3 tests covering `upload_dataframe` |
| `tests/extractor/test_mko.py` | New — 4 tests covering `MkoExtractor.run` |

**Test coverage summary:**

| Module | Tests | What is covered |
|---|---|---|
| `endpoints.py` | 17 | All 5 fetch functions — field values, FK relationships, empty input, namespace handling, null stock rows, boolean serialisation |
| `client.py` | 4 | Successful response, HTTP error, `ChunkedEncodingError` urllib fallback, other exceptions re-raised |
| `loader.py` | 3 | `put_object` called with correct args, body is valid Parquet, correct AWS region |
| `mko.py` | 4 | All feeds fetched, all 7 S3 keys correct, correct bucket, total upload count |

---

## What I Should Be Able to Explain After Day 7

- What `unittest.mock.patch` does and why the patch target must be the import site,
  not the definition site
- What `MagicMock` is and how `call_args` lets you inspect what a mocked function
  was called with
- Why fixture XML is defined at module level rather than per-test
- The difference between `is` and `==` for Python booleans, and why `numpy.bool_`
  breaks `is True`
- What a `.dockerignore` does and what happens without one (credentials in image,
  bloated build context)
- What `service_completed_successfully` means in Docker Compose and why it matters
  for a single-writer database like DuckDB
- What `pyvenv.cfg` contains and what breaks when a venv is moved without being
  recreated
