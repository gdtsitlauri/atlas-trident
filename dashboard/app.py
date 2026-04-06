from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="ATLAS Dashboard", page_icon="AT", layout="wide")
st.title("ATLAS - Agentic Twin Ledger for Autonomous Systems")
st.caption("TRIDENT governance analytics, twin state visibility, and experiment observability")

default_logs = st.sidebar.text_input("Logs directory", value=os.getenv("ATLAS_LOGS_DIR", "logs/latest"))
logs_dir = Path(default_logs)
refresh = st.sidebar.button("Refresh")

if refresh:
    st.rerun()

metrics_file = logs_dir / "metrics.csv"
state_file = logs_dir / "state_latest.json"
ledger_file = logs_dir / "atlas_ledger.db"
summary_file = logs_dir / "summary.json"
run_metadata_file = logs_dir / "run_metadata.json"

if run_metadata_file.exists():
    run_metadata = json.loads(run_metadata_file.read_text(encoding="utf-8"))
    st.sidebar.markdown("### Run Context")
    st.sidebar.write(f"Baseline: {run_metadata.get('baseline_mode', 'n/a')}")
    st.sidebar.write(f"Seed: {run_metadata.get('seed', 'n/a')}")
    st.sidebar.write(f"Deterministic: {run_metadata.get('deterministic_mode', 'n/a')}")

if summary_file.exists():
    summary = json.loads(summary_file.read_text(encoding="utf-8"))
    left, center, right = st.columns(3)
    left.metric("Scenario", summary.get("scenario", "n/a"))
    center.metric("Cycles", summary.get("cycles", 0))
    right.metric("Action Success", f"{summary.get('action_success_rate', 0.0):.2%}")

if metrics_file.exists():
    metrics_df = pd.read_csv(metrics_file)
    if not metrics_df.empty:
        st.subheader("Core Evaluation Metrics")
        row1 = st.columns(4)
        row1[0].metric("Decision Latency (ms)", f"{metrics_df['decision_latency_ms'].iloc[-1]:.2f}")
        row1[1].metric("Consensus Latency (ms)", f"{metrics_df['consensus_latency_ms'].iloc[-1]:.2f}")
        row1[2].metric("Latest SLA Violations", int(metrics_df["sla_violations"].iloc[-1]))
        row1[3].metric("Recovery Time (ms)", f"{metrics_df['recovery_time_ms'].iloc[-1]:.1f}")

        st.line_chart(
            metrics_df.set_index("step")[["avg_latency_ms", "resource_utilization", "utility"]],
            use_container_width=True,
        )
        st.line_chart(
            metrics_df.set_index("step")[["decision_latency_ms", "consensus_latency_ms"]],
            use_container_width=True,
        )
        st.dataframe(metrics_df.tail(20), use_container_width=True)
else:
    st.warning("No metrics.csv found yet. Run an experiment or API cycle first.")

if state_file.exists():
    state = json.loads(state_file.read_text(encoding="utf-8"))
    st.subheader("Twin State Snapshot")

    col_nodes, col_services = st.columns(2)
    node_df = pd.DataFrame.from_dict(state.get("nodes", {}), orient="index")
    service_df = pd.DataFrame.from_dict(state.get("services", {}), orient="index")
    col_nodes.dataframe(node_df, use_container_width=True)
    col_services.dataframe(service_df, use_container_width=True)

    trust_scores = state.get("trust_scores", {})
    if trust_scores:
        trust_df = pd.DataFrame(
            [{"agent": agent, "trust": score} for agent, score in trust_scores.items()]
        )
        st.subheader("Trust Score Evolution (Latest)")
        st.bar_chart(trust_df.set_index("agent"), use_container_width=True)

if ledger_file.exists():
    st.subheader("Governance Chain")
    conn = sqlite3.connect(ledger_file)
    try:
        proposals = pd.read_sql_query(
            "SELECT proposal_id, agent_id, governance_id, composite_score, status, created_at FROM proposals ORDER BY created_at DESC LIMIT 30",
            conn,
        )
        decisions = pd.read_sql_query(
            "SELECT proposal_id, approved, quorum_required, yes_votes, total_votes, consensus_latency_ms, decided_at FROM decisions ORDER BY decided_at DESC LIMIT 30",
            conn,
        )
        executions = pd.read_sql_query(
            "SELECT proposal_id, success, reward, decision_latency_ms, executed_at FROM executions ORDER BY executed_at DESC LIMIT 30",
            conn,
        )

        tab1, tab2, tab3 = st.tabs(["Proposals", "Decisions", "Executions"])
        tab1.dataframe(proposals, use_container_width=True)
        tab2.dataframe(decisions, use_container_width=True)
        tab3.dataframe(executions, use_container_width=True)
    finally:
        conn.close()
