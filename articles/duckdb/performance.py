import duckdb
import polars as pl
import pandas as pd
import numpy as np
import timeit

# Generate random data
np.random.seed(42)
data = {
    "column1": np.random.randint(0, 100, size=1000000),
    "column2": np.random.random(size=1000000),
    "column3": np.random.choice(["A", "B", "C"], size=1000000)
}

df = pd.DataFrame(data)
pl_df = pl.DataFrame(data)

# Create a DuckDB connection and register the Pandas DataFrame
conn = duckdb.connect()
conn.register('dummy_data', df)

# Define the DuckDB query function
def duckdb_query():
    return conn.execute('SELECT column3, AVG(column2) FROM dummy_data GROUP BY column3').fetchall()

# Define the Polars query function
def polars_query():
    return pl_df.groupby("column3").agg(pl.col("column2").mean())

# Measure the time taken for each query
duckdb_time = timeit.timeit(duckdb_query, number=100)
polars_time = timeit.timeit(polars_query, number=100)

print(f'''
DuckDB average time: {duckdb_time / 100:.6f} seconds
Polars average time: {polars_time / 100:.6f} seconds
''')

