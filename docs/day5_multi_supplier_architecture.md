# Day 5 — Multi-Supplier Architecture Refactor

## What I Did

I refactored the codebase to support multiple suppliers. Until this point, every component
was hard-coded for Makito (MKO): the extractor, the dbt models, the UI queries, and the
supplier reference logic. Adding XDC or any other supplier would have required editing
those components directly — a sign that the architecture hadn't separated the
supplier-specific from the supplier-agnostic.

The refactor introduced five structural changes to turn supplier-specific code into
supplier-agnostic code with supplier-specific adapters. This mirrors the architectural
pattern used in production data platforms — including at Helloprint — where multiple
suppliers with different API formats feed the same downstream system.

---

## Core Concepts

### Abstract base classes and real seams

A **seam** is a place where behaviour can be swapped without editing surrounding code.
The new `SupplierExtractor` abstract base class creates exactly that:

```python
# extractor/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class SupplierConfig:
    name: str
    base_url: str
    endpoints: dict[str, str]

class SupplierExtractor(ABC):
    def __init__(self, config: SupplierConfig, bucket: str):
        self.config = config
        self.bucket = bucket

    @abstractmethod
    def run(self, date: str) -> None:
        ...
```

`ABC` stands for Abstract Base Class. The `@abstractmethod` decorator means any subclass
*must* implement `run()` — Python raises a `TypeError` at instantiation if it doesn't.
This enforces the contract: every supplier extractor exposes a `run(date)` method, and
nothing in `run_pipeline.py` needs to know anything else about the supplier.

**Why a dataclass for `SupplierConfig`?** A dataclass is a regular Python class with
`__init__`, `__repr__`, and `__eq__` generated automatically from the field annotations.
It is the right choice when an object is purely data (name, URL, endpoints dict) with
no behaviour of its own.

**The deletion test:** if I deleted `SupplierExtractor`, the complexity would not
disappear — it would reappear inside `run_pipeline.py` as supplier-specific if/else
branches. That tells me the abstraction is earning its keep.

---

### The dbt intermediate layer

Before the refactor, staging models mapped directly to mart models:

```
stg_mko_products → mko_catalog
```

There was no place to add a `supplier` column without hard-coding it in every mart.

After the refactor, an intermediate layer sits between staging and marts:

```
stg_mko_products → int_mko_products (adds supplier='mko') → catalog (UNION all suppliers)
```

Each `int_mko_*` model does one thing: add `'mko' as supplier` and pass everything
through.

```sql
-- int_mko_products.sql
select 'mko' as supplier, * from {{ ref('stg_mko_products') }}
```

This is a **pass-through with enrichment** — thin on its own, but it creates the right
shape for the canonical mart to union across suppliers. When XDC is added:

```sql
-- catalog.sql (future)
select * from {{ ref('int_mko_products') }}
union all
select * from {{ ref('int_xdc_products') }}
```

The intermediate layer means XDC staging models do not need to look like MKO staging
models. They just need to produce the same shape at the `int_*` boundary — the right
column names, the right types, the `supplier` column populated.

---

### Canonical mart models

The canonical marts (`catalog`, `variants`, `prices`, `print_options`, `print_prices`)
are supplier-agnostic tables that the UI queries. They contain data from all suppliers
via UNION.

The old `mko_catalog`, `mko_variants` etc. become simple filters:

```sql
-- mko_catalog.sql (backwards-compatible wrapper)
select * from {{ ref('catalog') }} where supplier = 'mko'
```

These stay in place so any existing tooling that queries `mko_catalog` continues to
work without change.

**A dbt gotcha discovered here:** dbt's Jinja parser processes `{{ ref() }}` calls
everywhere in a SQL file — including inside SQL comments. Writing:

```sql
-- future: union all from {{ ref('int_xdc_products') }}
```

causes a compile error because dbt tries to resolve `int_xdc_products`, which does not
exist yet. The fix is to use plain English in comments and never put Jinja syntax inside
a comment line.

---

### Shared modules in the UI

Two new modules replace inline code that appeared in multiple UI pages:

