# Day 2 — Data Extraction

## What I Did

I built the extraction layer of the pipeline: Python code that fetches data from the
Makito API and uploads it to AWS S3 as Parquet files. This is the **E** and first **L**
in ELT — Extract, then Load the raw data before transforming it.

---

## Core Concepts

### Why raw data goes to S3 first

A key principle in modern ELT (used at Helloprint too) is that you **preserve the raw
data before transforming it**. You never transform in-flight and discard the source.

Why? Because:
- If your transformation logic has a bug, you can re-run it against the raw data without
  hitting the API again
- It gives you an audit trail — you can see exactly what the supplier sent on any given day
- It separates concerns: extraction can succeed even if transformation fails

The date-partitioned S3 paths (`mko/raw/product/2026-04-24/products.parquet`) make it
easy to see what arrived on each run.

---

### Virtual environments

Before writing any code, I set up a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**What is a virtual environment?**
By default, `pip install` installs packages globally on your machine — shared across every
project. That causes conflicts: Project A needs `pandas==1.5`, Project B needs `pandas==2.2`.
A virtual environment is an isolated Python installation just for this project. Everything
installed inside `.venv/` stays there and doesn't affect anything else.

`source .venv/bin/activate` tells your terminal "use the Python and pip inside `.venv/`
from now on". Your prompt changes to `(.venv)` to remind you.

---

### Environment variables and `.env`

Credentials (AWS keys, API keys) must never go in code. If they did, you'd accidentally
commit them to GitHub and anyone could use them.

Instead, we store them in a `.env` file:
```
AWS_ACCESS_KEY_ID=AKIA...
MKO_BASE_URL=https://print.makito.es/...
```

The `.gitignore` file lists `.env`, which tells git to never track it.

In code, `python-dotenv` loads these into environment variables:
```python
from dotenv import load_dotenv
load_dotenv()

import os
base_url = os.environ["MKO_BASE_URL"]  # reads from the environment
```

`os.environ["KEY"]` raises an error if the key is missing — this is intentional. Better
to fail loudly at startup than silently use a None value halfway through a pipeline run.

---

## The Code

### `extractor/client.py` — HTTP requests with retry logic

```python
def get_with_retry(url: str, timeout: int = 30) -> bytes:
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
```

**`requests.Session()`** — A session object reuses the underlying TCP connection across
multiple requests. More efficient than creating a new connection each time.

**`Retry(total=5, backoff_factor=1)`** — If a request fails, retry up to 5 times. The
`backoff_factor` controls the wait between retries: 1s, 2s, 4s, 8s, 16s. This
exponential backoff avoids hammering a struggling server.

**`status_forcelist=[500, 502, 503, 504]`** — Only retry on server-side errors (5xx).
Don't retry on 404 (not found) or 401 (unauthorised) — those won't fix themselves.

**`session.mount("https://", ...)`** — Attaches the retry logic to all HTTPS requests
made by this session.

```python
    except requests.exceptions.ChunkedEncodingError as e:
        logger.warning(f"ChunkedEncodingError, falling back to urllib: {e}")
        with urlopen(url) as u:
            return u.read()
```

