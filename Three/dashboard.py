"""Streamlit dashboard for the phase 3 router.

Run: ./venv/bin/python -m streamlit run dashboard.py
"""

import datetime
import os

import pandas as pd
import requests
import streamlit as st

API = os.environ.get("ROUTER_API", "http://localhost:8080")

st.set_page_config(page_title="LLM Router Dashboard", page_icon="🔀", layout="wide")


def fetch(path: str):
    try:
        resp = requests.get(f"{API}{path}", timeout=3)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return None


def require(*payloads) -> None:
    """Stop the page with a clear error when the backend is unreachable."""
    if any(p is None for p in payloads):
        st.error(
            f"Data unavailable: backend unreachable at {API}. "
            "Start it with `./venv/bin/python main.py` and refresh."
        )
        st.stop()


def pct(value, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%" if value is not None else "n/a"


def ms(value) -> str:
    return f"{value:.0f} ms" if value is not None else "n/a"


# -- sidebar -----------------------------------------------------------------

page = st.sidebar.radio(
    "Page", ["Overview", "Models", "Performance", "Users", "Costs", "Alerts", "Logs"]
)
status = fetch("/status")
if status:
    st.sidebar.success(
        f"Backend running, {status['router_mode']} mode, "
        f"{status['model_count']} models, up {status['uptime_seconds']}s"
    )
    adapters = status.get("adapters", {})
    for name, info in adapters.items():
        icon = "🟢" if info.get("healthy") else "🔴"
        st.sidebar.caption(f"{icon} {name}: {', '.join(info.get('models', []))}")
else:
    st.sidebar.error(f"Backend unreachable at {API}")
st.sidebar.button("Refresh")


# -- pages -------------------------------------------------------------------

if page == "Overview":
    st.title("Overview")
    analytics = fetch("/analytics")
    health = fetch("/health")
    require(analytics, health)
    c = st.columns(5)
    c[0].metric("Total requests", analytics["total_requests"])
    c[1].metric("Success rate", pct(analytics["success_rate"]))
    c[2].metric("Avg latency", ms(analytics["avg_latency_ms"]))
    c[3].metric("Total cost", f"${analytics['total_cost_usd']:.6f}")
    c[4].metric("Cache hit rate", pct(analytics["cache_hit_rate"]))
    st.caption(f"Overall health: {health['status']}")
    st.subheader("Requests, last 30 minutes")
    series = analytics["requests_per_minute"]
    if series:
        df = pd.DataFrame(series).set_index("minutes_ago").sort_index(ascending=False)
        st.line_chart(df, y="requests")
    else:
        st.info("No requests recorded yet. Call POST /route and refresh.")

elif page == "Models":
    st.title("Models")
    analytics = fetch("/analytics")
    require(analytics)
    by_model = analytics["by_model"]
    if not by_model:
        st.info("No requests recorded yet. Call POST /route and refresh.")
    else:
        df = pd.DataFrame(by_model).T
        df.index.name = "model"
        st.dataframe(df, use_container_width=True)
        st.subheader("Requests by model")
        st.bar_chart(df["requests"])

elif page == "Performance":
    st.title("Performance")
    quality = fetch("/quality/dashboard")
    analytics = fetch("/analytics")
    require(quality, analytics)
    c = st.columns(4)
    c[0].metric("Requests", quality["requests_total"])
    c[1].metric("Avg latency", ms(quality["avg_latency_ms"]))
    c[2].metric("P95 latency", ms(quality["p95_latency_ms"]))
    c[3].metric("Error rate", pct(quality["error_rate"]))
    st.subheader("Request volume, last 30 minutes")
    series = analytics["requests_per_minute"]
    if series:
        df = pd.DataFrame(series).set_index("minutes_ago").sort_index(ascending=False)
        st.line_chart(df, y="requests")
    else:
        st.info("No requests recorded yet.")

elif page == "Users":
    st.title("Users")
    analytics = fetch("/analytics")
    require(analytics)
    by_tier = analytics["by_tier"]
    if not by_tier:
        st.info("No requests recorded yet.")
    else:
        df = pd.DataFrame(by_tier).T
        df.index.name = "tier"
        st.dataframe(df, use_container_width=True)
        st.subheader("Requests by tier")
        st.bar_chart(df["requests"])
        st.subheader("Requests by query type")
        st.bar_chart(pd.Series(analytics["by_query_type"], name="requests"))

elif page == "Costs":
    st.title("Costs")
    analytics = fetch("/analytics")
    require(analytics)
    st.metric("Total cost", f"${analytics['total_cost_usd']:.6f}")
    by_model = analytics["by_model"]
    if by_model:
        df = pd.DataFrame(by_model).T
        df.index.name = "model"
        st.subheader("Cost by model")
        st.bar_chart(df["total_cost_usd"])
        st.dataframe(
            df[["requests", "total_cost_usd", "total_tokens", "cost_per_1k_tokens"]],
            use_container_width=True,
        )
    else:
        st.info("No requests recorded yet.")

elif page == "Alerts":
    st.title("Alerts")
    quality = fetch("/quality/dashboard")
    health = fetch("/health")
    require(quality, health)
    slo = quality["slo"]
    compliant = slo["compliant"]
    if compliant is None:
        st.info("SLO status: no traffic yet.")
    elif compliant:
        st.success(
            f"SLO compliant: error rate <= {slo['error_rate_target']:.0%}, "
            f"P95 <= {slo['p95_latency_target_ms']} ms"
        )
    else:
        st.error("SLO violated, see alerts below.")
    for alert in quality["alerts"]:
        (st.error if alert["severity"] == "critical" else st.warning)(alert["message"])
    if not quality["alerts"]:
        st.caption("No active alerts.")
    st.subheader("Hotspot models")
    if quality["hotspots"]:
        st.dataframe(pd.DataFrame(quality["hotspots"]), use_container_width=True)
    else:
        st.info("No traffic yet.")

elif page == "Logs":
    st.title("Logs")
    logs = fetch("/logs")
    require(logs)
    entries = logs["logs"]
    if entries:
        df = pd.DataFrame(entries)
        df["time"] = df["ts"].map(
            lambda t: datetime.datetime.fromtimestamp(t).strftime("%H:%M:%S")
        )
        st.dataframe(
            df[["time", "level", "message"]].iloc[::-1],
            use_container_width=True, height=420,
        )
    else:
        st.info("No log entries yet.")

    st.subheader("Submit feedback")
    with st.form("feedback"):
        query_id = st.text_input("Query ID")
        rating = st.slider("Rating", 1, 5, 4)
        comment = st.text_input("Comment (optional)")
        if st.form_submit_button("Send"):
            try:
                resp = requests.post(
                    f"{API}/feedback",
                    json={"query_id": query_id or "unknown", "rating": rating, "comment": comment},
                    timeout=3,
                )
                resp.raise_for_status()
                st.success(f"Feedback stored, total {resp.json()['feedback_count']}")
            except requests.RequestException:
                st.error(f"Could not submit: backend unreachable at {API}.")
