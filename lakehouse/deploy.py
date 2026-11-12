"""Deploy the Databricks side of DataStack (idempotent: re-run after any change).

    uv run python -m lakehouse.deploy            # sync connection, notebook, job (+ dashboard)
    uv run python -m lakehouse.deploy --run      # ...and run the forecast job now, waiting for it

1. Lakehouse Federation: UC connection `snowflake_datastack` (as DATABRICKS_SVC, REPORTER role,
   key-pair) + foreign catalog `snowflake_analytics` = Snowflake's ANALYTICS database.
2. Notebook `lakehouse/forecast_downloads.py` → /Users/<me>/datastack/forecast_downloads.
3. Job `datastack-forecast`: serverless, nightly 15:00 UTC (the GitHub Actions dbt build
   that refreshes the marts runs ~14:17-14:21 UTC).
4. AI/BI dashboard from `lakehouse/dashboard.lvdash.json`.

Needs DATABRICKS_HOST / DATABRICKS_TOKEN in .env and ~/.snowflake/databricks_svc_key.p8.
"""

import base64
import os
import sys
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace
from databricks.sdk.service.catalog import ConnectionType
from databricks.sdk.service.dashboards import Dashboard
from dotenv import load_dotenv

HERE = Path(__file__).parent
CONNECTION = "snowflake_datastack"
FOREIGN_CATALOG = "snowflake_analytics"
JOB_NAME = "datastack-forecast"
DASHBOARD_NAME = "Chronic Health Download Forecast"


def sql(w: WorkspaceClient, warehouse_id: str, statement: str):
    r = w.statement_execution.execute_statement(warehouse_id=warehouse_id, statement=statement, wait_timeout="50s")
    while r.status.state.value in ("PENDING", "RUNNING"):
        time.sleep(3)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.error:
        raise RuntimeError(f"{statement[:80]}: {r.status.error.message}")
    return r.result.data_array if r.result else None


def sync_federation(w: WorkspaceClient, warehouse_id: str) -> None:
    pem = (Path.home() / ".snowflake/databricks_svc_key.p8").read_text()
    # Databricks wants the base64 body only; with the BEGIN/END lines it says "invalid PEM".
    options = {
        "host": f"{os.environ['SNOWFLAKE_ACCOUNT']}.snowflakecomputing.com",
        "port": "443",
        "sfWarehouse": "REPORTING_WH",
        "user": "DATABRICKS_SVC",
        "pem_private_key": "".join(l for l in pem.splitlines() if "-----" not in l),
    }
    if any(c.name == CONNECTION for c in w.connections.list()):
        w.connections.update(name=CONNECTION, options=options)
    else:
        w.connections.create(name=CONNECTION, connection_type=ConnectionType.SNOWFLAKE, options=options,
                             comment="Snowflake ANALYTICS via DATABRICKS_SVC (REPORTER role, read-only)")
    sql(w, warehouse_id, f"CREATE FOREIGN CATALOG IF NOT EXISTS {FOREIGN_CATALOG} "
                         f"USING CONNECTION {CONNECTION} OPTIONS (database 'ANALYTICS')")
    print(f"federation: {CONNECTION} → {FOREIGN_CATALOG}")


def sync_notebook(w: WorkspaceClient, folder: str) -> str:
    w.workspace.mkdirs(folder)
    path = f"{folder}/forecast_downloads"
    w.workspace.import_(path=path, format=workspace.ImportFormat.SOURCE, language=workspace.Language.PYTHON,
                        overwrite=True,
                        content=base64.b64encode((HERE / "forecast_downloads.py").read_bytes()).decode())
    print(f"notebook: {path}")
    return path


def sync_job(w: WorkspaceClient, notebook_path: str, email: str) -> int:
    settings = dict(
        name=JOB_NAME,
        tasks=[jobs.Task(task_key="forecast", notebook_task=jobs.NotebookTask(notebook_path=notebook_path))],
        schedule=jobs.CronSchedule(quartz_cron_expression="0 0 15 * * ?", timezone_id="UTC"),
        email_notifications=jobs.JobEmailNotifications(on_failure=[email]),
        max_concurrent_runs=1,
    )
    existing = next(iter(w.jobs.list(name=JOB_NAME)), None)
    if existing:
        w.jobs.reset(job_id=existing.job_id, new_settings=jobs.JobSettings(**settings))
        job_id = existing.job_id
    else:
        job_id = w.jobs.create(**settings).job_id
    print(f"job: {JOB_NAME} ({job_id}), nightly 15:00 UTC")
    return job_id


def sync_dashboard(w: WorkspaceClient, folder: str, warehouse_id: str) -> None:
    spec = HERE / "dashboard.lvdash.json"
    if not spec.exists():
        return
    body = Dashboard(display_name=DASHBOARD_NAME, parent_path=folder, warehouse_id=warehouse_id,
                     serialized_dashboard=spec.read_text())
    existing = next((d for d in w.lakeview.list() if d.display_name == DASHBOARD_NAME), None)
    if existing:
        d = w.lakeview.update(dashboard_id=existing.dashboard_id, dashboard=body)
    else:
        d = w.lakeview.create(dashboard=body)
    w.lakeview.publish(dashboard_id=d.dashboard_id, warehouse_id=warehouse_id, embed_credentials=True)
    print(f"dashboard: {w.config.host}/dashboardsv3/{d.dashboard_id}/published")


def main() -> None:
    load_dotenv(".env")
    w = WorkspaceClient()
    me = w.current_user.me().user_name
    warehouse_id = next(iter(w.warehouses.list())).id
    folder = f"/Users/{me}/datastack"

    sync_federation(w, warehouse_id)
    job_id = sync_job(w, sync_notebook(w, folder), me)
    if "--run" in sys.argv:
        print("running job (first run installs Prophet, ~3-5 min)...")
        run = w.jobs.run_now_and_wait(job_id=job_id)
        print(f"run {run.state.result_state}: {run.run_page_url}")
    sync_dashboard(w, folder, warehouse_id)


if __name__ == "__main__":
    main()