**ChunkedEncodingError** — Some servers (Makito included) send responses in chunks and
occasionally drop the connection mid-transfer. `requests` raises a `ChunkedEncodingError`
when this happens. The fallback to `urllib` (Python's built-in HTTP library) handles this
differently and is often more tolerant of poorly-behaved servers.

This fallback pattern came directly from the Helloprint production DAG — it existed
because Makito's server had this exact issue in production.

---

### `extractor/endpoints.py` — Parsing the API responses

#### The helper function

```python
def _t(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None
```

XML elements can be missing entirely, or present but empty. This helper handles both
cases safely, returning `None` rather than crashing. We use it everywhere to keep the
parsing code clean.

The underscore prefix on `_t` is a Python convention meaning "this is a private helper,
not part of the public interface".

#### `fetch_products` — parsing the product catalog XML

The Makito product endpoint returns XML like this:

```xml
<catalog>
  <product>
    <ref>2050</ref>
    <name>40 L/ m2</name>
    <variants>
      <variant>
        <matnr>12050000000</matnr>
        <colour>S/C</colour>
      </variant>
    </variants>
    <images>
      <image>
        <imagemax>https://...jpg</imagemax>
        <main>false</main>
      </image>
    </images>
  </product>
</catalog>
```

One XML document, one `<catalog>` root, many nested `<product>` elements. Each product
has flat fields, plus nested `<variants>` and `<images>` collections.

```python
for product in root.findall(".//product"):
    ref = _t(product, "ref")

    products.append({ "ref": ref, "name": _t(product, "name"), ... })

    for variant in product.findall("variants/variant"):
        variants.append({ "product_ref": ref, "matnr": _t(variant, "matnr"), ... })

    for image in product.findall("images/image"):
        images.append({ "product_ref": ref, "imagemax": _t(image, "imagemax"), ... })
```

**`root.findall(".//product")`** — The `".//"`  means "find anywhere in the tree". This
returns a list of all `<product>` elements.

**Why three separate DataFrames?** Because the data has different granularities:
- 1 product has many variants → can't flatten into one row without losing data
- 1 product has many images → same problem
- Keeping them separate lets dbt join them correctly later

We carry `product_ref` into every variant and image row so we can join them back.

#### `fetch_price` — the price XML

The price endpoint returns one `<product>` per product with four price tiers:

```xml
<product>
  <ref>1011</ref>
  <section1>-500</section1>  <!-- up to 500 units -->
  <price1>3.8</price1>
  <section2>1000</section2>
  <price2>3.5</price2>
  ...
</product>
```

We extract all four tier columns as-is. The dbt staging model later unpivots them into
proper rows (one row per tier, not four columns per product).

#### `fetch_stock` — the stock XML

Stock has a nested structure: each product has multiple `<infostock>` elements (one per
warehouse):

```xml
<product>
  <ref>1011</ref>
  <infostocks>
    <infostock>
      <from>+</from>
      <stock>360</stock>
      <available>immediately</available>
    </infostock>
  </infostocks>
</product>
```

We flatten this so each row in the DataFrame is one product + one warehouse entry, with
`product_ref` carried through for joining.

---

### `extractor/loader.py` — Uploading to S3

```python
def _s3():
    return boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "eu-south-2"))
```

`boto3` is the official AWS Python SDK. `boto3.client("s3")` creates an S3 client.
It automatically picks up `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from
environment variables — we don't need to pass them explicitly.

```python
def upload_dataframe(df: pd.DataFrame, bucket: str, key: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    _s3().put_object(Body=buf.getvalue(), Bucket=bucket, Key=key)
```

**Why Parquet?** Parquet is a columnar file format designed for analytics. Compared to CSV:
- Much smaller file size (columnar compression)
- Preserves data types (CSV is always strings)
- DuckDB reads it directly from S3 without downloading the whole file

**`io.BytesIO()`** — An in-memory file object. We write the Parquet bytes into memory
rather than to disk, then send those bytes directly to S3. This avoids writing temp files.

**`buf.seek(0)`** — After writing to the buffer, the cursor is at the end. We seek back
to position 0 before reading, otherwise `getvalue()` would return nothing.

---

### `run_pipeline.py` — Orchestration

```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
```

Structured logging: every log line gets a timestamp, level (INFO/WARNING/ERROR), and the
name of the module that logged it. This is how you debug a pipeline — you read the logs
and can see exactly what ran, when, and in what order.

```python
def extract():
    products_df, variants_df, images_df = fetch_products(BASE_URL, os.environ["MKO_URL_SUFFIX_PRODUCT"])
    upload_dataframe(products_df, BUCKET, f"mko/raw/product/{TODAY}/products.parquet")
    ...
```

The pipeline runs sequentially — extract all three endpoints, then hand off to dbt.
There is no Airflow here. That comes later in the roadmap (Weeks 5-6). For now, a plain
Python script running steps in order is correct and sufficient.

---

## Issues We Hit

### Issue 1: The product endpoint wasn't a manifest

**What we assumed:** Based on the Helloprint production code, the product endpoint returned
a manifest XML (a list of file URLs pointing to CSVs), which we then had to fetch separately.

**What actually happened:** The personal API key returns the full product catalog as a
single XML file directly — no manifest, no CSV links. `fetch_product_manifest` found 0
files because there were no `<file>` elements to find.

**How we diagnosed it:** I wrote a small debug script (`debug_manifest.py`) to fetch
and print the raw API response. Seeing the actual XML made the structure immediately clear.

**Lesson:** Always inspect the raw API response before writing a parser. Never assume
the response structure — check it. The Helloprint DLT wrapper had hidden this detail.

### Issue 2: `_parse_namespace` disappeared after a rewrite

**What happened:** When rewriting `endpoints.py` to fix Issue 1, the `_parse_namespace`
helper function was accidentally removed. The `fetch_price` and `fetch_stock` functions
still called it, causing a `NameError`.

**How we fixed it:** Added the function back.

**Lesson:** When rewriting a file, be careful about shared helper functions. A test suite
would have caught this immediately — adding tests is on the roadmap.

---

## What You Should Be Able to Explain After Day 2

- Why raw data is preserved in S3 before transformation
- What a virtual environment is and why you use one
- Why credentials go in `.env` and not in code
- What `requests.Session` and `Retry` do, and why exponential backoff makes sense
- How `ElementTree` parses XML — `fromstring`, `findall`, `find`, `.text`
- Why we split products/variants/images into three DataFrames
- What Parquet is and why it's better than CSV for this use case
- What `boto3` is and how it finds your AWS credentials
