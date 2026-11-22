"""Give the care finder app's service principal exactly what it needs (ticket #30).

- app resources: the SQL warehouse (CAN_USE) and the two serving endpoints (CAN_QUERY)
- Unity Catalog grants: USE CATALOG / USE SCHEMA; SELECT on the app tables, the
  pincode directory and the Vector Search index; MODIFY on the label cache
- CAN_USE on the Vector Search endpoint
- CAN_EDIT on the MLflow experiment, when it exists (ticket #31)

Run from the repo root: uv run python scripts/app_permissions.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.apps import (
    App,
    AppResource,
    AppResourceServingEndpoint,
    AppResourceServingEndpointServingEndpointPermission,
    AppResourceSqlWarehouse,
    AppResourceSqlWarehouseSqlWarehousePermission,
)

from config import (
    APP,
    APP_CHAT_MODEL,
    APP_EMBEDDING_MODEL,
    APP_NAME,
    APP_PINCODES,
    APP_VS_ENDPOINT,
    APP_VS_INDEX,
    APP_WAREHOUSE_ID,
    OUTPUT_CATALOG,
    OUTPUT_SCHEMA,
)
from talaria.care_finder.backend import LABELS_SCHEMA, DatabricksBackend

EXPERIMENT = "/Shared/talaria-care-finder"

w = WorkspaceClient()
app = w.apps.get(APP_NAME)
principal = app.service_principal_client_id
print(f"{APP_NAME}: service principal {principal}")

resources = [
    AppResource(
        name="sql-warehouse",
        sql_warehouse=AppResourceSqlWarehouse(id=APP_WAREHOUSE_ID, permission=AppResourceSqlWarehouseSqlWarehousePermission.CAN_USE),
    ),
    AppResource(
        name="chat-model",
        serving_endpoint=AppResourceServingEndpoint(name=APP_CHAT_MODEL, permission=AppResourceServingEndpointServingEndpointPermission.CAN_QUERY),
    ),
    AppResource(
        name="embedding-model",
        serving_endpoint=AppResourceServingEndpoint(name=APP_EMBEDDING_MODEL, permission=AppResourceServingEndpointServingEndpointPermission.CAN_QUERY),
    ),
]
w.apps.update(APP_NAME, App(name=APP_NAME, description=app.description, resources=resources))
print("App resources: sql-warehouse (CAN_USE), chat-model and embedding-model (CAN_QUERY)")

backend = DatabricksBackend(w)
# The label cache must exist before it can be granted; the app never creates tables.
backend.sql(f"CREATE TABLE IF NOT EXISTS {APP['item_labels']} ({LABELS_SCHEMA})")
grants = [
    f"GRANT USE CATALOG ON CATALOG {OUTPUT_CATALOG} TO `{principal}`",
    f"GRANT USE SCHEMA ON SCHEMA {OUTPUT_CATALOG}.{OUTPUT_SCHEMA} TO `{principal}`",
    f"GRANT SELECT ON TABLE {APP['facilities']} TO `{principal}`",
    f"GRANT SELECT ON TABLE {APP['facility_items']} TO `{principal}`",
    f"GRANT SELECT ON TABLE {APP_PINCODES} TO `{principal}`",
    f"GRANT SELECT, MODIFY ON TABLE {APP['item_labels']} TO `{principal}`",
    f"GRANT SELECT ON TABLE {APP_VS_INDEX} TO `{principal}`",
]
for grant in grants:
    backend.sql(grant)
    print(grant)

endpoint = w.vector_search_endpoints.get_endpoint(APP_VS_ENDPOINT)
w.api_client.do(
    "PATCH",
    f"/api/2.0/permissions/vector-search-endpoints/{endpoint.id}",
    body={"access_control_list": [{"service_principal_name": principal, "permission_level": "CAN_USE"}]},
)
print(f"CAN_USE on Vector Search endpoint {APP_VS_ENDPOINT}")

try:
    experiment = w.experiments.get_by_name(EXPERIMENT).experiment
except Exception:
    experiment = None
if experiment:
    w.api_client.do(
        "PATCH",
        f"/api/2.0/permissions/experiments/{experiment.experiment_id}",
        body={"access_control_list": [{"service_principal_name": principal, "permission_level": "CAN_EDIT"}]},
    )
    print(f"CAN_EDIT on experiment {EXPERIMENT}")
