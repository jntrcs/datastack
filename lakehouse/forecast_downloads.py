# Databricks notebook source
# MAGIC %md
# MAGIC # Chronic Health — first-time download forecast (Prophet + MLflow)
# MAGIC
# MAGIC **Question:** where are daily downloads heading, and when does the app cross
# MAGIC **1,000** first-time downloads?
# MAGIC
# MAGIC - **Input:** `snowflake_analytics.marts.daily_kpis` (Lakehouse Federation: the dbt mart
# MAGIC   in Snowflake, read in place as `DATABRICKS_SVC` / REPORTER; no copy).
# MAGIC - **Output:** `workspace.forecasting.download_forecast` (Delta), one row per day, actuals
# MAGIC   + forecast + 80% interval, daily and cumulative. Every run is logged to MLflow.
# MAGIC
# MAGIC Deployed and scheduled by `lakehouse/deploy.py` in the repo; edit there, not here.

# COMMAND ----------

# MAGIC %pip install prophet==1.1.6 cmdstanpy==1.2.5 --quiet
# MAGIC # cmdstanpy 1.3 rejects the CmdStan bundled inside the prophet wheel ("missing makefile").

# COMMAND ----------

import datetime as dt

import mlflow
import numpy as np
import pandas as pd
from prophet import Prophet

SOURCE = "snowflake_analytics.marts.daily_kpis"
TARGET = "workspace.forecasting.download_forecast"
HORIZON_DAYS = 90
HOLDOUT_DAYS = 28
MILESTONE = 1000
INTERVAL = 0.80
# Model sqrt(downloads), then square back. Counts get noisier as they grow (Poisson-like:
# variance ≈ mean), but Prophet assumes one noise level for the whole series. On the raw
# scale the quiet summer drags that estimate down and the 80% band covered only 50% of
# the holdout days. sqrt is the standard variance-stabilizing transform for counts.
TRANSFORM = "sqrt"  # or "none" to compare

PARAMS = dict(
    growth="linear",
    weekly_seasonality=True,
    yearly_seasonality=False,  # < 1 year of history: can't estimate a yearly cycle
    daily_seasonality=False,  # daily grain
    changepoint_range=0.95,  # default 0.8 would freeze the trend before November's growth
    changepoint_prior_scale=0.05,  # default flexibility
    interval_width=INTERVAL,
    uncertainty_samples=1000,
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load
# MAGIC NULL `first_time_downloads` = Apple hasn't published that day yet (not zero). Drop those
# MAGIC so the model never learns a fake 0 at the end of the series.

# COMMAND ----------

df = (
    spark.table(SOURCE)
    .where("first_time_downloads is not null")
    .selectExpr("date as ds", "cast(first_time_downloads as double) as y")
    .orderBy("ds")
    .toPandas()
)
df["ds"] = pd.to_datetime(df["ds"])
last_actual = df["ds"].max()
print(f"{len(df)} days, {df['ds'].min():%Y-%m-%d} → {last_actual:%Y-%m-%d}, {int(df['y'].sum())} downloads")

# COMMAND ----------


def fit(train: pd.DataFrame) -> Prophet:
    m = Prophet(**PARAMS)
    m.fit(train.assign(y=np.sqrt(train["y"]) if TRANSFORM == "sqrt" else train["y"]))
    return m


def sample_paths(m: Prophet, future: pd.DataFrame) -> np.ndarray:
    """Simulated futures in downloads/day, shape (days, samples). Clip at 0 (no negative
    downloads) before squaring back, or a -2 on the sqrt scale would become +4."""
    s = np.clip(m.predictive_samples(future)["yhat"], 0, None)
    return s**2 if TRANSFORM == "sqrt" else s


def mae(a, b) -> float:
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(b))))


# COMMAND ----------

# MAGIC %md
# MAGIC ## Backtest: does Prophet beat a naive guess?
# MAGIC Hold out the last 28 days, train on the rest, compare against the **naive baseline**
# MAGIC "every future day = the average of the previous 28 days". A model that can't beat that
# MAGIC isn't earning its complexity. MAE (downloads/day), not MAPE: days with 0 or 1 download
# MAGIC make percentage errors blow up.

# COMMAND ----------

cutoff = last_actual - pd.Timedelta(days=HOLDOUT_DAYS)
train, test = df[df["ds"] <= cutoff], df[df["ds"] > cutoff]

bt_paths = sample_paths(fit(train), test[["ds"]])
bt_pred = bt_paths.mean(axis=1)  # expected downloads per day
naive_pred = np.full(len(test), train["y"].tail(HOLDOUT_DAYS).mean())
lo_q, hi_q = (1 - INTERVAL) / 2 * 100, (1 + INTERVAL) / 2 * 100
in_interval = (test["y"].to_numpy() >= np.percentile(bt_paths, lo_q, axis=1)) & (
    test["y"].to_numpy() <= np.percentile(bt_paths, hi_q, axis=1)
)

