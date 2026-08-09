"""
LandSense Early Warning System - Modern Streamlit Dashboard
"""

from pathlib import Path
from datetime import datetime, timezone

import json

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st
from sklearn.cluster import DBSCAN
from sklearn.metrics import auc, roc_curve
from sklearn.preprocessing import label_binarize
from streamlit.components.v1 import html as components_html

from alert_system import (
    SensorReading,
    classify_alert_level,
    load_alert_history,
    process_reading,
)
from geofencing import find_zone_matches, highest_zone_risk, load_zones
from insar_processing import inverse_velocity_method, simulate_insar_stack
from route_planner import plan_safe_route

st.set_page_config(
    page_title="LandSense EWS",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = Path(__file__).parent
MODEL_DIR = BASE_DIR / "models"
DATA_PATH = BASE_DIR / "data" / "landslide_dataset.csv"

RISK_COLOR = {"Low": "#22c55e", "Medium": "#f59e0b", "High": "#ef4444"}
RISK_BG = {"Low": "rgba(34, 197, 94, 0.14)", "Medium": "rgba(245, 158, 11, 0.14)", "High": "rgba(239, 68, 68, 0.14)"}
RISK_TEXT = {
    "Low": {"status": "Stable", "recommendation": "Continue monitoring and keep routine patrols active.", "icon": "Stable"},
    "Medium": {"status": "Watch", "recommendation": "Review slope conditions and prepare response teams.", "icon": "Watch"},
    "High": {"status": "Critical", "recommendation": "Prioritize evacuation readiness and issue urgent alerts.", "icon": "Critical"},
}
LABEL_MAP = {0: "Low", 1: "Medium", 2: "High"}
FEATURES = [
    "deformation_mm",
    "velocity_mm_yr",
    "coherence",
    "rainfall_mm",
    "slope_deg",
    "soil_moisture_pct",
    "elevation_m",
    "aspect_deg",
    "ndvi",
]
TAB_NAMES = [
  "Public Safety",
  "Operations / Admin",
  "Research / Analytics",
]

MODE_HELP = {
  "Public Safety": "Live risk awareness, evacuation guidance, map-centric monitoring, and active alerts.",
  "Operations / Admin": "Sensor monitoring, geofence activity, route planning, rainfall, and alert pipeline control.",
  "Research / Analytics": "Feature importance, ROC-AUC, clustering, diagnostics, and technical analysis.",
}


@st.cache_resource
def load_models():
    rf = joblib.load(MODEL_DIR / "random_forest.pkl")
    xgb = joblib.load(MODEL_DIR / "xgboost.pkl")
    return rf, xgb


@st.cache_data
def load_dataset():
    return pd.read_csv(DATA_PATH)


@st.cache_data
def load_metrics():
    with open(MODEL_DIR / "metrics.json", encoding="utf-8") as f:
        return json.load(f)


@st.cache_data
def load_importance(model_name: str):
    return pd.read_csv(MODEL_DIR / f"{model_name}_feature_importance.csv")


@st.cache_data
def get_insar_stack():
    return simulate_insar_stack(n_pixels=100, n_dates=40)


def utc_now_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def normalize_risk_label(level: str) -> str:
    value = str(level or "Low").strip().title()
    return value if value in RISK_COLOR else "Low"


def risk_meta(level: str) -> dict:
    normalized = normalize_risk_label(level)
    theme = RISK_TEXT[normalized]
    return {
        "label": normalized,
        "color": RISK_COLOR[normalized],
        "bg": RISK_BG[normalized],
        "status": theme["status"],
        "recommendation": theme["recommendation"],
    }


def apply_chart_theme(ax):
    ax.set_facecolor("#0b1220")
    ax.grid(color="white", alpha=0.08, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#334155")
    ax.spines["bottom"].set_color("#334155")
    ax.tick_params(colors="#cbd5e1")
    ax.xaxis.label.set_color("#e2e8f0")
    ax.yaxis.label.set_color("#e2e8f0")
    ax.title.set_color("#f8fafc")


def render_styles():
    st.markdown(
        """
        <style>
          :root {
            --bg0: #050b14;
            --bg1: #07111d;
            --bg2: #0b1726;
            --panel: rgba(9, 16, 28, 0.72);
            --panel-strong: rgba(12, 22, 38, 0.88);
            --line: rgba(255, 255, 255, 0.08);
            --line-strong: rgba(255, 255, 255, 0.14);
            --text: #e5eefc;
            --muted: #97a7c0;
            --accent: #7dd3fc;
          }

          html, body, .stApp {
            background:
              radial-gradient(circle at top left, rgba(59, 130, 246, 0.16), transparent 26%),
              radial-gradient(circle at top right, rgba(34, 197, 94, 0.10), transparent 22%),
              linear-gradient(180deg, var(--bg0) 0%, var(--bg1) 40%, var(--bg2) 100%);
            color: var(--text);
          }

          .stApp header { background: transparent; }
          .main .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2.25rem;
            max-width: 1450px;
          }

          [data-testid="stSidebar"] {
            background: linear-gradient(180deg, rgba(6, 13, 24, 0.98), rgba(8, 16, 29, 0.94));
            border-right: 1px solid var(--line);
          }

          h1, h2, h3, h4, h5, h6 {
            letter-spacing: -0.03em;
            color: #f8fafc;
          }

          .hero-shell,
          .glass-card,
          .chart-shell,
          .panel-shell,
          .risk-card-modern,
          .map-shell {
            background: linear-gradient(180deg, rgba(15, 23, 42, 0.84), rgba(8, 15, 28, 0.82));
            border: 1px solid var(--line);
            border-radius: 24px;
            box-shadow: 0 24px 64px rgba(0, 0, 0, 0.28);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
          }

          .hero-shell {
            padding: 1.5rem;
            position: relative;
            overflow: hidden;
            animation: fadeUp 0.5s ease;
          }

          .hero-shell::before {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, rgba(96, 165, 250, 0.10), rgba(34, 197, 94, 0.05), transparent 72%);
            pointer-events: none;
          }

          .hero-title {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.04em;
            line-height: 1.04;
            margin: 0;
          }

          .hero-subtitle {
            color: var(--muted);
            margin-top: 0.35rem;
            font-size: 0.98rem;
          }

          .live-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.42rem 0.75rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--line);
            color: #d6e4ff;
            font-size: 0.8rem;
            letter-spacing: 0.02em;
          }

          .live-dot {
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #22c55e;
            box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.6);
            animation: pulse 2s infinite;
          }

          .risk-banner {
            border-radius: 22px;
            padding: 1.2rem 1.25rem;
            border: 1px solid var(--line-strong);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
            position: relative;
            overflow: hidden;
          }

          .risk-banner::after {
            content: "";
            position: absolute;
            inset: 0;
            background: linear-gradient(135deg, rgba(255,255,255,0.08), transparent 40%);
            pointer-events: none;
          }

          .risk-title {
            font-size: 1.8rem;
            font-weight: 800;
            margin: 0;
          }

          .risk-kicker {
            text-transform: uppercase;
            letter-spacing: 0.2em;
            font-size: 0.72rem;
            color: #a8b6d1;
            margin-bottom: 0.4rem;
          }

          .kpi-card {
            padding: 1rem 1rem 0.95rem;
            min-height: 112px;
            position: relative;
            overflow: hidden;
            transition: transform 180ms ease, border-color 180ms ease, box-shadow 180ms ease;
            animation: fadeUp 0.55s ease;
          }

          .kpi-card:hover,
          .glass-card:hover,
          .chart-shell:hover,
          .panel-shell:hover {
            transform: translateY(-2px);
            border-color: rgba(125, 211, 252, 0.24);
            box-shadow: 0 30px 70px rgba(0, 0, 0, 0.34);
          }

          .kpi-label {
            color: #9fb0c9;
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.14em;
          }

          .kpi-value {
            margin-top: 0.35rem;
            font-size: 1.85rem;
            font-weight: 800;
            line-height: 1.05;
          }

          .kpi-detail {
            margin-top: 0.45rem;
            color: #c9d8ee;
            font-size: 0.9rem;
          }

          .soft-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.35rem 0.72rem;
            border-radius: 999px;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--line);
            color: #d4def1;
            font-size: 0.82rem;
          }

          .section-title {
            margin: 0;
            font-size: 1.22rem;
            font-weight: 750;
          }

          .section-note {
            color: var(--muted);
            margin-top: 0.25rem;
            font-size: 0.92rem;
          }

          .chart-shell,
          .panel-shell,
          .map-shell {
            padding: 1rem;
          }

          .risk-card-modern {
            padding: 0.9rem 1rem;
            animation: fadeUp 0.45s ease;
          }

          .risk-card-modern .level {
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
          }

          .risk-card-modern .meta {
            color: #c7d6ea;
            font-size: 0.88rem;
          }

          div[data-testid="metric-container"] {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 14px 16px;
          }

          div[data-testid="stExpander"] details {
            border: 1px solid var(--line);
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.03);
            padding: 0.15rem 0.1rem;
          }

          div[data-testid="stTabs"] [data-baseweb="tab-list"] {
            gap: 0.45rem;
            border-bottom: 1px solid var(--line);
          }

          button[data-baseweb="tab"] {
            border-radius: 999px;
            padding: 0.55rem 0.95rem;
            background: rgba(255, 255, 255, 0.04);
            color: #cbd5e1;
            border: 1px solid transparent;
          }

          button[data-baseweb="tab"][aria-selected="true"] {
            background: linear-gradient(135deg, rgba(96, 165, 250, 0.25), rgba(34, 197, 94, 0.16));
            color: #ffffff;
            border-color: rgba(125, 211, 252, 0.18);
            box-shadow: 0 10px 24px rgba(59, 130, 246, 0.18);
          }

          .stButton > button,
          .stDownloadButton > button {
            background: linear-gradient(135deg, #1d4ed8 0%, #2563eb 45%, #0f766e 100%);
            color: white;
            border: 0;
            border-radius: 999px;
            padding: 0.75rem 1rem;
            font-weight: 700;
            box-shadow: 0 18px 38px rgba(37, 99, 235, 0.22);
            transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
          }

          .stButton > button:hover,
          .stDownloadButton > button:hover {
            transform: translateY(-1px);
            box-shadow: 0 24px 48px rgba(37, 99, 235, 0.30);
            filter: brightness(1.04);
          }

          .stSlider [data-baseweb="slider"] div[role="slider"] {
            box-shadow: 0 0 0 0 rgba(125, 211, 252, 0.48);
            animation: pulse 2s infinite;
          }

          @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.6); }
            70% { box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }
            100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
          }

          @keyframes fadeUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
          }

          @media (max-width: 900px) {
            .hero-title { font-size: 1.7rem; }
            .kpi-value { font-size: 1.5rem; }
            .main .block-container { padding-left: 0.9rem; padding-right: 0.9rem; }
          }
          
          /* Loading skeletons and subtle transitions */
          .skeleton {
            display: block;
            width: 100%;
            height: 12rem;
            border-radius: 12px;
            background: linear-gradient(90deg, rgba(255,255,255,0.02) 0%, rgba(255,255,255,0.04) 50%, rgba(255,255,255,0.02) 100%);
            background-size: 200% 100%;
            animation: shimmer 1.6s linear infinite;
          }

          @keyframes shimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
          }

          @media (max-width: 700px) {
            .chart-shell, .panel-shell, .map-shell, .hero-shell { border-radius: 16px; }
            .kpi-card { min-height: 96px; }
            .hero-title { font-size: 1.45rem; }
          }
          .gauge {
            --size: 96px;
            width: var(--size);
            height: var(--size);
            border-radius: 50%;
            display: inline-grid;
            place-items: center;
            background: conic-gradient(var(--g-color, #38bdf8) var(--g-pct, 40%), rgba(255,255,255,0.04) 0);
            box-shadow: 0 6px 18px rgba(2,6,23,0.6);
            border: 1px solid rgba(255,255,255,0.04);
            transition: background 700ms ease;
          }
          .gauge .inner {
            width: 68%;
            height: 68%;
            border-radius: 50%;
            background: rgba(11,17,34,0.9);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e6f0ff;
            font-weight: 800;
            font-size: 0.95rem;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.02);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def auto_refresh(enabled: bool, interval_seconds: int):
    if not enabled:
        return
    components_html(
        f"""
        <script>
          (function() {{
            const delay = {int(interval_seconds)} * 1000;
            setTimeout(function() {{
              window.parent.location.reload();
            }}, delay);
          }})();
        </script>
        """,
        height=0,
    )


def render_kpi_card(label: str, value: str, detail: str, accent: str):
    st.markdown(
        f"""
        <div class="glass-card kpi-card" style="border-top: 3px solid {accent};">
          <div class="kpi-label">{label}</div>
          <div class="kpi-value" style="color: {accent};">{value}</div>
          <div class="kpi-detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_section_header(title: str, note: str):
    st.markdown(
        f"""
        <div style="margin-bottom: 0.75rem;">
          <div class="section-title">{title}</div>
          <div class="section-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_risk_meter(level: str, size: int = 96):
    normalized = normalize_risk_label(level)
    pct = {"Low": 18, "Medium": 62, "High": 94}.get(normalized, 18)
    color = RISK_COLOR.get(normalized, "#38bdf8")
    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:0.8rem;">
          <div class="gauge" style="--size:{size}px; --g-pct:{pct}deg; --g-color:{color}; background: conic-gradient({color} {pct}%, rgba(255,255,255,0.04) 0);">
            <div class="inner">{pct}%</div>
          </div>
          <div style="line-height:1;">
            <div style="font-size:0.92rem; color:#cfe8ff; font-weight:700;">{normalized} risk</div>
            <div style="font-size:0.82rem; color:#9fb0c9; margin-top:0.18rem;">Severity indicator</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_alert_cards(alerts):
    if not alerts:
        st.info("No alerts recorded yet. Run a prediction to generate alerts.")
        return
    for alert in reversed(alerts[-5:]):
        level = normalize_risk_label(alert.get("risk_level", "Low"))
        theme = risk_meta(level)
        timestamp = str(alert.get("timestamp", ""))[:16]
        location = alert.get("location_name", "Unknown location")
        st.markdown(
            f"""
            <div class="risk-card-modern" style="border-left: 4px solid {theme['color']}; background: {theme['bg']};">
              <div class="level" style="color: {theme['color']};">{level}</div>
              <div class="meta" style="margin-top: 0.25rem;">{location}</div>
              <div class="meta" style="opacity: 0.85; margin-top: 0.2rem;">{timestamp}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def build_alert_timeline(summary: dict, alerts: list[dict], zones_geojson: dict[str, object], focus_point: pd.Series | None = None) -> list[dict]:
    timeline: list[dict] = []
    current_risk = summary["current_risk"]
    theme = risk_meta(current_risk)

    timeline.append(
        {
            "time": summary["last_updated"],
            "title": "Operational snapshot refreshed",
            "detail": f"Current risk is {current_risk}. {theme['recommendation']}",
            "accent": theme["color"],
        }
    )

    if summary["rainfall_mm"] >= 80:
      timeline.append(
        {
          "time": summary["last_updated"],
          "title": "Rainfall spike detected",
          "detail": f"Focus-zone rainfall is {summary['rainfall_mm']:.1f} mm.",
          "accent": "#38bdf8",
        }
      )

    if summary["deformation_mm"] >= 10:
      timeline.append(
        {
          "time": summary["last_updated"],
          "title": "Deformation increase observed",
          "detail": f"Ground deformation is {summary['deformation_mm']:.1f} mm with IVM estimate near {summary['estimated_failure_days']:.0f} days.",
          "accent": "#f97316",
        }
      )

    if focus_point is not None:
      matches = find_zone_matches(float(focus_point["latitude"]), float(focus_point["longitude"]), zones_geojson)
      if matches:
        zone_name = matches[0].name
        zone_level = highest_zone_risk(matches)
        timeline.append(
          {
            "time": summary["last_updated"],
            "title": "Geofence entry / zone match",
            "detail": f"Monitoring area intersects {zone_name} ({zone_level}).",
            "accent": RISK_COLOR.get(normalize_risk_label(zone_level), "#7dd3fc"),
          }
        )

    if alerts:
      recent = alerts[-1]
      recent_level = normalize_risk_label(recent.get("risk_level", current_risk))
      timeline.append(
        {
          "time": str(recent.get("timestamp", summary["last_updated"])),
          "title": "Alert triggered",
          "detail": f"{recent_level} alert for {recent.get('location_name', 'Unknown location')}.",
          "accent": RISK_COLOR.get(recent_level, "#ef4444"),
        }
      )
      if recent.get("sent_telegram") or recent.get("sent_whatsapp"):
        timeline.append(
          {
            "time": str(recent.get("timestamp", summary["last_updated"])),
            "title": "SMS / Telegram dispatched",
            "detail": "At least one notification channel acknowledged the alert.",
            "accent": "#22c55e",
          }
        )

    timeline.append(
      {
        "time": summary["last_updated"],
        "title": "Evacuation routing ready",
        "detail": "Safe route planning is available in the Operations / Admin view.",
        "accent": "#a855f7",
      }
    )
    return timeline


def render_timeline(timeline: list[dict]):
    if not timeline:
        st.info("No operational timeline events are available yet.")
        return

    for event in timeline:
        st.markdown(
            f"""
            <div class="risk-card-modern" style="border-left: 4px solid {event['accent']}; margin-bottom: 0.6rem;">
              <div class="level" style="color: {event['accent']};">{event['title']}</div>
              <div class="meta" style="margin-top: 0.25rem;">{event['detail']}</div>
              <div class="meta" style="opacity: 0.82; margin-top: 0.2rem;">{event['time']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_hero_dashboard(summary: dict, alerts: list[dict], df_pred: pd.DataFrame, zones_geojson: dict[str, object]):
    theme = risk_meta(summary["current_risk"])
    failure_probability = {"Low": 0.18, "Medium": 0.56, "High": 0.87}.get(summary["current_risk"], 0.18)

    focus_point = df_pred.nlargest(1, "confidence").iloc[0]
    if not pd.isna(focus_point["latitude"]) and not pd.isna(focus_point["longitude"]):
        route_end_source = df_pred[df_pred["risk_label"] == "Low"]
        if route_end_source.empty:
            route_end_source = df_pred.nsmallest(1, "confidence")
        route_end = route_end_source.iloc[0]
        route_info = plan_safe_route(
            float(focus_point["latitude"]),
            float(focus_point["longitude"]),
            float(route_end["latitude"]),
            float(route_end["longitude"]),
            zones_geojson,
        )
    else:
        route_info = {"path": [], "distance_km": None, "status": "no_path"}

    st.markdown(
        f"""
        <div class="hero-shell">
          <div class="live-pill"><span class="live-dot"></span> Public safety / operations / research modes active</div>
          <div style="position: relative; z-index: 1; margin-top: 1rem;">
          <div class="hero-title">LandSense Landslide Early Warning Console</div>
          <div class="hero-subtitle">Operational monitoring designed for public safety, emergency response, and geospatial analytics.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top_cols = st.columns([1.2, 0.95])
    with top_cols[0]:
        st.markdown(
            f"""
            <div class="risk-banner" style="margin-top: 0.85rem; background: {theme['bg']}; border: 1px solid {theme['color']};">
              <div class="risk-kicker">Hero risk section</div>
              <div class="risk-title" style="color: {theme['color']};">{summary['current_risk'].upper()} RISK</div>
              <div style="margin-top: 0.5rem; color: #d6e4ff; line-height: 1.55;">{theme['recommendation']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with top_cols[1]:
        route_distance = "N/A" if route_info["distance_km"] is None else f"{route_info['distance_km']:.3f} km"
        st.markdown(
            f"""
            <div class="glass-card" style="padding: 1rem; margin-top: 0.85rem; height: 100%;">
              <div class="risk-kicker">Route readiness</div>
              <div style="font-size: 1.1rem; font-weight: 800; margin-top: 0.2rem;">{route_info['status'].replace('_', ' ').title()}</div>
              <div style="margin-top: 0.6rem; color: #c9d8ee; line-height: 1.55;">
              Route distance: <b>{route_distance}</b><br>
              Alert severity: <b style="color: {theme['color']};">{summary['current_status']}</b><br>
              Failure probability: <b>{failure_probability:.0%}</b>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    hero_cols = st.columns(7)
    hero_cards = [
        ("Current Risk Level", summary["current_risk"], "Live monitoring status", theme["color"]),
        ("Failure Probability", f"{failure_probability:.0%}", "Derived operational urgency", "#38bdf8"),
        ("IVM Estimated Failure Time", f"{summary['estimated_failure_days']:.0f} days", "Inverse velocity forecast", "#f97316"),
        ("Rainfall Status", f"{summary['rainfall_mm']:.1f} mm", "Current focus-zone rainfall", "#0ea5e9"),
        ("Deformation Status", f"{summary['deformation_mm']:.1f} mm", "Current focus-zone deformation", "#a855f7"),
        ("Alert Severity", summary["current_status"], "Operational alert class", "#ef4444" if summary["current_risk"] == "High" else "#f59e0b"),
        ("Recommended Action", "Evacuate" if summary["current_risk"] == "High" else "Monitor", "Immediate response cue", "#22c55e" if summary["current_risk"] == "Low" else "#f59e0b"),
    ]
    for col, card in zip(hero_cols, hero_cards):
        with col:
            render_kpi_card(card[0], card[1], card[2], card[3])

    st.markdown("<div style='height: 0.45rem;'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.18, 0.82])
    with left:
        st.markdown('<div class="map-shell">', unsafe_allow_html=True)
        render_section_header("Map-centric operations", "Live map, danger zones, evacuation routes, and live user position support the operational view.")
        map_df = df_pred[["latitude", "longitude", "risk_code", "risk_label", "confidence"]].copy()
        map_df["color"] = map_df["risk_label"].map({"Low": [34, 197, 94, 150], "Medium": [245, 158, 11, 195], "High": [239, 68, 68, 235]})
        st.map(map_df[map_df["risk_label"] != "Low"].rename(columns={"latitude": "lat", "longitude": "lon"}), color="color")
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel-shell">', unsafe_allow_html=True)
        render_section_header("Alert timeline", "Chronological operational flow derived from the existing alert + logging architecture.")
        render_timeline(build_alert_timeline(summary, alerts, zones_geojson, focus_point=focus_point))
        st.markdown("</div>", unsafe_allow_html=True)


def render_public_safety_mode(summary, alerts, df_pred, zones_geojson):
    render_hero_dashboard(summary, alerts, df_pred, zones_geojson)
    st.markdown("<div style='height: 0.35rem;'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.1, 0.9])
    with left:
        st.markdown('<div class="chart-shell">', unsafe_allow_html=True)
        render_section_header("Live risk status", "Compact distribution view to keep the interface readable during public safety operations.")
        render_distribution_chart(df_pred)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel-shell">', unsafe_allow_html=True)
        render_section_header("Active alerts", "Recent notifications and field-facing context.")
        render_alert_cards(alerts)
        st.markdown("</div>", unsafe_allow_html=True)
    with st.expander("Evacuation guidance", expanded=True):
        theme = risk_meta(summary["current_risk"])
        st.markdown(
            f"""
            <div class="risk-banner" style="background: {theme['bg']}; border: 1px solid {theme['color']};">
              <div class="risk-kicker">Recommended response</div>
              <div style="color: #f8fafc; line-height: 1.6;">{theme['recommendation']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "- Maintain live monitoring on the Risk Map and Alert System tabs.\n"
            "- Prioritize low-lying evacuation routes when the risk level is High.\n"
            "- Share updates with field teams before escalation windows close."
        )


def render_operations_mode(summary, alerts, df_pred, rf_model, xgb_model, zones_geojson):
    render_section_header("Operations / Admin", MODE_HELP["Operations / Admin"])
    top = st.columns(4)
    stats = [
        ("Current risk", summary["current_risk"], f"{summary['current_status']} status", RISK_COLOR[summary["current_risk"]]),
        ("Active alerts", str(summary["active_alerts"]), "Recent system triggers", "#7dd3fc"),
        ("Last refresh", summary["last_updated"], "UTC timestamp", "#c084fc"),
        ("Region focus", summary["region_status"], "Operational outlook", "#38bdf8"),
    ]
    for col, stat in zip(top, stats):
        with col:
            render_kpi_card(stat[0], stat[1], stat[2], stat[3])

    left, right = st.columns([1.08, 0.92])
    with left:
        st.markdown('<div class="chart-shell">', unsafe_allow_html=True)
        render_section_header("Live monitoring", "Sensor summaries plus alert status without overwhelming the operator.")
        st.metric("Rainfall", f"{summary['rainfall_mm']:.1f} mm")
        st.metric("Ground deformation", f"{summary['deformation_mm']:.1f} mm")
        st.metric("Velocity", f"{summary['velocity_mm_yr']:.1f} mm/yr")
        st.metric("Estimated failure days", f"{summary['estimated_failure_days']:.0f}")
        render_alert_cards(alerts)
        st.markdown("</div>", unsafe_allow_html=True)
    with right:
        st.markdown('<div class="panel-shell">', unsafe_allow_html=True)
        render_section_header("Route planning + geofence activity", "Safe routing, zone awareness, and alert pipeline control remain available in one place.")
        focus_point = df_pred.nlargest(1, "confidence").iloc[0]
        low_target = df_pred[df_pred["risk_label"] == "Low"]
        if low_target.empty:
            low_target = df_pred.nsmallest(1, "confidence")
        route = plan_safe_route(
            float(focus_point["latitude"]),
            float(focus_point["longitude"]),
            float(low_target.iloc[0]["latitude"]),
            float(low_target.iloc[0]["longitude"]),
            zones_geojson,
        )
        st.metric("Safe route status", route["status"])
        st.metric("Safe route distance", "N/A" if route["distance_km"] is None else f"{route['distance_km']:.3f} km")
        st.caption("Use the alert system below for controlled trigger simulation and notification dispatch.")
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Alert pipeline control", expanded=False):
        render_alert_system(rf_model, xgb_model)


def render_research_mode(df_pred, metrics, ensemble_proba):
    render_section_header("Research / Analytics", MODE_HELP["Research / Analytics"])
    cols = st.columns(4)
    rf = metrics["random_forest"]
    xgb = metrics["xgboost"]
    cards = [
        ("RF accuracy", f"{rf['accuracy']:.3f}", "Random Forest", RISK_COLOR["Low"]),
        ("RF ROC-AUC", f"{rf['roc_auc']:.3f}", "Random Forest", "#38bdf8"),
        ("XGB accuracy", f"{xgb['accuracy']:.3f}", "XGBoost", RISK_COLOR["Medium"]),
        ("XGB ROC-AUC", f"{xgb['roc_auc']:.3f}", "XGBoost", RISK_COLOR["High"]),
    ]
    for col, card in zip(cols, cards):
        with col:
            render_kpi_card(card[0], card[1], card[2], card[3])

    with st.expander("Technical model diagnostics", expanded=True):
        render_ml_insights(df_pred, metrics, ensemble_proba)
    with st.expander("Spatial and statistical analytics", expanded=False):
        render_advanced_analytics(df_pred, metrics, ensemble_proba)


def render_distribution_chart(df_pred):
    counts = df_pred["risk_label"].value_counts().reindex(["Low", "Medium", "High"], fill_value=0)
    colors = [RISK_COLOR[label] for label in ["Low", "Medium", "High"]]
    with st.spinner("Rendering risk distribution..."):
        fig, ax = plt.subplots(figsize=(8.2, 3.8))
        bars = ax.barh(counts.index, counts.values, color=colors, height=0.54, edgecolor="none")
        max_count = max(int(counts.max()), 1)
        for bar, count in zip(bars, counts.values):
            ax.text(bar.get_width() + max_count * 0.02 + 1, bar.get_y() + bar.get_height() / 2, f"{int(count):,}", va="center", fontsize=10, color="#e2e8f0", fontweight="bold")
        ax.set_xlabel("Pixel count")
        ax.set_title("Risk distribution across the study area", fontweight="bold")
        apply_chart_theme(ax)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)


def render_live_monitoring(summary, alerts):
    render_section_header("Live Monitoring", "A compact operational dashboard with current system condition, alert activity, and live readiness.")
    top = st.columns(4)
    stats = [
        ("Current risk", summary["current_risk"], f"{summary['current_status']} status", RISK_COLOR[summary["current_risk"]]),
        ("Active alerts", str(summary["active_alerts"]), "Recent system triggers", "#7dd3fc"),
        ("Last refresh", summary["last_updated"], "UTC timestamp", "#c084fc"),
        ("Region focus", summary["region_status"], "Operational outlook", "#38bdf8"),
    ]
    for col, stat in zip(top, stats):
        with col:
            render_kpi_card(stat[0], stat[1], stat[2], stat[3])

    st.markdown("<div style='height: 0.4rem;'></div>", unsafe_allow_html=True)
    col_a, col_b = st.columns([1.2, 0.9])
    with col_a:
        st.markdown('<div class="chart-shell">', unsafe_allow_html=True)
        render_section_header("Status feed", "Recent alerts and operational context.")
        render_alert_cards(alerts)
        st.markdown("</div>", unsafe_allow_html=True)
    with col_b:
        st.markdown('<div class="panel-shell">', unsafe_allow_html=True)
        render_section_header("Readiness indicators", "High-level summary without the technical clutter.")
        theme = risk_meta(summary["current_risk"])
        st.metric("Rainfall", f"{summary['rainfall_mm']:.1f} mm")
        st.metric("Ground deformation", f"{summary['deformation_mm']:.1f} mm")
        st.metric("Velocity", f"{summary['velocity_mm_yr']:.1f} mm/yr")
        st.metric("Estimated failure days", f"{summary['estimated_failure_days']:.0f}")
        st.markdown(
            f"""
            <div style="margin-top: 0.75rem; padding: 0.9rem 1rem; border-radius: 18px; background: {theme['bg']}; border: 1px solid {theme['color']};">
              <div style="font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.18em; color: #a8b6d1;">Emergency recommendation</div>
              <div style="margin-top: 0.35rem; color: #f8fafc; line-height: 1.5;">{summary['recommendation']}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)


def render_insar_analysis(summary, slider_key: str):
  render_section_header("InSAR Analysis", "Kept intact, but presented as a focused analysis workspace.")
  disp, coh, dates = summary["insar_stack"]
  pixel_id = st.slider("Select pixel / location", 0, disp.shape[0] - 1, int(summary["critical_pixel_id"]), key=slider_key)
  d_series = disp[pixel_id]
  c_series = coh[pixel_id]

  with st.spinner("Rendering InSAR analysis..."):
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    fig.patch.set_facecolor("#0b1220")

    ax = axes[0]
    ax.fill_between(dates, d_series, alpha=0.14, color="#7c3aed")
    ax.plot(dates, d_series, color="#7c3aed", lw=2.1)
    ax.axhline(10, color="#f59e0b", lw=1.2, ls="--", label="Medium threshold (10 mm)")
    ax.axhline(25, color="#ef4444", lw=1.2, ls="--", label="High threshold (25 mm)")
    ax.set_ylabel("LOS displacement (mm)")
    ax.set_title(f"Pixel {pixel_id} - cumulative deformation", fontweight="bold")
    ax.legend(frameon=False)
    apply_chart_theme(ax)

    ax2 = axes[1]
    velocity = np.gradient(d_series) / 12
    ax2.bar(dates, velocity, color=["#ef4444" if v > 2 else "#38bdf8" for v in velocity], width=8, alpha=0.88)
    ax2.axhline(0, color="#cbd5e1", lw=0.8)
    ax2.set_ylabel("Velocity (mm/day)")
    ax2.set_title("Instantaneous LOS velocity", fontweight="bold")
    apply_chart_theme(ax2)

    ax3 = axes[2]
    ax3.fill_between(dates, c_series, alpha=0.18, color="#22c55e")
    ax3.plot(dates, c_series, color="#22c55e", lw=2.1)
    ax3.axhline(0.3, color="#ef4444", lw=1, ls="--", label="Coherence threshold")
    ax3.set_ylabel("Coherence")
    ax3.set_xlabel("Date")
    ax3.set_ylim(0, 1)
    ax3.set_title("InSAR coherence", fontweight="bold")
    ax3.legend(frameon=False)
    apply_chart_theme(ax3)

    plt.tight_layout()
    st.pyplot(fig)
    plt.close(fig)

  st.markdown("<div style='height: 0.25rem;'></div>", unsafe_allow_html=True)
  m1, m2, m3 = st.columns(3)
  m1.metric("Alert level", summary["ivm"]["alert_level"])
  m2.metric("Estimated failure", f"{summary['ivm']['failure_day_est']:.0f} days")
  m3.metric("IVM slope", f"{summary['ivm']['slope_m']:.5f}")

  fig2, ax = plt.subplots(figsize=(10.5, 4.2))
  ivm = summary["ivm"]
  n = len(ivm["inverse_velocity"])
  ax.plot(range(n), ivm["inverse_velocity"], "o-", color="#38bdf8", lw=2, ms=4, label="Inverse velocity")
  proj_x = range(n, n + len(ivm["inv_v_projected"]))
  ax.plot(proj_x, ivm["inv_v_projected"], "--", color="#ef4444", lw=2, label="Projection")
  ax.axhline(0, color="#cbd5e1", lw=0.8, ls=":")
  ax.set_xlabel("Time step (x 12 days)")
  ax.set_ylabel("1 / v (day / mm)")
  ax.set_title("Inverse Velocity Method - failure forecast", fontweight="bold")
  ax.legend(frameon=False)
  apply_chart_theme(ax)
  fig2.tight_layout()
  st.pyplot(fig2)
  plt.close(fig2)


def render_ml_insights(df_pred, metrics, ensemble_proba):
    render_section_header("ML Insights", "Model evaluation and feature intelligence are available, but tucked away behind compact expanders.")
    cols = st.columns(4)
    rf = metrics["random_forest"]
    xgb = metrics["xgboost"]
    cards = [
        ("RF accuracy", f"{rf['accuracy']:.3f}", "Random Forest", RISK_COLOR["Low"]),
        ("RF ROC-AUC", f"{rf['roc_auc']:.3f}", "Random Forest", "#38bdf8"),
        ("XGB accuracy", f"{xgb['accuracy']:.3f}", "XGBoost", RISK_COLOR["Medium"]),
        ("XGB ROC-AUC", f"{xgb['roc_auc']:.3f}", "XGBoost", RISK_COLOR["High"]),
    ]
    for col, card in zip(cols, cards):
        with col:
            render_kpi_card(card[0], card[1], card[2], card[3])

    with st.expander("Feature importance", expanded=False):
        with st.spinner("Loading feature importance..."):
            rf_imp = load_importance("rf")
            xgb_imp = load_importance("xgb")
            fig, axes = plt.subplots(1, 2, figsize=(13, 5))
            for ax, imp_df, name, color in zip(
                axes,
                [rf_imp, xgb_imp],
                ["Random Forest", "XGBoost"],
                ["#38bdf8", "#f97316"],
            ):
                bars = ax.barh(imp_df["feature"][::-1], imp_df["importance"][::-1], color=color, alpha=0.9, edgecolor="none")
                ax.set_title(name, fontweight="bold")
                ax.set_xlabel("Feature importance")
                for bar, val in zip(bars, imp_df["importance"][::-1]):
                    ax.text(bar.get_width() + 0.002, bar.get_y() + bar.get_height() / 2, f"{val:.3f}", va="center", fontsize=8, color="#dbeafe")
                apply_chart_theme(ax)
            fig.patch.set_facecolor("#0b1220")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    with st.expander("Confusion matrix", expanded=False):
        with st.spinner("Rendering confusion matrices..."):
            fig, axes = plt.subplots(1, 2, figsize=(12, 5))
            for ax, model_key, title in zip(axes, ["random_forest", "xgboost"], ["Random Forest", "XGBoost"]):
                cm = np.array(metrics[model_key]["confusion_matrix"])
                sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax, linewidths=0.5, linecolor="white")
                ax.set_title(f"{title} confusion matrix", fontweight="bold")
                ax.set_xlabel("Predicted")
                ax.set_ylabel("Actual")
            fig.patch.set_facecolor("#0b1220")
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    with st.expander("ROC curves", expanded=False):
        with st.spinner("Computing ROC curves..."):
            y_true = df_pred["label"].astype(int).values
            y_bin = np.asarray(label_binarize(y_true, classes=[0, 1, 2]))
            fig, ax = plt.subplots(figsize=(8.8, 6))
            class_names = ["Low", "Medium", "High"]
            for idx, name in enumerate(class_names):
                fpr, tpr, _ = roc_curve(y_bin[:, idx], ensemble_proba[:, idx])
                score = auc(fpr, tpr)
                ax.plot(fpr, tpr, lw=2, label=f"{name} (AUC {score:.3f})", color=RISK_COLOR[name])
            ax.plot([0, 1], [0, 1], ls="--", color="#94a3b8", lw=1)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1.02)
            ax.set_xlabel("False positive rate")
            ax.set_ylabel("True positive rate")
            ax.set_title("One-vs-rest ROC curves", fontweight="bold")
            ax.legend(frameon=False)
            apply_chart_theme(ax)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    with st.expander("Research metrics", expanded=False):
        rcols = st.columns(5)
        research_cards = [
            ("Accuracy", f"{rf['accuracy']:.3f}", "Random Forest", "#38bdf8"),
            ("Precision", f"{rf['precision']:.3f}", "Random Forest", "#38bdf8"),
            ("Recall", f"{rf['recall']:.3f}", "Random Forest", "#38bdf8"),
            ("F1", f"{rf['f1']:.3f}", "Random Forest", "#38bdf8"),
            ("ROC-AUC", f"{rf['roc_auc']:.3f}", "Random Forest", "#38bdf8"),
        ]
        for col, card in zip(rcols, research_cards):
            with col:
                render_kpi_card(card[0], card[1], card[2], card[3])
        st.caption(f"Dataset rows: {len(df_pred):,} | Features: {len(FEATURES)} | Labels: Low, Medium, High")











def render_risk_map(df_pred):
    render_section_header("Risk Map", "A cleaner spatial view of the same geospatial predictions.")
    map_cols = st.columns(3)
    for col, label in zip(map_cols, ["Low", "Medium", "High"]):
        count = int((df_pred["risk_label"] == label).sum())
        with col:
            render_kpi_card(f"{label} pixels", f"{count:,}", "Ensemble prediction count", RISK_COLOR[label])

    map_df = df_pred[["latitude", "longitude", "risk_code", "risk_label", "confidence"]].copy()
    map_df["color"] = map_df["risk_label"].map(
        {
            "Low": [34, 197, 94, 150],
            "Medium": [245, 158, 11, 195],
            "High": [239, 68, 68, 235],
        }
    )

    st.markdown('<div class="map-shell">', unsafe_allow_html=True)
    with st.spinner("Rendering map view..."):
      st.map(map_df[map_df["risk_label"] != "Low"].rename(columns={"latitude": "lat", "longitude": "lon"}), color="color")
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        with st.expander("Rainfall band analysis", expanded=False):
            df_tmp = df_pred.copy()
            df_tmp["rainfall_band"] = pd.cut(df_tmp["rainfall_mm"], bins=[0, 50, 100, 200, 350], labels=["0-50", "50-100", "100-200", "200+"])
            grp = df_tmp.groupby(["rainfall_band", "risk_label"]).size().unstack(fill_value=0)
            fig, ax = plt.subplots(figsize=(6.8, 4.4))
            grp.plot(kind="bar", ax=ax, color=[RISK_COLOR["Low"], RISK_COLOR["Medium"], RISK_COLOR["High"]], edgecolor="none")
            ax.set_xlabel("Rainfall band (mm)")
            ax.set_ylabel("Pixel count")
            ax.set_title("Risk by rainfall band", fontweight="bold")
            ax.legend(title="Risk", frameon=False)
            apply_chart_theme(ax)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
    with col2:
        with st.expander("Slope sensitivity", expanded=False):
            fig, ax = plt.subplots(figsize=(6.8, 4.4))
            for label, color in RISK_COLOR.items():
                mask = df_pred["risk_label"] == label
                ax.scatter(df_pred.loc[mask, "slope_deg"], df_pred.loc[mask, "deformation_mm"], c=color, alpha=0.4, s=14, label=label)
            ax.axvline(30, color="#94a3b8", ls="--", lw=1, label="30 deg threshold")
            ax.set_xlabel("Slope (deg)")
            ax.set_ylabel("Deformation (mm)")
            ax.set_title("Risk vs slope", fontweight="bold")
            ax.legend(frameon=False)
            apply_chart_theme(ax)
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)



def render_alert_system(rf, xgb_m):
    render_section_header("Alert System", "The same prediction and alert workflow, presented as a focused action panel.")
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown('<div class="panel-shell">', unsafe_allow_html=True)
        st.subheader("InSAR parameters")
        deformation_mm = st.slider("Deformation (mm)", -20.0, 60.0, 5.0, 0.1)
        velocity_mm_yr = st.slider("LOS velocity (mm/yr)", 0.0, 200.0, 15.0, 0.5)
        coherence = st.slider("InSAR coherence [0-1]", 0.1, 1.0, 0.8, 0.01)
        ivm_days = st.slider("IVM failure estimate (days)", 1, 9999, 500, 1)
        st.markdown("</div>", unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="panel-shell">', unsafe_allow_html=True)
        st.subheader("Environmental parameters")
        rainfall_mm = st.slider("7-day rainfall (mm)", 0.0, 350.0, 40.0, 1.0)
        slope_deg = st.slider("Slope (degrees)", 0.0, 60.0, 20.0, 0.5)
        soil_moisture_pct = st.slider("Soil moisture (%)", 5.0, 95.0, 35.0, 0.5)
        elevation_m = st.slider("Elevation (m)", 100.0, 3000.0, 800.0, 10.0)
        ndvi = st.slider("NDVI", -1.0, 1.0, 0.4, 0.01)
        st.markdown("</div>", unsafe_allow_html=True)

    model_choice = st.selectbox("Model", ["ensemble", "xgboost", "random_forest"])
    location = st.text_input("Location name", "Site A - Western Ghats")

    if st.button("Predict Risk Level", type="primary", use_container_width=True):
        X = np.array([
            [
                deformation_mm,
                velocity_mm_yr,
                coherence,
                rainfall_mm,
                slope_deg,
                soil_moisture_pct,
                elevation_m,
                180.0,
                ndvi,
            ]
        ])

        proba_rf = rf.predict_proba(X)[0]
        proba_xgb = xgb_m.predict_proba(X)[0]

        if model_choice == "ensemble":
            proba = (proba_rf + proba_xgb) / 2
        elif model_choice == "xgboost":
            proba = proba_xgb
        else:
            proba = proba_rf

        pred_cls = int(np.argmax(proba))
        risk_label = LABEL_MAP[pred_cls]
        confidence = float(proba[pred_cls])
        theme = risk_meta(risk_label)

        st.markdown(
            f"""
            <div class="risk-banner" style="background: {theme['bg']}; border: 1px solid {theme['color']};">
              <div class="risk-kicker">Prediction result</div>
              <div class="risk-title" style="color: {theme['color']};">{risk_label.upper()} RISK</div>
              <div style="margin-top: 0.45rem; color: #dce9fb;">Confidence: <b>{confidence:.1%}</b> | Model: <b>{model_choice.replace('_', ' ').title()}</b></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        ca, cb, cc = st.columns(3)
        for col_w, label, prob in zip([ca, cb, cc], ["Low", "Medium", "High"], proba):
            accent = RISK_COLOR[label]
            col_w.markdown(
                f"""
                <div class="glass-card" style="padding: 0.9rem;">
                  <div style="display: flex; justify-content: space-between; align-items: center; color: #dbeafe; font-weight: 700;">
                    <span>{label}</span><span style="color: {accent};">{prob:.1%}</span>
                  </div>
                  <div style="height: 10px; background: rgba(255,255,255,0.08); border-radius: 999px; overflow: hidden; margin-top: 0.6rem;">
                    <div style="width: {prob * 100:.1f}%; height: 10px; background: {accent}; border-radius: 999px;"></div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        st.subheader("Alert assessment")
        reading = SensorReading(
            location_name=location,
            deformation_mm=deformation_mm,
            velocity_mm_yr=velocity_mm_yr,
            rainfall_mm=rainfall_mm,
            slope_deg=slope_deg,
            soil_moisture_pct=soil_moisture_pct,
            coherence=coherence,
            ivm_failure_days=float(ivm_days),
            ml_risk_label=risk_label,
            ml_confidence=confidence,
        )
        level, triggers = classify_alert_level(reading)
        st.markdown(f"**Alert level:** `{level}`")
        for trigger in triggers:
            st.markdown(f"- {trigger}")

        if st.button("Send Alert Notification"):
            alert = process_reading(reading, send_only_above="LOW")
            telegram_status = "sent" if alert.sent_telegram else "not set"
            whatsapp_status = "sent" if alert.sent_whatsapp else "not set"
            st.success(f"Alert `{alert.alert_id}` logged. Telegram: {telegram_status} | WhatsApp: {whatsapp_status}")


def render_advanced_analytics(df_pred, metrics, ensemble_proba):
    render_section_header("Advanced Analytics", "Hidden by default so the dashboard feels lighter, while the research assets still remain available.")

    with st.expander("Correlation matrix", expanded=False):
        corr = df_pred[FEATURES + ["label"]].corr(numeric_only=True)
        fig, ax = plt.subplots(figsize=(9, 7))
        mask = np.triu(np.ones_like(corr, dtype=bool))
        sns.heatmap(corr, mask=mask, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax, linewidths=0.5, cbar_kws={"shrink": 0.8})
        ax.set_title("Feature correlation matrix", fontweight="bold")
        apply_chart_theme(ax)
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

    with st.expander("Clustering analysis", expanded=False):
        high_mask = df_pred["risk_label"] == "High"
        if high_mask.any():
            coords = np.radians(df_pred.loc[high_mask, ["latitude", "longitude"]].values)
            db = DBSCAN(eps=0.05, min_samples=5, algorithm="ball_tree", metric="haversine")
            labels = db.fit_predict(coords)
            cluster_count = len(set(labels)) - (1 if -1 in labels else 0)
            noise_count = int((labels == -1).sum())

            c1, c2, c3 = st.columns(3)
            c1.metric("High-risk points", f"{len(labels):,}")
            c2.metric("Clusters", str(max(cluster_count, 0)))
            c3.metric("Noise points", str(noise_count))

            fig, ax = plt.subplots(figsize=(8.5, 5.5))
            scatter = ax.scatter(
                df_pred.loc[high_mask, "longitude"],
                df_pred.loc[high_mask, "latitude"],
                c=labels,
                cmap="viridis",
                s=18,
                alpha=0.85,
            )
            ax.set_xlabel("Longitude")
            ax.set_ylabel("Latitude")
            ax.set_title("DBSCAN clusters of high-risk pixels", fontweight="bold")
            apply_chart_theme(ax)
            fig.colorbar(scatter, ax=ax, shrink=0.82, label="Cluster ID")
            fig.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("No high-risk pixels are currently available for clustering.")

    with st.expander("Research metrics", expanded=False):
        rf = metrics["random_forest"]
        xgb = metrics["xgboost"]
        c1, c2, c3, c4, c5 = st.columns(5)
        for col, card in zip(
            [c1, c2, c3, c4, c5],
            [
                ("RF accuracy", f"{rf['accuracy']:.3f}"),
                ("RF precision", f"{rf['precision']:.3f}"),
                ("RF recall", f"{rf['recall']:.3f}"),
                ("RF F1", f"{rf['f1']:.3f}"),
                ("RF ROC-AUC", f"{rf['roc_auc']:.3f}"),
            ],
        ):
            with col:
                render_kpi_card(card[0], card[1], "Random Forest", "#38bdf8")
        c6, c7, c8, c9, c10 = st.columns(5)
        for col, card in zip(
            [c6, c7, c8, c9, c10],
            [
                ("XGB accuracy", f"{xgb['accuracy']:.3f}"),
                ("XGB precision", f"{xgb['precision']:.3f}"),
                ("XGB recall", f"{xgb['recall']:.3f}"),
                ("XGB F1", f"{xgb['f1']:.3f}"),
                ("XGB ROC-AUC", f"{xgb['roc_auc']:.3f}"),
            ],
        ):
            with col:
                render_kpi_card(card[0], card[1], "XGBoost", "#f97316")
        st.caption(f"Dataset rows: {len(df_pred):,} | Features: {len(FEATURES)} | Labels: Low, Medium, High")



render_styles()

st.sidebar.markdown("## LandSense EWS")
st.sidebar.markdown("*Landslide Early Warning System*")
st.sidebar.divider()

st.sidebar.markdown("**System status**")
st.sidebar.success("Models loaded")
st.sidebar.info(f"Live time: {utc_now_label()}")
st.sidebar.caption("Sentinel-1 | 12-day repeat | Western Ghats AOI")
st.sidebar.divider()
refresh_enabled = st.sidebar.checkbox("Live auto-refresh", value=True)
refresh_interval = st.sidebar.select_slider("Refresh interval (seconds)", options=[15, 30, 45, 60], value=30)
auto_refresh(refresh_enabled, refresh_interval)

rf_model, xgb_model = load_models()
df = load_dataset()
metrics = load_metrics()
alerts = load_alert_history(100)
zones_geojson = load_zones(BASE_DIR / "config" / "risk_zones.geojson")
disp, coh, dates = get_insar_stack()

proba_rf = rf_model.predict_proba(df[FEATURES].values)
proba_xgb = xgb_model.predict_proba(df[FEATURES].values)
ensemble_proba = (proba_rf + proba_xgb) / 2
preds = np.argmax(ensemble_proba, axis=1)

df_pred = df.copy()
df_pred["risk_code"] = preds
df_pred["risk_label"] = [LABEL_MAP[p] for p in preds]
df_pred["confidence"] = ensemble_proba[np.arange(len(ensemble_proba)), preds]

risk_counts = df_pred["risk_label"].value_counts()
current_risk = "High" if int(risk_counts.get("High", 0)) > 0 else "Medium" if int(risk_counts.get("Medium", 0)) > 0 else "Low"
current_status = risk_meta(current_risk)["status"]
region_status = "Immediate attention required" if current_risk == "High" else "Heightened watch" if current_risk == "Medium" else "Stable"
focus_df = df_pred[df_pred["risk_label"] == current_risk]
if focus_df.empty:
    focus_df = df_pred.nlargest(max(1, len(df_pred) // 10), "confidence")

critical_pixel_id = int(df_pred["deformation_mm"].idxmax()) % disp.shape[0]
ivm = inverse_velocity_method(disp[critical_pixel_id], dt_days=12.0, window=5, project_steps=15)

summary = {
    "current_risk": current_risk,
    "current_status": current_status,
    "region_status": region_status,
    "active_alerts": len(alerts),
    "rainfall_mm": float(focus_df["rainfall_mm"].mean()),
    "deformation_mm": float(focus_df["deformation_mm"].mean()),
    "velocity_mm_yr": float(focus_df["velocity_mm_yr"].mean()),
    "estimated_failure_days": float(ivm["failure_day_est"]),
    "recommendation": risk_meta(current_risk)["recommendation"],
    "last_updated": utc_now_label(),
    "insar_stack": (disp, coh, dates),
    "critical_pixel_id": critical_pixel_id,
    "ivm": ivm,
}

st.markdown(
    f"<div class='soft-pill'>Live view updated at {summary['last_updated']}</div>",
    unsafe_allow_html=True,
)

st.markdown(
  f"<div class='soft-pill' style='margin-top:0.35rem;'>Mode help: {MODE_HELP[st.session_state.get('landsense_mode', TAB_NAMES[0])]}</div>",
  unsafe_allow_html=True,
)

sections = st.tabs(TAB_NAMES)
with sections[0]:
  render_public_safety_mode(summary, alerts, df_pred, zones_geojson)
  with st.expander("Operational geospatial detail", expanded=False):
    render_risk_map(df_pred)
with sections[1]:
  render_operations_mode(summary, alerts, df_pred, rf_model, xgb_model, zones_geojson)
  with st.expander("Live monitoring detail", expanded=False):
    render_live_monitoring(summary, alerts)
  with st.expander("Geospatial risk map detail", expanded=False):
    render_risk_map(df_pred)
  with st.expander("InSAR operational detail", expanded=False):
    render_insar_analysis(summary, slider_key="insar_pixel_operations")
with sections[2]:
  render_research_mode(df_pred, metrics, ensemble_proba)
  with st.expander("Advanced analytics detail", expanded=False):
    render_advanced_analytics(df_pred, metrics, ensemble_proba)
  with st.expander("InSAR research detail", expanded=False):
    render_insar_analysis(summary, slider_key="insar_pixel_research")
