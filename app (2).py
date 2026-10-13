
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

# ============================================================
# ORCA — Marine Ecosystem Reasoning with Collaborative Agents
# Streamlit frontend + optional existing FastAPI backend
# ============================================================

st.set_page_config(
    page_title="ORCA | Marine Ecosystem Intelligence",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- Configuration ----------------
DEFAULT_BACKEND = os.getenv("ORCA_API_URL", "").strip()

try:
    BACKEND_URL = str(
        st.secrets.get("ORCA_API_URL", DEFAULT_BACKEND)
    ).strip().rstrip("/")
except Exception:
    BACKEND_URL = DEFAULT_BACKEND.rstrip("/")

REQUEST_TIMEOUT = int(os.getenv("ORCA_TIMEOUT_SECONDS", "25"))

REGIONS: dict[str, dict[str, float]] = {
    "Arabian Sea": {"lat": 17.0, "lon": 64.0},
    "Bay of Bengal": {"lat": 15.0, "lon": 88.0},
    "Indian Ocean": {"lat": -10.0, "lon": 75.0},
    "Andaman Sea": {"lat": 10.0, "lon": 96.0},
    "North Atlantic": {"lat": 40.0, "lon": -35.0},
    "Coral Triangle": {"lat": -2.0, "lon": 125.0},
    "Gulf of Mexico": {"lat": 24.0, "lon": -90.0},
    "Southern Ocean": {"lat": -55.0, "lon": 30.0},
}

st.session_state.setdefault("orca_history", [])
st.session_state.setdefault("orca_last_result", None)
st.session_state.setdefault("orca_last_inputs", None)


# ---------------- Visual styling ----------------
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

    :root { color-scheme: dark; }

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .stApp {
        background:
            radial-gradient(circle at 12% 0%, rgba(0,210,220,.12), transparent 28%),
            radial-gradient(circle at 95% 12%, rgba(25,110,200,.13), transparent 30%),
            linear-gradient(180deg, #061421 0%, #071b2a 55%, #061421 100%);
        color: #edf8ff;
    }

    [data-testid="stSidebar"] {
        background: #081c2a;
        border-right: 1px solid #173b50;
    }

    h1, h2, h3 {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #f3fbff;
    }

    p, label, .stMarkdown {
        color: #d0e4ef;
    }

    .orca-hero {
        position: relative;
        overflow: hidden;
        padding: 30px 32px;
        border: 1px solid rgba(103,232,249,.27);
        border-radius: 24px;
        background: linear-gradient(115deg, rgba(10,65,83,.94), rgba(7,31,53,.97));
        box-shadow: 0 18px 55px rgba(0,0,0,.18);
        margin-bottom: 18px;
    }

    .orca-hero:after {
        content: "";
        position: absolute;
        width: 300px;
        height: 300px;
        right: -100px;
        top: -150px;
        border: 1px solid rgba(103,232,249,.18);
        border-radius: 50%;
        box-shadow: 0 0 0 28px rgba(103,232,249,.025),
                    0 0 0 58px rgba(103,232,249,.02);
        pointer-events: none;
    }

    .eyebrow {
        color: #67e8f9;
        font-size: .76rem;
        letter-spacing: .19em;
        font-weight: 800;
        text-transform: uppercase;
    }

    .hero-title {
        font-family: 'Space Grotesk';
        font-size: clamp(2.2rem, 4.5vw, 3.7rem);
        line-height: 1.02;
        font-weight: 700;
        margin: 12px 0;
    }

    .hero-copy {
        color: #c4e2ee;
        max-width: 850px;
        font-size: 1.02rem;
    }

    .chip {
        display: inline-block;
        padding: 5px 10px;
        margin: 5px 5px 0 0;
        border-radius: 999px;
        background: #103b4a;
        color: #9cf3f2;
        font-size: .72rem;
        font-weight: 700;
        border: 1px solid #1d5968;
    }

    .metric-card, .agent-card, .info-card, .report-card {
        background: linear-gradient(145deg, rgba(15,43,62,.96), rgba(8,29,45,.96));
        border: 1px solid #1c465c;
        border-radius: 16px;
        padding: 17px 18px;
        height: 100%;
    }

    .metric-label {
        color: #92b6c8;
        font-size: .74rem;
        text-transform: uppercase;
        letter-spacing: .09em;
    }

    .metric-value {
        color: #f0fbff;
        font-family: 'Space Grotesk';
        font-size: 1.75rem;
        font-weight: 700;
        margin: 5px 0;
    }

    .metric-note {
        color: #8edce8;
        font-size: .8rem;
    }

    .muted {
        color: #8fb8cb;
        font-size: .85rem;
    }

    .smallcaps {
        color: #76dce8;
        font-size: .73rem;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button {
        background: linear-gradient(90deg, #06b6d4, #0ea5a4);
        color: #031824;
        font-weight: 800;
        border: 0;
        border-radius: 11px;
        min-height: 42px;
    }

    div[data-testid="stButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover {
        background: linear-gradient(90deg, #67e8f9, #5eead4);
        color: #031824;
    }

    hr { border-color: #183a4e; }

    [data-testid="stMetricValue"] { color: #f0fbff; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------- Helpers ----------------
def safe_float(value: Any) -> float | None:
    """Convert a value to float; blank or invalid values become None."""
    try:
        if value is None:
            return None

        text_value = str(value).strip()

        if not text_value:
            return None

        return float(text_value)

    except (TypeError, ValueError):
        return None


def to_json_download(value: Any) -> str:
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def metric_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def agent_card(
    icon: str,
    name: str,
    speciality: str,
    finding: str,
    status: str,
) -> None:
    st.markdown(
        f"""
        <div class="agent-card">
            <div style="display:flex;justify-content:space-between;gap:8px;align-items:center">
                <span style="font-size:1.55rem">{icon}</span>
                <span class="chip">{status}</span>
            </div>
            <div style="font-size:1.02rem;font-weight:700;color:#effaff;margin-top:10px">
                {name}
            </div>
            <div class="muted" style="margin:4px 0 10px">{speciality}</div>
            <div style="font-size:.9rem;color:#d5e9f2">{finding}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------- External data ----------------
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_open_meteo(
    lat: float,
    lon: float,
) -> dict[str, Any]:
    """Fetch available marine and weather data from Open-Meteo."""

    output: dict[str, Any] = {
        "source": "unavailable",
        "marine": {},
        "weather": {},
        "errors": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        marine_url = "https://marine-api.open-meteo.com/v1/marine"

        marine_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "wave_height,wave_direction,wave_period",
            "hourly": "wave_height",
            "forecast_days": 2,
            "timezone": "UTC",
        }

        response = requests.get(
            marine_url,
            params=marine_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        output["marine"] = response.json()

    except Exception as exc:
        output["errors"].append(f"Marine API: {exc}")

    try:
        weather_url = "https://api.open-meteo.com/v1/forecast"

        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": (
                "temperature_2m,relative_humidity_2m,"
                "wind_speed_10m,wind_direction_10m,precipitation"
            ),
            "hourly": "wind_speed_10m",
            "forecast_days": 2,
            "timezone": "UTC",
        }

        response = requests.get(
            weather_url,
            params=weather_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        output["weather"] = response.json()

    except Exception as exc:
        output["errors"].append(f"Weather API: {exc}")

    if output["marine"] or output["weather"]:
        output["source"] = "live API"

    return output


def extract_current(api_data: dict[str, Any]) -> dict[str, Any]:
    marine = api_data.get("marine", {}).get("current", {}) or {}
    weather = api_data.get("weather", {}).get("current", {}) or {}

    return {
        "wave_height_m": safe_float(marine.get("wave_height")),
        "wave_direction_deg": safe_float(marine.get("wave_direction")),
        "wave_period_s": safe_float(marine.get("wave_period")),
        "air_temperature_c": safe_float(weather.get("temperature_2m")),
        "humidity_pct": safe_float(weather.get("relative_humidity_2m")),
        "wind_speed_kmh": safe_float(weather.get("wind_speed_10m")),
        "wind_direction_deg": safe_float(weather.get("wind_direction_10m")),
        "precipitation_mm": safe_float(weather.get("precipitation")),
    }


def post_backend(
    region: str,
    lat: float,
    lon: float,
    marine: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Call the existing FastAPI backend if ORCA_API_URL is configured."""

    if not BACKEND_URL:
        return None, "Backend URL not configured."

    payload = {
        "region": region,
        "latitude": lat,
        "longitude": lon,
        "marine_data": marine,
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/assess",
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        if not isinstance(data, dict):
            return {"backend_response": data}, None

        return data, None

    except requests.RequestException as exc:
        return None, f"Backend request failed: {exc}"

    except ValueError as exc:
        return None, f"Backend did not return valid JSON: {exc}"


# ---------------- Six agent functions ----------------
def run_temperature_agent(
    sea_temp: float | None,
) -> dict[str, Any]:

    if sea_temp is None:
        return {
            "name": "Sea Temperature Agent",
            "status": "DATA MISSING",
            "finding": (
                "No sea-surface temperature was supplied. "
                "Air temperature is not a substitute."
            ),
            "evidence": None,
            "level": "Unknown",
        }

    if sea_temp >= 30:
        level = "Attention"
        status = "SCREENING FLAG"
        finding = (
            f"Sea temperature is {sea_temp:.1f} °C. "
            "Compare against the local seasonal climatology."
        )

    elif sea_temp >= 28:
        level = "Context needed"
        status = "CONTEXT NEEDED"
        finding = (
            f"Sea temperature is {sea_temp:.1f} °C. "
            "Temperature alone cannot establish heat stress "
            "without a regional baseline and habitat context."
        )

    else:
        level = "No threshold crossed"
        status = "SCREENING"
        finding = (
            f"Sea temperature is {sea_temp:.1f} °C. "
            "No broad threshold was crossed in this simple screen. "
            "A local baseline comparison is still needed."
        )

    return {
        "name": "Sea Temperature Agent",
        "status": status,
        "finding": finding,
        "evidence": sea_temp,
        "level": level,
    }


def run_chlorophyll_agent(
    chlorophyll: float | None,
) -> dict[str, Any]:

    if chlorophyll is None:
        return {
            "name": "Chlorophyll Agent",
            "status": "DATA MISSING",
            "finding": (
                "No chlorophyll concentration was supplied. "
                "The default Open-Meteo request does not provide it."
            ),
            "evidence": None,
            "level": "Unknown",
        }

    if chlorophyll >= 5:
        level = "Attention"
        status = "SCREENING FLAG"
        finding = (
            f"Chlorophyll is {chlorophyll:.2f} mg/m³. "
            "Check local baselines and validated bloom products. "
            "This value alone does not prove a harmful bloom."
        )

    else:
        level = "Context needed"
        status = "SCREENING"
        finding = (
            f"Chlorophyll is {chlorophyll:.2f} mg/m³. "
            "Interpret with season, water type, satellite quality, "
            "and local reference values."
        )

    return {
        "name": "Chlorophyll Agent",
        "status": status,
        "finding": finding,
        "evidence": chlorophyll,
        "level": level,
    }


def run_weather_agent(
    wind_kmh: float | None,
    wave_height: float | None,
    precip: float | None,
) -> dict[str, Any]:

    if wind_kmh is None and wave_height is None:
        return {
            "name": "Weather & Wind Agent",
            "status": "DATA MISSING",
            "finding": "No live wind or wave observation was returned.",
            "evidence": None,
            "level": "Unknown",
        }

    notes = []

    if wind_kmh is not None:
        notes.append(f"wind {wind_kmh:.1f} km/h")

    if wave_height is not None:
        notes.append(f"waves {wave_height:.1f} m")

    if precip is not None:
        notes.append(f"precipitation {precip:.1f} mm")

    flagged = (
        (wind_kmh is not None and wind_kmh >= 35)
        or (wave_height is not None and wave_height >= 3)
    )

    return {
        "name": "Weather & Wind Agent",
        "status": "SCREENING FLAG" if flagged else "OBSERVATIONS RECEIVED",
        "finding": (
            "Available conditions: "
            + ", ".join(notes)
            + ". These are contextual indicators. "
            "Use official marine forecasts for safety decisions."
        ),
        "evidence": {
            "wind_kmh": wind_kmh,
            "wave_height_m": wave_height,
            "precipitation_mm": precip,
        },
        "level": "Attention" if flagged else "Context needed",
    }


def run_historical_agent(
    deviation_pct: float | None,
) -> dict[str, Any]:

    if deviation_pct is None:
        return {
            "name": "Historical Trend Agent",
            "status": "BASELINE NEEDED",
            "finding": (
                "No historical anomaly value was provided. "
                "A real trend needs comparable time-series data "
                "and a documented baseline."
            ),
            "evidence": None,
            "level": "Unknown",
        }

    level = (
        "Attention"
        if abs(deviation_pct) >= 10
        else "Context needed"
    )

    return {
        "name": "Historical Trend Agent",
        "status": (
            "SCREENING FLAG"
            if level == "Attention"
            else "SCREENING"
        ),
        "finding": (
            f"Supplied historical deviation is {deviation_pct:.1f}%. "
            "Verify its source, period, units, and baseline."
        ),
        "evidence": deviation_pct,
        "level": level,
    }


def run_satellite_agent(
    satellite_status: str,
    satellite_note: str,
) -> dict[str, Any]:

    if satellite_status == "Unavailable":
        return {
            "name": "Satellite Intelligence Agent",
            "status": "UNAVAILABLE",
            "finding": (
                "No satellite feed is connected in this Streamlit layer. "
                "Connect a validated satellite source or return "
                "satellite evidence from FastAPI."
            ),
            "evidence": None,
            "level": "Unknown",
        }

    return {
        "name": "Satellite Intelligence Agent",
        "status": satellite_status.upper(),
        "finding": (
            satellite_note
            or "Satellite context was supplied manually or by the backend. "
            "Validate source, time, and coverage."
        ),
        "evidence": satellite_note or None,
        "level": "Context needed",
    }


def run_reasoning_agent(
    agents: list[dict[str, Any]],
    backend_result: dict[str, Any] | None,
) -> dict[str, Any]:

    available = [
        agent for agent in agents
        if agent.get("level") != "Unknown"
    ]

    flagged = [
        agent for agent in available
        if agent.get("level") == "Attention"
    ]

    missing = [
        agent for agent in agents
        if agent.get("level") == "Unknown"
    ]

    if backend_result:
        summary = (
            backend_result.get("summary")
            or backend_result.get("reasoning")
            or backend_result.get("assessment")
        )

        if isinstance(summary, str) and summary.strip():
            return {
                "status": "Backend assessment",
                "summary": summary,
                "basis": (
                    "This summary was returned by the configured "
                    "FastAPI backend. Review its evidence and assumptions."
                ),
                "flagged": flagged,
                "missing": missing,
                "backend_used": True,
            }

    if len(flagged) >= 2:
        status = "Elevated attention"
        summary = (
            "Multiple available indicators crossed broad screening "
            "thresholds. This calls for verification; it does not "
            "prove ecosystem damage or a confirmed event."
        )

    elif len(flagged) == 1:
        status = "Watch"
        summary = (
            "One available indicator crossed a broad screening "
            "threshold. Review its source and compare it with "
            "local seasonal and historical conditions."
        )

    elif not available:
        status = "Insufficient data"
        summary = (
            "There is not enough usable data to form a meaningful "
            "assessment. Connect marine observations or the FastAPI backend."
        )

    else:
        status = "No broad screening flags"
        summary = (
            "No broad screening threshold was crossed in the available "
            "indicators. This does not confirm that the ecosystem is healthy; "
            "important variables may be missing."
        )

    return {
        "status": status,
        "summary": summary,
        "basis": (
            "This fallback combines transparent screening rules. "
            "It is not a trained AI model, validated ecological risk score, "
            "or causal model."
        ),
        "flagged": flagged,
        "missing": missing,
        "backend_used": False,
    }


# ---------------- Sidebar ----------------
with st.sidebar:
    st.markdown("## 🌊 ORCA")
    st.markdown(
        '<div class="smallcaps">Ocean Reasoning Collaborative Agency</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    page = st.radio(
        "Navigate",
        [
            "Mission Control",
            "Agent Lab",
            "Two Worlds",
            "Ocean Memory",
            "Evidence Report",
            "Data & Integrations",
        ],
    )

    st.divider()

    region = st.selectbox(
        "Marine region",
        list(REGIONS.keys()),
        index=0,
    )

    coordinates = REGIONS[region]

    use_live = st.toggle(
        "Fetch available live conditions",
        value=True,
    )

    st.caption(
        "Live requests use Open-Meteo marine and weather endpoints. "
        "Availability varies by variable and region."
    )

    st.divider()
    st.markdown("**Backend connection**")

    if BACKEND_URL:
        st.success("FastAPI URL configured")
        st.caption(BACKEND_URL)
    else:
        st.warning("FastAPI URL not configured")
        st.caption(
            "Set ORCA_API_URL in Streamlit Secrets to call your backend."
        )

    st.divider()
    st.caption(
        "Research and decision-support prototype—not a validated warning service."
    )

    # Optional manual values.
    # Blank fields are treated as missing data.
    st.divider()
    st.markdown("**Optional data overrides**")

    manual_chl_text = st.text_input(
        "Chlorophyll (mg/m³)",
        value="",
        placeholder="Leave blank if unavailable",
        help="Enter a verified chlorophyll concentration.",
    )

    manual_sst_text = st.text_input(
        "Sea surface temperature (°C)",
        value="",
        placeholder="Leave blank if unavailable",
        help="Enter verified sea-surface temperature. Air temperature is not a substitute.",
    )

    manual_deviation_text = st.text_input(
        "Historical deviation (%)",
        value="",
        placeholder="Leave blank if unavailable",
        help="Enter a verified deviation against a documented baseline.",
    )

    satellite_status = st.selectbox(
        "Satellite data status",
        ["Unavailable", "Connected", "Cached"],
        index=0,
    )

    satellite_note = st.text_input(
        "Satellite observation note",
        placeholder="Source, timestamp, observation",
    )


# Blank or invalid inputs become None.
chlorophyll = safe_float(manual_chl_text)
sea_temp = safe_float(manual_sst_text)
historical_deviation = safe_float(manual_deviation_text)


# ---------------- Load current external data ----------------
api_data: dict[str, Any] = {
    "source": "disabled",
    "marine": {},
    "weather": {},
    "errors": [],
}

if use_live:
    with st.spinner("Checking available marine and weather data..."):
        api_data = fetch_open_meteo(
            coordinates["lat"],
            coordinates["lon"],
        )

current = extract_current(api_data)

# Recover the previous backend result across Streamlit reruns.
result = st.session_state.get("orca_last_result")
backend_result = result.get("backend_result") if result else None
backend_error = result.get("backend_error") if result else None


# ---------------- Header ----------------
st.markdown(
    f"""
    <div class="orca-hero">
        <div class="eyebrow">Marine Ecosystem Intelligence Platform</div>
        <div class="hero-title">
            Read the ocean.<br>
            <span style="color:#67e8f9">Connect both worlds.</span>
        </div>
        <div class="hero-copy">
            ORCA brings marine observations together, examines evidence
            through six specialist agents, and explains what may be
            happening above and below the water while making missing
            data and uncertainty visible.
        </div>
        <div style="margin-top:16px">
            <span class="chip">📍 {region}</span>
            <span class="chip">🤖 6 AGENTS</span>
            <span class="chip">🌊 ABOVE + BELOW WATER</span>
            <span class="chip">🔎 EVIDENCE FIRST</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Dashboard refreshed: "
    + datetime.now().astimezone().strftime("%d %b %Y, %I:%M:%S %p %Z")
)


# ---------------- Run assessment ----------------
if st.button(
    "🚀 Run ORCA Assessment",
    type="primary",
    use_container_width=True,
):
    with st.spinner(
        "Running specialist analyses and checking your FastAPI backend..."
    ):
        backend_payload = {
            "open_meteo": api_data,
            "current_conditions": current,
            "manual_inputs": {
                "chlorophyll_mg_m3": chlorophyll,
                "sea_surface_temperature_c": sea_temp,
                "historical_deviation_pct": historical_deviation,
                "satellite_status": satellite_status,
                "satellite_note": satellite_note,
            },
        }

        backend_result, backend_error = post_backend(
            region,
            coordinates["lat"],
            coordinates["lon"],
            backend_payload,
        )

        temp_agent = run_temperature_agent(sea_temp)
        chl_agent = run_chlorophyll_agent(chlorophyll)

        weather_agent = run_weather_agent(
            current.get("wind_speed_kmh"),
            current.get("wave_height_m"),
            current.get("precipitation_mm"),
        )

        hist_agent = run_historical_agent(historical_deviation)

        sat_agent = run_satellite_agent(
            satellite_status,
            satellite_note,
        )

        # Five specialist agents + one collaborative reasoning agent.
        agents = [
            temp_agent,
            chl_agent,
            weather_agent,
            hist_agent,
            sat_agent,
        ]

        reasoning = run_reasoning_agent(
            agents,
            backend_result,
        )

        all_result = {
            "region": region,
            "coordinates": coordinates,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_source": api_data.get("source", "unavailable"),
            "current_conditions": current,
            "agents": agents,
            "reasoning": reasoning,
            "backend_result": backend_result,
            "backend_error": backend_error,
        }

        st.session_state["orca_last_result"] = all_result
        st.session_state["orca_last_inputs"] = {
            "region": region,
            "temperature": sea_temp,
            "chlorophyll": chlorophyll,
            "wind": current.get("wind_speed_kmh"),
            "historical_deviation": historical_deviation,
            "status": reasoning["status"],
        }

        st.session_state["orca_history"].append({
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "region": region,
            "status": reasoning["status"],
            "temperature_c": sea_temp,
            "chlorophyll_mg_m3": chlorophyll,
            "wind_kmh": current.get("wind_speed_kmh"),
            "data_source": api_data.get("source", "unavailable"),
        })

        st.session_state["orca_history"] = (
            st.session_state["orca_history"][-30:]
        )

    st.success(
        "ORCA assessment complete. Review the evidence and missing-data notes below."
    )

result = st.session_state.get("orca_last_result")

if result and result.get("region") != region:
    st.info(
        "The last assessment was for another region. "
        "Run the assessment again to refresh it."
    )


# ---------------- Mission Control ----------------
if page == "Mission Control":
    st.markdown("### Mission Control")
    st.markdown(
        '<div class="muted">Live data availability, agent findings, and an evidence-aware overview.</div>',
        unsafe_allow_html=True,
    )

    source_label = api_data.get("source", "unavailable")

    if source_label == "live API":
        st.success(
            "Some current marine/weather data was retrieved from Open-Meteo. "
            "Individual variables may still be missing."
        )
    elif use_live:
        st.warning(
            "Live data could not be retrieved. Check your connection; "
            "unavailable values are not fabricated."
        )
    else:
        st.info(
            "Live fetching is disabled. Only manual inputs or backend data "
            "can be assessed."
        )

    cols = st.columns(4)

    with cols[0]:
        metric_card(
            "Wave height",
            f"{current['wave_height_m']:.2f} m"
            if current["wave_height_m"] is not None
            else "Unavailable",
            "Open-Meteo marine API",
        )

    with cols[1]:
        metric_card(
            "Wind speed",
            f"{current['wind_speed_kmh']:.1f} km/h"
            if current["wind_speed_kmh"] is not None
            else "Unavailable",
            "Open-Meteo weather API",
        )

    with cols[2]:
        metric_card(
            "Air temperature",
            f"{current['air_temperature_c']:.1f} °C"
            if current["air_temperature_c"] is not None
            else "Unavailable",
            "Not sea-surface temperature",
        )

    with cols[3]:
        metric_card(
            "Chlorophyll",
            f"{chlorophyll:.2f} mg/m³"
            if chlorophyll is not None
            else "Unavailable",
            "Requires a verified source/input",
        )

    st.write("")

    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        st.markdown("#### 📊 Available indicator profile")

        chart_rows = []

        for label, value, unit in [
            ("Wave height", current["wave_height_m"], "m"),
            ("Wind speed", current["wind_speed_kmh"], "km/h"),
            ("Air temperature", current["air_temperature_c"], "°C"),
            ("Chlorophyll", chlorophyll, "mg/m³"),
            ("Sea surface temperature", sea_temp, "°C"),
        ]:
            if value is not None:
                chart_rows.append({
                    "Indicator": label,
                    "Value": value,
                    "Unit": unit,
                })

        if chart_rows:
            chart_df = pd.DataFrame(chart_rows)

            fig = px.bar(
                chart_df,
                x="Indicator",
                y="Value",
                color="Indicator",
                hover_data=["Unit"],
                template="plotly_dark",
            )

            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=10, r=10, t=20, b=10),
                showlegend=False,
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No numeric observations are available to chart yet.")

    with right:
        st.markdown("#### 🧠 Assessment snapshot")

        if result:
            reasoning = result["reasoning"]

            st.markdown(
                f"""
                <div class="info-card">
                    <div class="smallcaps">LATEST ASSESSMENT</div>
                    <div style="font-size:1.5rem;font-weight:700;color:#67e8f9;margin:8px 0">
                        {reasoning['status']}
                    </div>
                    <p>{reasoning['summary']}</p>
                    <hr>
                    <p class="muted">{reasoning['basis']}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if result.get("backend_error"):
                st.warning(result["backend_error"])

            if (
                result.get("backend_result")
                and not reasoning.get("backend_used")
            ):
                st.caption(
                    "Backend returned data, but no recognized summary, "
                    "reasoning, or assessment string was found. "
                    "Inspect the raw response in Data & Integrations."
                )

        else:
            st.markdown(
                """
                <div class="info-card">
                    <div class="smallcaps">READY TO ANALYZE</div>
                    <p>
                        Run an assessment to call the configured backend,
                        analyze available inputs, and save a snapshot to
                        Ocean Memory.
                    </p>
                    <p class="muted">
                        Missing data is not replaced with invented values.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("### 🤖 Agent activity")

    if result:
        agent_list = result.get("agents", [])
        cols = st.columns(3)

        icons = ["🌡️", "🟢", "🌬️", "📈", "🛰️"]
        descriptions = [
            "Ocean heat and seasonal context",
            "Chlorophyll and productivity proxy",
            "Weather, wind, waves, and precipitation",
            "Historical comparison and anomalies",
            "Satellite-derived context and coverage",
        ]

        for i, agent in enumerate(agent_list):
            with cols[i % 3]:
                agent_card(
                    icons[i],
                    agent["name"],
                    descriptions[i],
                    agent["finding"],
                    agent["status"],
                )

        st.write("")

        with st.container(border=True):
            st.markdown("#### 🧠 Collaborative Reasoning Agent")
            st.markdown(f"**Assessment:** {result['reasoning']['status']}")
            st.write(result["reasoning"]["summary"])
            st.caption(result["reasoning"]["basis"])

    else:
        cols = st.columns(3)

        previews = [
            (
                "🌡️",
                "Sea Temperature Agent",
                "Temperature needs sea-surface observations and local baselines.",
            ),
            (
                "🟢",
                "Chlorophyll Agent",
                "Chlorophyll needs a verified satellite or in-situ source.",
            ),
            (
                "🌬️",
                "Weather & Wind Agent",
                "Uses available wind and wave data, if returned by the API.",
            ),
            (
                "📈",
                "Historical Trend Agent",
                "Requires a comparable historical time series.",
            ),
            (
                "🛰️",
                "Satellite Intelligence Agent",
                "Requires a connected satellite source.",
            ),
            (
                "🧠",
                "Collaborative Reasoning Agent",
                "Combines agent evidence and makes uncertainty visible.",
            ),
        ]

        for i, (icon, name, description) in enumerate(previews):
            with cols[i % 3]:
                agent_card(
                    icon,
                    name,
                    "Ready / awaiting assessment",
                    description,
                    "READY",
                )

    st.markdown("### 🗺️ Marine region map")

    map_df = pd.DataFrame([
        {
            "region": name,
            "lat": values["lat"],
            "lon": values["lon"],
            "selected": name == region,
        }
        for name, values in REGIONS.items()
    ])

    fig_map = px.scatter_geo(
        map_df,
        lat="lat",
        lon="lon",
        hover_name="region",
        color="selected",
        projection="natural earth",
        template="plotly_dark",
    )

    fig_map.update_traces(
        marker=dict(
            size=11,
            line=dict(width=1, color="#baf7ff"),
        )
    )

    fig_map.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            showocean=True,
            oceancolor="#06263a",
            showland=True,
            landcolor="#163747",
        ),
        margin=dict(l=0, r=0, t=0, b=0),
        height=420,
        showlegend=False,
    )

    st.plotly_chart(fig_map, use_container_width=True)

    st.caption(
        "Markers show representative coordinates, not marine boundaries "
        "or precise data footprints."
    )


# ---------------- Agent Lab ----------------
elif page == "Agent Lab":
    st.markdown("### 🧪 Agent Lab")
    st.write(
        "Each specialist returns its own status, evidence, and explanation. "
        "The reasoning agent combines these outputs after an assessment."
    )

    if not result:
        st.info("Run ORCA Assessment from Mission Control first.")

    else:
        for agent in result.get("agents", []):
            with st.expander(
                f"{agent['name']} — {agent['status']}",
                expanded=True,
            ):
                st.write(agent["finding"])
                st.markdown("**Evidence / input**")
                st.json(agent.get("evidence"))
                st.markdown(
                    f"**Screening level:** {agent.get('level', 'Unknown')}"
                )

        with st.expander(
            "🧠 Collaborative Reasoning Agent",
            expanded=True,
        ):
            reasoning = result["reasoning"]

            st.markdown(f"**{reasoning['status']}**")
            st.write(reasoning["summary"])
            st.write(reasoning["basis"])

            if reasoning.get("flagged"):
                st.markdown("**Indicators requiring follow-up**")

                for item in reasoning["flagged"]:
                    st.write(f"- {item['name']}: {item['finding']}")

            if reasoning.get("missing"):
                st.markdown("**Missing evidence**")

                for item in reasoning["missing"]:
                    st.write(f"- {item['name']}: {item['finding']}")

        if result.get("backend_result"):
            with st.expander("Raw response from existing FastAPI backend"):
                st.json(result["backend_result"])


# ---------------- Two Worlds ----------------
elif page == "Two Worlds":
    st.markdown("### 🌍 Two Worlds. One Ocean.")

    st.write(
        "Ocean and atmosphere are connected. Ecological consequences need "
        "direct observations and should not be inferred from physical "
        "indicators alone."
    )

    below, above = st.columns(2, gap="large")

    with below:
        st.markdown(
            """
            <div class="info-card">
                <div class="smallcaps">WORLD 01 · SUBSURFACE + OCEAN</div>
                <div style="font-size:2.2rem;margin:8px 0">🐠 🪸 🐢 🐋</div>
                <h3>Life Below the Water</h3>
                <ul>
                    <li><b>Fish and biodiversity:</b> use surveys, acoustic,
                    catch, or observation data to investigate distribution.</li>
                    <li><b>Coral reefs and habitats:</b> combine habitat maps
                    with temperature and field observations.</li>
                    <li><b>Plankton:</b> interpret chlorophyll as a proxy,
                    not a direct species count.</li>
                    <li><b>Turtles and marine mammals:</b> require sightings,
                    tracking, or validated biodiversity records.</li>
                    <li><b>Habitat stress:</b> identify conditions for
                    investigation, not confirmed damage.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with above:
        st.markdown(
            """
            <div class="info-card">
                <div class="smallcaps">WORLD 02 · ATMOSPHERE + SURFACE</div>
                <div style="font-size:2.2rem;margin:8px 0">🐦 🌦️ 🌬️ 🚤</div>
                <h3>Life Above the Water</h3>
                <ul>
                    <li><b>Seabirds and coastal wildlife:</b> require
                    wildlife sightings and habitat records.</li>
                    <li><b>Weather and wind:</b> use forecasts and
                    observations for environmental context.</li>
                    <li><b>Ocean surface:</b> use waves, sea state,
                    and satellite-derived products where available.</li>
                    <li><b>Coastal communities:</b> combine official
                    advisories with locally relevant information.</li>
                    <li><b>Marine safety:</b> defer to official marine
                    warnings and authorities.</li>
                </ul>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown("#### 🔗 How ORCA connects the worlds")

    st.markdown(
        """
        <div class="report-card">
            <b>
                Observed condition → possible mechanism → ecological evidence
                → confidence → next action
            </b>
            <p>
                Example: an observed temperature anomaly may affect habitat
                suitability. ORCA should check local habitat and species
                observations before claiming an impact. If those observations
                are missing, the report should explicitly say so.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.caption(
        "Species and habitat impacts are not generated from temperature, "
        "wind, or chlorophyll alone in this prototype."
    )


# ---------------- Ocean Memory ----------------
elif page == "Ocean Memory":
    st.markdown("### 🧠 Ocean Memory")

    st.write(
        "Ocean Memory stores recent assessment snapshots in the current "
        "Streamlit session. It is not permanent storage and resets when "
        "the session or server restarts."
    )

    history = st.session_state.get("orca_history", [])

    if history:
        hist_df = pd.DataFrame(history)

        st.dataframe(
            hist_df,
            use_container_width=True,
            hide_index=True,
        )

        if "temperature_c" in hist_df:
            valid_temp = hist_df.dropna(subset=["temperature_c"])
        else:
            valid_temp = pd.DataFrame()

        if not valid_temp.empty:
            fig = px.line(
                valid_temp,
                x="time",
                y="temperature_c",
                color="region",
                markers=True,
                template="plotly_dark",
                title="Recorded temperature inputs",
            )

            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
            )

            st.plotly_chart(fig, use_container_width=True)

        st.download_button(
            "Download Ocean Memory CSV",
            hist_df.to_csv(index=False).encode("utf-8"),
            "orca_ocean_memory.csv",
            "text/csv",
        )

        if st.button("Clear Ocean Memory"):
            st.session_state["orca_history"] = []
            st.rerun()

    else:
        st.info(
            "No assessments saved in this session. "
            "Run an assessment to create the first snapshot."
        )

    st.markdown("#### Future enhancement")

    st.write(
        "For persistent memory across users and deployments, store records "
        "in a database such as PostgreSQL, Supabase, or your existing database."
    )


# ---------------- Evidence Report ----------------
elif page == "Evidence Report":
    st.markdown("### 📄 Evidence-to-Action Report")

    if not result:
        st.info("Run an assessment first to create a report.")

    else:
        report = {
            "title": "ORCA Marine Ecosystem Assessment",
            "generated_at_utc": result["timestamp"],
            "region": result["region"],
            "coordinates": result["coordinates"],
            "data_source": result["data_source"],
            "current_conditions": result["current_conditions"],
            "agents": result["agents"],
            "reasoning": result["reasoning"],
            "backend_result": result.get("backend_result"),
            "limitations": [
                "Broad screening rules are not a validated ecological risk model.",
                "Missing values are not inferred or fabricated.",
                "Marine-life impacts require species or habitat evidence.",
                "The app is not an official warning or safety service.",
            ],
        }

        st.markdown(
            f"#### {result['region']} — {result['reasoning']['status']}"
        )

        st.write(result["reasoning"]["summary"])

        st.markdown("**Evidence received**")
        st.json(result["current_conditions"])

        st.markdown("**Recommended next steps**")

        st.markdown(
            """
            1. Verify source, timestamp, units, and spatial coverage.
            2. Compare observations against a documented seasonal baseline.
            3. Check species and habitat records before describing impacts.
            4. Investigate conflicting agent results and record uncertainty.
            5. Use official marine forecasts for operational safety decisions.
            """
        )

        st.download_button(
            "⬇️ Download complete JSON report",
            to_json_download(report),
            "orca_assessment_report.json",
            "application/json",
        )

        markdown_report = f"""# ORCA Marine Ecosystem Assessment

- **Region:** {result['region']}
- **Generated (UTC):** {result['timestamp']}
- **Data source status:** {result['data_source']}
- **Assessment:** {result['reasoning']['status']}

## Reasoning summary
{result['reasoning']['summary']}

## Evidence
```json
{json.dumps(result['current_conditions'], indent=2, default=str)}
```

## Agent findings
""" + "\n".join(
            [
                f"- **{agent['name']} — {agent['status']}:** "
                f"{agent['finding']}"
                for agent in result["agents"]
            ]
        ) + """

## Recommended next steps
- Verify data source, time, units, and spatial coverage.
- Compare against a documented seasonal and regional baseline.
- Check species and habitat records before making ecological claims.
- Record uncertainty and investigate conflicting evidence.

## Limitations
This prototype is not a validated ecological forecasting system or official warning service.
"""

        st.download_button(
            "⬇️ Download Markdown report",
            markdown_report,
            "orca_assessment_report.md",
            "text/markdown",
        )


# ---------------- Data & Integrations ----------------
elif page == "Data & Integrations":
    st.markdown("### 🔌 Data & Integrations")
    st.markdown("#### Source status")

    st.write(f"**Open-Meteo request status:** {api_data.get('source', 'unavailable')}")

    st.write(
        f"**Selected region coordinates:** "
        f"{coordinates['lat']}, {coordinates['lon']}"
    )

    if api_data.get("errors"):
        for error in api_data["errors"]:
            st.warning(error)

    st.markdown("#### Existing FastAPI backend")

    st.write(
        "The app calls POST /api/assess when ORCA_API_URL is configured. "
        "It sends region, coordinates, available API data, and optional inputs."
    )

    st.code(
        'ORCA_API_URL = "https://your-deployed-backend.example.com"',
        language="toml",
    )

    st.write(
        "In Streamlit Community Cloud, open App settings → Secrets and set:"
    )

    st.code(
        'ORCA_API_URL = "https://your-deployed-backend.example.com"',
        language="toml",
    )

    st.warning(
        "Replace the example URL with your actual deployed FastAPI URL. "
        "Do not use localhost for a cloud deployment."
    )

    if result and result.get("backend_result"):
        st.markdown("#### Last backend response")
        st.json(result["backend_result"])

    elif result and result.get("backend_error"):
        st.error(result["backend_error"])

    else:
        st.info(
            "The backend is called when you run an assessment. "
            "Without a configured URL, the app uses transparent local "
            "screening functions."
        )

    st.markdown("#### Data limitations")

    st.markdown(
        """
        - Open-Meteo may return wave and weather variables but not every marine variable.
        - Air temperature is not sea-surface temperature.
        - Chlorophyll and species observations are not fabricated when unavailable.
        - Satellite status is manually configured here; it does not prove a feed is connected.
        - A backend response is displayed raw if its schema differs from the expected fields.
        """
    )


# ---------------- Footer ----------------
st.divider()

st.markdown(
    """
    <div style="display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;color:#789bad;font-size:.78rem">
        <span>ORCA · Marine Ecosystem Reasoning with Collaborative Agents</span>
        <span>Evidence-aware prototype · Not a validated alert system</span>
    </div>
    """,
    unsafe_allow_html=True,
)