metrics = {
    "holdout_mae": mae(test["y"], bt_pred),
    "holdout_mae_naive": mae(test["y"], naive_pred),
    "holdout_total_error": float(bt_pred.sum() - test["y"].sum()),  # + = over-forecast
    "holdout_interval_coverage": float(in_interval.mean()),  # want ≈ 0.80
}
metrics["holdout_skill_vs_naive"] = 1 - metrics["holdout_mae"] / metrics["holdout_mae_naive"]
print(metrics)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Fit on all history and forecast
# MAGIC **Cumulative bands come from sample paths, not from summing daily bands.** Adding up
# MAGIC each day's 10th percentile assumes every day is simultaneously unlucky, which gives
# MAGIC a band that's far too wide. Instead: draw 1,000 simulated futures, cumulative-sum each one,
# MAGIC then take percentiles across the 1,000 totals.

# COMMAND ----------

model = fit(df)
future = model.make_future_dataframe(periods=HORIZON_DAYS, include_history=False)
paths = sample_paths(model, future)
to_date = df["y"].sum()
cum_paths = to_date + np.cumsum(paths, axis=0)

forecast = pd.DataFrame(
    {
        "date": future["ds"].dt.date,
        "yhat": paths.mean(axis=1),
        "yhat_lower": np.percentile(paths, lo_q, axis=1),
        "yhat_upper": np.percentile(paths, hi_q, axis=1),
        "cumulative_yhat": np.percentile(cum_paths, 50, axis=1),
        "cumulative_lower": np.percentile(cum_paths, lo_q, axis=1),
        "cumulative_upper": np.percentile(cum_paths, hi_q, axis=1),
    }
)

# Milestone: in what share of simulated futures have we crossed 1,000 by each date?
first_cross = np.argmax(cum_paths >= MILESTONE, axis=0).astype(float)
first_cross[~(cum_paths >= MILESTONE).any(axis=0)] = np.nan
crossed = ~np.isnan(first_cross)


def cross_date(q):
    if crossed.mean() * 100 < q:
        return None  # fewer than q% of futures cross within the horizon
    return forecast["date"].iloc[int(np.nanpercentile(np.where(crossed, first_cross, np.inf), q))]


milestone = {
    "p_cross_within_horizon": float(crossed.mean()),
    "date_p10": cross_date(10),
    "date_p50": cross_date(50),
    "date_p90": cross_date(90),
}
print(milestone)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write the dashboard table (actuals + forecast, one row per day)

# COMMAND ----------

actuals = df.rename(columns={"ds": "date", "y": "actual"}).assign(date=lambda d: d["date"].dt.date)
actuals["cumulative_actual"] = actuals["actual"].cumsum()

with mlflow.start_run(run_name=f"prophet_downloads_{dt.date.today()}") as run:
    mlflow.log_params({**PARAMS, "transform": TRANSFORM, "horizon_days": HORIZON_DAYS, "holdout_days": HOLDOUT_DAYS,
                       "train_start": str(df["ds"].min().date()), "train_end": str(last_actual.date()),
                       "source": SOURCE})
    mlflow.log_metrics({**metrics, "downloads_to_date": float(to_date),
                        "p_cross_1000_within_horizon": milestone["p_cross_within_horizon"]})
    mlflow.set_tags({f"milestone_{k}": str(v) for k, v in milestone.items()})
    mlflow.prophet.log_model(model, name="model", input_example=future.head(3))
    run_id = run.info.run_id

out = pd.concat([actuals, forecast], ignore_index=True).sort_values("date")
out["is_forecast"] = out["actual"].isna()
out["milestone"] = MILESTONE
out["milestone_date_p10"] = milestone["date_p10"]
out["milestone_date_p50"] = milestone["date_p50"]
out["milestone_date_p90"] = milestone["date_p90"]
out["holdout_mae"] = metrics["holdout_mae"]
out["holdout_mae_naive"] = metrics["holdout_mae_naive"]
out["holdout_interval_coverage"] = metrics["holdout_interval_coverage"]
out["mlflow_run_id"] = run_id
out["generated_at"] = pd.Timestamp.now(tz="UTC")

spark.sql("CREATE SCHEMA IF NOT EXISTS workspace.forecasting")
(spark.createDataFrame(out).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(TARGET))
spark.sql(f"COMMENT ON TABLE {TARGET} IS 'Prophet forecast of Chronic Health first-time downloads "
          f"(actuals + {HORIZON_DAYS}d forecast, {int(INTERVAL*100)}% intervals). Built by "
          f"lakehouse/forecast_downloads.py from {SOURCE}. MLflow run {run_id}.'")
print(f"wrote {len(out)} rows to {TARGET}; MLflow run {run_id}")
