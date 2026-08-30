"""Cutoff-safe aggregate H&M personas for the reviewed simulation study."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Final, Literal

import duckdb
from pydantic import Field, model_validator

from structagent_api.catalog import RELBENCH_V1_REVISION
from structagent_api.contracts.models import StrictModel
from structagent_api.contracts.simulation import ContractDigest, TraitName
from structagent_api.materialization.hm_assets import REL_HM_ASSETS
from structagent_api.materialization.materializer import HMDatasetFiles
from structagent_api.simulation.edsl import AgentTrait

TRAIT_QUERY_VERSION: Final = "hm-personas-v1"

TRAIT_QUERY: Final = """
WITH source_transactions AS (
    SELECT
        CAST(t.customer_id AS VARCHAR) AS customer_id,
        CAST(t.article_id AS VARCHAR) AS article_id,
        CAST(t.t_dat AS DATE) AS transaction_date,
        CAST(t.price AS DOUBLE) AS price,
        CAST(t.sales_channel_id AS INTEGER) AS sales_channel_id,
        COALESCE(CAST(a.product_type_name AS VARCHAR), 'unknown') AS product_type_name,
        COALESCE(CAST(a.index_group_name AS VARCHAR), 'unknown') AS index_group_name
    FROM transactions t
    JOIN article a USING (article_id)
    WHERE CAST(t.t_dat AS DATE) < CAST(? AS DATE)
),
daily_prices AS (
    SELECT article_id, transaction_date, median(price) AS daily_price, count(*) AS daily_count
    FROM source_transactions
    GROUP BY article_id, transaction_date
),
rolling_reference AS (
    SELECT
        article_id,
        transaction_date,
        median(daily_price) OVER (
            PARTITION BY article_id ORDER BY transaction_date
            RANGE BETWEEN INTERVAL 28 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
        ) AS reference_price,
        sum(daily_count) OVER (
            PARTITION BY article_id ORDER BY transaction_date
            RANGE BETWEEN INTERVAL 28 DAY PRECEDING AND INTERVAL 1 DAY PRECEDING
        ) AS reference_count
    FROM daily_prices
),
enriched AS (
    SELECT
        t.*,
        CASE WHEN r.reference_count >= 3 AND r.reference_price > 0
             THEN CAST(t.price < r.reference_price * 0.95 AS INTEGER)
             ELSE NULL END AS markdown_proxy
    FROM source_transactions t
    LEFT JOIN rolling_reference r USING (article_id, transaction_date)
),
aggregates AS (
    SELECT
        customer_id,
        min(transaction_date) AS first_transaction,
        max(transaction_date) AS last_transaction,
        count(*) AS transaction_count,
        avg(price) AS average_price,
        avg(CAST(sales_channel_id = 2 AS INTEGER)) AS online_share,
        mode(product_type_name) AS primary_category,
        mode(index_group_name) AS index_group,
        avg(markdown_proxy) AS markdown_share
    FROM enriched
    GROUP BY customer_id
),
eligible AS (
    SELECT
        x.*,
        c.age,
        COALESCE(CAST(c.club_member_status AS VARCHAR), 'unknown') AS club_member_status,
        COALESCE(CAST(c.fashion_news_frequency AS VARCHAR), 'unknown') AS fashion_news_frequency
    FROM aggregates x
    JOIN customer c USING (customer_id)
),
sampled AS (
    SELECT *
    FROM eligible
    ORDER BY hash(customer_id || CAST(? AS VARCHAR))
    LIMIT ?
),
banded AS (
    SELECT
        *,
        ntile(3) OVER (ORDER BY transaction_count, customer_id) AS frequency_tile,
        ntile(3) OVER (ORDER BY average_price, customer_id) AS basket_tile,
        ntile(3) OVER (ORDER BY markdown_share NULLS FIRST, customer_id) AS markdown_tile
    FROM sampled
)
SELECT * FROM banded ORDER BY hash(customer_id || CAST(? AS VARCHAR))
""".strip()


class SimulationPersona(StrictModel):
    """One pseudonymous agent with only the approved aggregate projection."""

    agent_key: str = Field(pattern=r"^agent-[0-9a-f]{24}$")
    traits: tuple[AgentTrait, ...]

    @model_validator(mode="after")
    def every_trait_is_present(self) -> SimulationPersona:
        if {trait.name for trait in self.traits} != set(TraitName):
            raise ValueError("persona must contain every approved aggregate trait")
        return self


class SimulationPopulationPackage(StrictModel):
    """Canonical minimized output of the trusted H&M trait boundary."""

    schema_version: Literal["1"] = "1"
    dataset_revision: str = Field(min_length=1)
    dataset_manifest_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    trait_query_digest: ContractDigest = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    cutoff: date
    seed: int = Field(ge=0, le=2**32 - 1)
    personas: tuple[SimulationPersona, ...] = Field(min_length=1)


def hm_dataset_manifest_digest() -> ContractDigest:
    payload = {
        "revision": RELBENCH_V1_REVISION,
        "assets": [
            {"path": asset.path, "sha256": asset.sha256, "byte_count": asset.byte_count}
            for asset in REL_HM_ASSETS
            if "/db/" in asset.path
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def trait_query_digest() -> ContractDigest:
    encoded = f"{TRAIT_QUERY_VERSION}\n{TRAIT_QUERY}".encode()
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _agent_key(customer_id: str, seed: int) -> str:
    digest = hashlib.sha256(f"{RELBENCH_V1_REVISION}:{seed}:{customer_id}".encode()).hexdigest()
    return f"agent-{digest[:24]}"


def _band(tile: int | None) -> str:
    if tile is None:
        return "unknown"
    return {1: "low", 2: "medium", 3: "high"}.get(tile, "unknown")


def _clean(value: object) -> str:
    text = str(value or "unknown").strip().lower().replace(" ", "_")
    return text[:100] or "unknown"


def derive_hm_population(
    dataset: HMDatasetFiles,
    *,
    cutoff: date,
    seed: int,
    target_agents: int,
) -> SimulationPopulationPackage:
    """Derive deterministic personas without retaining customer identifiers."""

    if target_agents <= 0:
        raise ValueError("target_agents must be positive")
    paths = dataset.validated_paths()
    connection = duckdb.connect()
    try:
        for table, path in paths.items():
            escaped = str(path).replace("'", "''")
            connection.execute(f"CREATE VIEW {table} AS SELECT * FROM read_parquet('{escaped}')")
        rows = connection.execute(TRAIT_QUERY, [cutoff, seed, target_agents, seed]).fetchall()
        columns = [item[0] for item in connection.description]
    finally:
        connection.close()
    if len(rows) != target_agents:
        raise ValueError("eligible H&M population is smaller than the reviewed sample")

    personas: list[SimulationPersona] = []
    for row in rows:
        record = dict(zip(columns, row, strict=True))
        age = record["age"]
        age_band = (
            "unknown"
            if age is None
            else "under_25"
            if age < 25
            else "25_34"
            if age < 35
            else "35_44"
            if age < 45
            else "45_54"
            if age < 55
            else "55_plus"
        )
        tenure_days = (cutoff - record["first_transaction"]).days
        recency_days = (cutoff - record["last_transaction"]).days
        traits = {
            TraitName.AGE_BAND: age_band,
            TraitName.CLUB_MEMBER_STATUS: _clean(record["club_member_status"]),
            TraitName.FASHION_NEWS_FREQUENCY: _clean(record["fashion_news_frequency"]),
            TraitName.TENURE_BAND: "new"
            if tenure_days <= 90
            else "established"
            if tenure_days <= 365
            else "long_term",
            TraitName.FREQUENCY_BAND: _band(record["frequency_tile"]),
            TraitName.RECENCY_BAND: "recent"
            if recency_days <= 14
            else "lapsed"
            if recency_days <= 56
            else "dormant",
            TraitName.BASKET_VALUE_BAND: _band(record["basket_tile"]),
            TraitName.PRIMARY_CATEGORY: _clean(record["primary_category"]),
            TraitName.INDEX_GROUP: _clean(record["index_group"]),
            TraitName.CHANNEL_MIX: "online"
            if record["online_share"] >= 0.8
            else "store"
            if record["online_share"] <= 0.2
            else "mixed",
            TraitName.MARKDOWN_SHARE_BAND: "unknown"
            if record["markdown_share"] is None
            else _band(record["markdown_tile"]),
        }
        personas.append(
            SimulationPersona(
                agent_key=_agent_key(record["customer_id"], seed),
                traits=tuple(AgentTrait(name=name, value=traits[name]) for name in TraitName),
            )
        )
    return SimulationPopulationPackage(
        dataset_revision=dataset.revision,
        dataset_manifest_digest=hm_dataset_manifest_digest(),
        trait_query_digest=trait_query_digest(),
        cutoff=cutoff,
        seed=seed,
        personas=tuple(personas),
    )
