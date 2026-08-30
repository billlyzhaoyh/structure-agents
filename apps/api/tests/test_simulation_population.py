from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
from structagent_api.contracts.simulation import TraitName
from structagent_api.materialization.materializer import HMDatasetFiles
from structagent_api.simulation.population import derive_hm_population


def dataset(root: Path) -> HMDatasetFiles:
    root.mkdir()
    connection = duckdb.connect()
    try:
        connection.execute(
            """
            CREATE TABLE customer(
                customer_id VARCHAR,
                age DOUBLE,
                club_member_status VARCHAR,
                fashion_news_frequency VARCHAR
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE article(
                article_id BIGINT,
                product_type_name VARCHAR,
                index_group_name VARCHAR
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE transactions(
                customer_id VARCHAR,
                article_id BIGINT,
                t_dat DATE,
                price DOUBLE,
                sales_channel_id INTEGER
            )
            """
        )
        connection.executemany(
            "INSERT INTO customer VALUES (?, ?, ?, ?)",
            [
                ("customer-a", 22, "ACTIVE", "Regularly"),
                ("customer-b", 38, "ACTIVE", "NONE"),
                ("customer-c", None, None, None),
                ("after-cutoff", 50, "ACTIVE", "Regularly"),
            ],
        )
        connection.executemany(
            "INSERT INTO article VALUES (?, ?, ?)",
            [(1, "Dress", "Ladieswear"), (2, "Shirt", "Menswear")],
        )
        connection.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?)",
            [
                ("customer-a", 1, "2020-01-01", 10, 2),
                ("customer-a", 1, "2020-01-10", 10, 2),
                ("customer-a", 1, "2020-01-20", 8, 2),
                ("customer-b", 2, "2019-01-01", 20, 1),
                ("customer-b", 2, "2020-01-15", 20, 1),
                ("customer-c", 1, "2020-01-05", 10, 1),
                ("after-cutoff", 1, "2020-02-02", 10, 1),
            ],
        )
        for table in ("customer", "article", "transactions"):
            connection.execute(
                f"COPY {table} TO ? (FORMAT PARQUET)", [str(root / f"{table}.parquet")]
            )
    finally:
        connection.close()
    return HMDatasetFiles.from_directory(root, revision="test-revision")


def test_population_is_cutoff_safe_minimized_and_deterministic(tmp_path: Path) -> None:
    files = dataset(tmp_path / "hm")

    first = derive_hm_population(files, cutoff=date(2020, 2, 1), seed=17, target_agents=3)
    second = derive_hm_population(files, cutoff=date(2020, 2, 1), seed=17, target_agents=3)

    assert first == second
    assert len(first.personas) == 3
    assert all(persona.agent_key.startswith("agent-") for persona in first.personas)
    assert all(
        {trait.name for trait in persona.traits} == set(TraitName) for persona in first.personas
    )
    serialized = first.model_dump_json()
    assert "customer-a" not in serialized
    assert "customer-b" not in serialized
    assert "customer-c" not in serialized
    assert "after-cutoff" not in serialized


def test_population_rejects_an_insufficient_eligible_cohort(tmp_path: Path) -> None:
    files = dataset(tmp_path / "hm")

    try:
        derive_hm_population(files, cutoff=date(2020, 2, 1), seed=17, target_agents=4)
    except ValueError as error:
        assert str(error) == "eligible H&M population is smaller than the reviewed sample"
    else:
        raise AssertionError("insufficient population was accepted")
