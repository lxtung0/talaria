"""The care finder's IO: SQL warehouse, Vector Search and model serving (ticket #28).

Authenticates with the Databricks SDK default credentials, so the same code runs
from a laptop (`DEFAULT` profile) and inside the Databricks App (its service principal).
Each method is one small call; `recommend` holds the logic.
"""

import json
import os
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementParameterListItem, StatementState

from config import APP, APP_CHAT_MODEL, APP_EMBEDDING_MODEL, APP_PINCODES, APP_SEARCH_PATH, APP_VS_INDEX, APP_WAREHOUSE_ID
from talaria.care_finder.location import Place

# The India bounding box: pincode directory offices outside it have broken coordinates.
_IN_INDIA = "lat BETWEEN 6 AND 38 AND lon BETWEEN 68 AND 98"
_PINCODES = f"""(SELECT pincode, district, statename,
    try_cast(latitude AS DOUBLE) AS lat, try_cast(longitude AS DOUBLE) AS lon FROM {APP_PINCODES})"""
CITY_MIN_SHARE = 0.1  # a city's state needs at least this share of its Facilities
LABELS_SCHEMA = "item_id STRING, service_query STRING, label STRING, reason STRING, labelled_at TIMESTAMP"
# A claim saying the Facility (or any part of it) is open around the clock, for the emergency rank.
OPEN_24_7 = r"(?i)(24\s*[/x×]\s*7|24\s*hours?|24\s*hrs?|round[- ]the[- ]clock)"


