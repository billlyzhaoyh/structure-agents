"""Small deterministic H&M-shaped database for local and provider smoke tests."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import duckdb

from structagent_api.materialization.materializer import HMDatasetFiles, TemporalCutoffs

SYNTHETIC_CUTOFFS = TemporalCutoffs(
    validation=datetime(2020, 1, 22),
    test=datetime(2020, 1, 29),
)


def _copy_table(connection: duckdb.DuckDBPyConnection, table: str, path: Path) -> None:
    connection.execute(
        f"COPY {table} TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
        [str(path)],
    )


def create_synthetic_hm(
    root: Path,
    *,
    complete_test_window: bool = True,
) -> HMDatasetFiles:
    """Create deterministic metadata-free retail tables with both churn classes."""
    root.mkdir(parents=True, exist_ok=False)
    connection = duckdb.connect()
    try:
        connection.execute("CREATE TABLE customer(customer_id VARCHAR PRIMARY KEY, age DOUBLE)")
        connection.execute(
            """
            CREATE TABLE article(
                article_id BIGINT PRIMARY KEY,
                product_type_name VARCHAR,
                detail_desc VARCHAR
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE transactions(
                customer_id VARCHAR,
                article_id BIGINT,
                t_dat TIMESTAMP,
                price DOUBLE,
                sales_channel_id BIGINT
            )
            """
        )
        connection.executemany(
            "INSERT INTO article VALUES (?, ?, ?)",
            [(1, "shirt", "Synthetic shirt"), (2, "trouser", "Synthetic trouser")],
        )

        prediction_times = [datetime(2020, 1, 1) + timedelta(days=7 * index) for index in range(5)]
        customers: list[tuple[str, float]] = [("sentinel", 30.0)]
        transactions: list[tuple[str, int, datetime, float, int]] = []
        for index, timestamp in enumerate(prediction_times):
            churner = f"churn-{index}"
            retained = f"retained-{index}"
            customers.extend([(churner, 20.0 + index), (retained, 40.0 + index)])
            transactions.extend(
                [
                    (churner, 1, timestamp - timedelta(days=1), 1.0, 1),
                    (retained, 1, timestamp - timedelta(days=1), 1.0, 1),
                    (retained, 1, timestamp + timedelta(days=1), 2.0, 2),
                ]
            )
        if complete_test_window:
            transactions.append(("sentinel", 2, SYNTHETIC_CUTOFFS.test + timedelta(days=7), 3.0, 1))

        connection.executemany("INSERT INTO customer VALUES (?, ?)", customers)
        connection.executemany("INSERT INTO transactions VALUES (?, ?, ?, ?, ?)", transactions)
        for table in ("article", "customer", "transactions"):
            _copy_table(connection, table, root / f"{table}.parquet")
    finally:
        connection.close()
    return HMDatasetFiles.from_directory(root, revision="synthetic")
