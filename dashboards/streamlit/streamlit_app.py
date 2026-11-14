"""Chronic Health growth dashboard: Streamlit in Snowflake.

Runs INSIDE Snowflake as an app owned by the REPORTER role, so it reads the dbt marts
with no credentials at all and can't see anything REPORTER can't (RAW, dev schemas).
Every number comes from ANALYTICS.MARTS.current_kpis / weekly_kpis: the metric logic
lives in dbt, and this file only draws it. The jacksoncurtis.me page reads the same
two tables (via the reverse ETL export), so the two can't disagree.

Deploy:  uv run python -m dashboards.deploy_streamlit
Local:   uv run streamlit run dashboards/streamlit/streamlit_app.py   (uses .env key)
"""

import altair as alt
import pandas as pd
import streamlit as st

MARTS = "ANALYTICS.MARTS"
BLUE, ORANGE = "#2a78d6", "#eb6834"  # categorical slots 1 and 2

st.set_page_config(page_title="Chronic Health growth", page_icon="📈", layout="wide")


@st.cache_data(ttl=3600)  # marts change once a night; don't wake the warehouse on every click
def run(sql: str) -> pd.DataFrame:
    try:
        from snowflake.snowpark.context import get_active_session

        df = get_active_session().sql(sql).to_pandas()
    except Exception:  # not inside Snowflake: local development
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from warehouse.sf import connect

        with connect(role="REPORTER", warehouse="REPORTING_WH") as conn:
            cur = conn.cursor().execute(sql)
            df = pd.DataFrame(cur.fetchall(), columns=[d[0] for d in cur.description])
    df.columns = [c.lower() for c in df.columns]
    return df


def weekly_bars(df: pd.DataFrame, col: str, title: str, color: str = BLUE) -> alt.Chart:
    data = df[["week_start", col]].dropna()
    return (
        alt.Chart(data, title=title)
        .mark_bar(color=color, cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("week_start:T", title=None, axis=alt.Axis(format="%b %d", grid=False)),
            y=alt.Y(f"{col}:Q", title=None),
            tooltip=[alt.Tooltip("week_start:T", title="Week of", format="%b %d, %Y"),
                     alt.Tooltip(f"{col}:Q", title=title, format=",.0f")],
        )
        .properties(height=240)
    )


now = run(f"select * from {MARTS}.current_kpis").iloc[0]
weekly = run(f"select * from {MARTS}.weekly_kpis order by week_start")
weekly["week_start"] = pd.to_datetime(weekly["week_start"])

st.title("Chronic Health: growth")
st.caption(
    f"Downloads through {now.downloads_as_of:%b %d, %Y} · ratings & reviews as of "
    f"{now.ratings_as_of:%b %d} · weekly charts show complete Mon–Sun weeks only · "
    f"source: dbt marts `current_kpis`, `weekly_kpis`"
)

# ---- Headline numbers ---------------------------------------------------------------
last = weekly.dropna(subset=["first_time_downloads"]).iloc[-1]
c1, c2, c3 = st.columns([2, 1, 1])
c1.metric("Total downloads", f"{int(now.total_first_time_downloads):,}",
          f"+{int(last.first_time_downloads)} week of {last.week_start:%b %d}",
          help="First-time downloads since launch (App Store Sales report).")
c2.metric("Ratings", f"{int(now.ratings_count)}", f"{float(now.average_rating):.2f} ★ average",
          delta_color="off", help="Star ratings across every storefront.")
c3.metric("Reviews", f"{int(now.reviews_count)}",
          help="Written reviews (title + text). Every review is also a rating.")

# ---- Weekly trends --------------------------------------------------------------------
st.subheader("Weekly")
left, right = st.columns(2)
left.altair_chart(weekly_bars(weekly, "first_time_downloads", "First-time downloads"), use_container_width=True)
right.altair_chart(weekly_bars(weekly, "app_store_search_impressions", "App Store search impressions"),
                   use_container_width=True)

left, right = st.columns(2)
left.altair_chart(weekly_bars(weekly, "app_store_product_page_views", "App Store product page views"),
                  use_container_width=True)

sites = weekly.melt(id_vars="week_start",
                    value_vars=["site_visits_jacksoncurtis_me", "site_visits_chronichealth"],
                    var_name="site", value_name="visits").dropna()
sites["site"] = sites["site"].map({"site_visits_jacksoncurtis_me": "jacksoncurtis.me",
                                   "site_visits_chronichealth": "chronichealth.jacksoncurtis.me"})
right.altair_chart(
    alt.Chart(sites, title="Website visits")
    # Lines, not grouped bars: grouped bars need xOffset (Altair 5), and Snowflake's
    # warehouse runtime ships Altair 4.
    .mark_line(point=alt.OverlayMarkDef(size=64), strokeWidth=2)
    .encode(
        x=alt.X("week_start:T", title=None, axis=alt.Axis(format="%b %d", grid=False)),
        y=alt.Y("visits:Q", title=None),
        color=alt.Color("site:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=["jacksoncurtis.me", "chronichealth.jacksoncurtis.me"],
                                        range=[BLUE, ORANGE])),
        tooltip=[alt.Tooltip("week_start:T", title="Week of", format="%b %d, %Y"), "site:N",
                 alt.Tooltip("visits:Q", format=",.0f")],
    )
    .properties(height=240),
    use_container_width=True,
)
if weekly["site_visits_chronichealth"].isna().all():
    right.caption("chronichealth.jacksoncurtis.me: tracking just started; first full week pending.")

with st.expander("Definitions"):
    st.markdown(
        "- **Visits** (not unique visitors): Cloudflare Web Analytics sets no cookies, so it "
        "can't recognize a returning person. A visit is a page load that came from another "
        "site or was typed in. Weeks with older days may be Cloudflare estimates (sampled).\n"
        "- **Search impressions**: times the app appeared in App Store search results.\n"
        "- **Product page views**: App Store product page views from every source."
    )
    st.dataframe(weekly, hide_index=True)