**`ui/db.py`** — a single `query()` function that opens a read-only DuckDB connection,
runs a query with parameterised inputs, and closes the connection in a `try/finally`.
Before this, `app.py` and `pages/2_Configure_Order.py` each had their own `DB_PATH`
and `duckdb.connect()` calls. Now there is one place to change if the connection
approach changes.

**`ui/supplier_reference.py`** — builds the supplier reference string from its
components. The MKO format is `variant_id` or `variant_id__teccode#areacode[__...]`.
The XDC clothing format is completely different: `size[gender_code]=variant_id`. This
logic cannot live inline in the UI — it would need to be duplicated across pages or
branched per supplier.

```python
def build(supplier: str, product_type: str, variant_id: str, prints: list[dict]) -> str:
    if supplier == "mko":
        return _mko(variant_id, prints)
    raise ValueError(f"No supplier_reference builder for {supplier!r}")
```

Adding XDC means adding `elif supplier == "xdc": return _xdc(...)`. Nothing else
changes.

---

## The Changes Made

| File | Change |
|---|---|
| `extractor/base.py` | New — `SupplierConfig` dataclass, `SupplierExtractor` ABC |
| `extractor/mko.py` | New — `MkoExtractor(SupplierExtractor)` |
| `run_pipeline.py` | Updated to use `EXTRACTOR_REGISTRY` and loop over suppliers |
| `dbt_project/models/intermediate/int_mko_*.sql` | 6 new pass-through models with `supplier` column |
| `dbt_project/models/marts/catalog.sql` | New canonical mart (replaces `mko_catalog` as primary) |
| `dbt_project/models/marts/variants.sql` | New canonical mart |
| `dbt_project/models/marts/prices.sql` | New canonical mart |
| `dbt_project/models/marts/print_options.sql` | New canonical mart |
| `dbt_project/models/marts/print_prices.sql` | New canonical mart |
| `dbt_project/models/marts/mko_catalog.sql` | Updated to filter canonical: `where supplier='mko'` |
| `dbt_project/dbt_project.yml` | Added `intermediate: +materialized: view` |
| `ui/db.py` | New — shared `query()` function |
| `ui/supplier_reference.py` | New — `build()` dispatcher + `_mko()` implementation |
| `ui/app.py` | Updated to import `from db import query` |
| `ui/pages/2_Configure_Order.py` | Updated to use `db.query` and `supplier_reference.build` |

**Result:** `dbt run` produced 22 models (12 views, 10 tables). All 17 tests passed.

---

## Issues I Hit

### dbt resolves `{{ ref() }}` in SQL comments

**What happened:** The canonical mart models had comments like:

```sql
-- future: union all select * from {{ ref('int_xdc_products') }}
```

dbt's Jinja parser processes the entire file including comments. It tried to resolve
`int_xdc_products`, which does not exist, and threw a compile error.

**Fix:** Rewrote the comments to use plain English with no Jinja syntax:

```sql
-- To add a supplier: add a union all branch pointing to its int_*_products model.
```

**Lesson:** dbt's template engine does not know the difference between active SQL and a
comment. Never put `{{ ref() }}` or `{{ env_var() }}` inside a SQL comment.

### AWS credentials not in environment for `dbt run`

**What happened:** Running `dbt run` without loading the `.env` file first caused a
parse-time error: `Env var required but not provided: 'AWS_ACCESS_KEY_ID'`. dbt reads
env vars at parse time (for `profiles.yml` expansion), before any models run.

**Fix:** `export $(grep -v '^#' .env | xargs) && dbt run ...`

**Lesson:** dbt's `{{ env_var() }}` in `profiles.yml` is evaluated at startup. If you
run dbt outside of the Python pipeline (e.g. directly in the terminal), you must load
the environment manually first.

---

## What I Should Be Able to Explain After Day 5

- What an abstract base class does and why `@abstractmethod` enforces a contract
- What a dataclass is and when to prefer it over a regular class
- Why the intermediate dbt layer is needed to support multiple suppliers cleanly
- What a canonical mart model is and how it differs from a supplier-specific mart
- Why shared modules (`db.py`, `supplier_reference.py`) reduce the cost of future changes
- Why dbt processes Jinja syntax in SQL comments, and how to avoid the trap
- What the deletion test is for assessing whether an abstraction earns its keep
