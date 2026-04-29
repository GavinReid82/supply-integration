import os

import duckdb
import pandas as pd

DB_PATH = os.getenv("DUCKDB_PATH", "data/catalog_data_platform.duckdb")


def query(sql: str, params: list = None) -> pd.DataFrame:
    con = duckdb.connect(DB_PATH, read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()