class DatabricksBackend:
    def __init__(self, client: WorkspaceClient | None = None, warehouse_id: str | None = None):
        self.w = client or WorkspaceClient()
        # Inside the App the warehouse comes from its resource; elsewhere from config.py.
        self.warehouse_id = warehouse_id or os.environ.get("DATABRICKS_WAREHOUSE_ID") or APP_WAREHOUSE_ID

    # --- SQL -------------------------------------------------------------

    def sql(self, statement: str, **params) -> list[dict]:
        """Rows as dicts, typed from the result manifest. Parameters are strings, bound as `:name`."""
        response = self.w.statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=statement,
            parameters=[StatementParameterListItem(name=k, value=None if v is None else str(v)) for k, v in params.items()],
            wait_timeout="30s",
        )
        while response.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(1)
            response = self.w.statement_execution.get_statement(response.statement_id)
        if response.status.state != StatementState.SUCCEEDED:
            raise RuntimeError(f"SQL failed: {response.status.error.message if response.status.error else response.status}")
        columns = [(c.name, c.type_name.value if c.type_name else "STRING") for c in response.manifest.schema.columns]
        rows = []
        chunk = response.result
        while chunk is not None:
            rows.extend(dict((name, _convert(v, t)) for (name, t), v in zip(columns, row)) for row in chunk.data_array or [])
            if chunk.next_chunk_index is None:
                break
            chunk = self.w.statement_execution.get_statement_result_chunk_n(response.statement_id, chunk.next_chunk_index)
        return rows

    # --- Location --------------------------------------------------------

    def pin_place(self, pin: str) -> Place | None:
        rows = self.sql(
            f"""SELECT median(lat) AS lat, median(lon) AS lon, first(district) AS district, first(statename) AS state
            FROM {_PINCODES} WHERE pincode = CAST(:pin AS BIGINT) AND {_IN_INDIA}""",
            pin=pin,
        )
        row = rows[0] if rows else None
        if not row or row["lat"] is None:
            return None
        return Place(f"PIN {pin} ({_title(row['district'])}, {_title(row['state'])})", "pin", row["lat"], row["lon"], row["state"])

    def district_places(self, name: str, state: str | None) -> list[Place]:
        rows = self.sql(
            f"""SELECT district, statename AS state, median(lat) AS lat, median(lon) AS lon FROM {_PINCODES}
            WHERE upper(district) = upper(:name) AND (:state IS NULL OR upper(statename) = upper(:state)) AND {_IN_INDIA}
            GROUP BY district, statename""",
            name=name,
            state=state,
        )
        return [Place(f"{_title(r['district'])}, {_title(r['state'])}", "district", r["lat"], r["lon"], r["state"]) for r in rows]

    def city_places(self, name: str, state: str | None) -> list[Place]:
        rows = self.sql(
            f"""SELECT first(address_city) AS city, address_state AS state, count(*) AS n,
                median(latitude) AS lat, median(longitude) AS lon FROM {APP['facilities']}
            WHERE upper(address_city) = upper(:name) AND (:state IS NULL OR upper(address_state) = upper(:state))
                AND latitude IS NOT NULL
                -- Only real state names: some address_state values are localities.
                AND upper(address_state) IN (SELECT DISTINCT upper(statename) FROM {APP_PINCODES})
            GROUP BY address_state""",
            name=name,
            state=state,
        )
        # A few Facilities with a mis-stated state shouldn't make a city ambiguous.
        total = sum(r["n"] for r in rows)
        return [
            Place(f"{r['city']}, {r['state']}", "city", r["lat"], r["lon"], r["state"])
            for r in rows
            if r["n"] >= CITY_MIN_SHARE * total
        ]

    # --- Search, labels, Facilities --------------------------------------

    def search_band(self, service: str, cells: list[str], num_results: int) -> list[dict]:
        if APP_SEARCH_PATH == "delta":
            return self._search_band_delta(service, cells, num_results)
        result = self.w.vector_search_indexes.query_index(
            index_name=APP_VS_INDEX,
            columns=["item_id", "unique_id", "item_type", "item_text", "h3_r5"],
            query_text=service,
            filters_json=json.dumps({"h3_r5": cells}),
            num_results=num_results,
        )
        names = [c.name for c in result.manifest.columns]
        return [
            {**dict(zip(names, row)), "similarity": float(row[names.index("score")])}
            for row in (result.result.data_array or [])
        ]

    def _search_band_delta(self, service: str, cells: list[str], num_results: int) -> list[dict]:
        """The fallback path (#27): cosine similarity against the `embedding` column, in SQL.

        The query is embedded in the same statement with `ai_query`, like the column was.
        """
        return self.sql(
            f"""WITH q AS (SELECT ai_query('{APP_EMBEDDING_MODEL}', :service) AS v),
            band AS (SELECT * FROM {APP['facility_items']}
                     WHERE array_contains(from_json(:cells, 'array<string>'), h3_r5) AND embedding IS NOT NULL),
            ranked AS (SELECT item_id, unique_id, item_type, item_text, h3_r5,
                aggregate(zip_with(band.embedding, q.v, (a, b) -> a * b), 0D, (acc, x) -> acc + x)
                / (sqrt(aggregate(band.embedding, 0D, (acc, x) -> acc + x * x)) * sqrt(aggregate(q.v, 0D, (acc, x) -> acc + x * x)))
                AS similarity
                FROM band CROSS JOIN q
                ORDER BY similarity DESC LIMIT {int(num_results)})
            -- Coordinates too, so the live search map can place each Facility as it is found.
            SELECT ranked.*, f.latitude, f.longitude FROM ranked JOIN {APP['facilities']} f USING (unique_id)
            ORDER BY similarity DESC""",
            service=service,
            cells=json.dumps(cells),
        )

    def chat(self, messages: list[dict]) -> str:
        body = {"messages": messages, "temperature": 0, "max_tokens": 4000, "response_format": {"type": "json_object"}}
        response = self.w.api_client.do("POST", f"/serving-endpoints/{APP_CHAT_MODEL}/invocations", body=body)
        return response["choices"][0]["message"]["content"]

    def cached_labels(self, service_key: str) -> dict[str, dict]:
        try:
            rows = self.sql(f"SELECT item_id, label, reason FROM {APP['item_labels']} WHERE service_query = :s", s=service_key)
        except RuntimeError as e:
            if "TABLE_OR_VIEW_NOT_FOUND" in str(e):
                return {}
            raise
        return {r["item_id"]: {"label": r["label"], "reason": r["reason"]} for r in rows}

    def save_labels(self, service_key: str, labels: dict[str, dict]) -> None:
        self.sql(f"CREATE TABLE IF NOT EXISTS {APP['item_labels']} ({LABELS_SCHEMA})")
        rows = [{"item_id": k, "label": v["label"], "reason": v["reason"]} for k, v in labels.items()]
        self.sql(
            f"""MERGE INTO {APP['item_labels']} t
            USING (SELECT r.item_id, :s AS service_query, r.label, r.reason, current_timestamp() AS labelled_at
                   FROM (SELECT explode(from_json(:rows, 'array<struct<item_id:string,label:string,reason:string>>')) AS r)) s
            ON t.item_id = s.item_id AND t.service_query = s.service_query
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *""",
            s=service_key,
            rows=json.dumps(rows),
        )

    def facilities(self, unique_ids: list[str]) -> list[dict]:
        """Each Facility's row plus `open_24_7_quote`: one of its claims that says 24/7, or null."""
        return self.sql(
            f"""SELECT f.*, o.open_24_7_quote
            FROM {APP['facilities']} f
            LEFT JOIN (SELECT unique_id, min_by(item_text, item_id) AS open_24_7_quote
                       FROM {APP['facility_items']}
                       WHERE array_contains(from_json(:ids, 'array<string>'), unique_id) AND item_text rlike :open_24_7
                       GROUP BY unique_id) o ON o.unique_id = f.unique_id
            WHERE array_contains(from_json(:ids, 'array<string>'), f.unique_id)""",
            ids=json.dumps(unique_ids),
            open_24_7=OPEN_24_7,
        )


def _convert(value, type_name: str):
    if value is None:
        return None
    if type_name == "BOOLEAN":
        return value == "true"
    if type_name in ("DOUBLE", "FLOAT", "DECIMAL"):
        return float(value)
    if type_name in ("INT", "LONG", "SHORT", "BYTE"):
        return int(value)
    if type_name in ("ARRAY", "MAP", "STRUCT"):
        return json.loads(value)
    return value


def _title(text: str | None) -> str:
    return (text or "").title()
