
from __future__ import annotations

import json
import os
import html
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st


# ============================================================
# ORCA — Marine Ecosystem Reasoning with Collaborative Agents
# Complete Streamlit application
# ============================================================

st.set_page_config(
    page_title="ORCA | Marine Ecosystem Intelligence",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- Configuration ----------------

REGIONS = {
    "Arabian Sea": {"lat": 17.0, "lon": 64.0},
    "Bay of Bengal": {"lat": 15.0, "lon": 88.0},
    "Indian Ocean": {"lat": -10.0, "lon": 75.0},
    "Andaman Sea": {"lat": 10.0, "lon": 96.0},
    "North Atlantic": {"lat": 40.0, "lon": -35.0},
    "Coral Triangle": {"lat": -2.0, "lon": 125.0},
    "Gulf of Mexico": {"lat": 24.0, "lon": -90.0},
    "Southern Ocean": {"lat": -55.0, "lon": 30.0},
}

TIMEOUT = 25

try:
    BACKEND_URL = str(
        st.secrets.get("ORCA_API_URL", os.getenv("ORCA_API_URL", ""))
    ).strip().rstrip("/")
except Exception:
    BACKEND_URL = os.getenv("ORCA_API_URL", "").strip().rstrip("/")

st.session_state.setdefault("orca_result", None)
st.session_state.setdefault("orca_history", [])


# ---------------- Styling ----------------

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

    .stApp {
        background:
            radial-gradient(circle at 10% 0%, #103b4a 0%, transparent 30%),
            linear-gradient(180deg, #061421, #081d2d 60%, #061421);
        color: #edf8ff;
    }

    [data-testid="stSidebar"] {
        background: #081b29;
        border-right: 1px solid #21445a;
    }

    h1, h2, h3, h4 {
        font-family: 'Space Grotesk', sans-serif !important;
        color: #f0fbff !important;
    }

    p, label {
        color: #d0e4ef;
    }

    .orca-hero {
        padding: 30px;
        border-radius: 22px;
        border: 1px solid #246074;
        background: linear-gradient(120deg, #0b4052, #0a2339);
        margin-bottom: 20px;
    }

    .eyebrow {
        color: #67e8f9;
        font-size: .78rem;
        letter-spacing: .17em;
        font-weight: 800;
        text-transform: uppercase;
    }

    .hero-title {
        font-family: 'Space Grotesk', sans-serif;
        font-size: clamp(2.2rem, 5vw, 3.8rem);
        line-height: 1.05;
        font-weight: 700;
        margin: 14px 0;
    }

    .hero-copy {
        color: #c6e4ef;
        max-width: 850px;
        font-size: 1rem;
    }

    .chip {
        display: inline-block;
        padding: 5px 10px;
        margin: 5px 5px 0 0;
        border-radius: 20px;
        background: #103b4a;
        color: #a5f3fc;
        border: 1px solid #286071;
        font-size: .75rem;
        font-weight: 700;
    }

    .metric-card, .agent-card, .info-card {
        padding: 18px;
        border-radius: 16px;
        border: 1px solid #214b60;
        background: linear-gradient(145deg, #102e42, #0a2031);
        margin-bottom: 10px;
    }

    .metric-label {
        color: #9ab9c9;
        font-size: .75rem;
        letter-spacing: .09em;
        text-transform: uppercase;
    }

    .metric-value {
        font-family: 'Space Grotesk', sans-serif;
        color: #f0fbff;
        font-size: 1.55rem;
        font-weight: 700;
        margin: 8px 0;
        overflow-wrap: anywhere;
    }

    .metric-note {
        color: #83dbe7;
        font-size: .8rem;
    }

    .muted {
        color: #91b5c6;
        font-size: .85rem;
    }

    .smallcaps {
        color: #67e8f9;
        font-size: .74rem;
        font-weight: 800;
        letter-spacing: .12em;
        text-transform: uppercase;
    }

    div[data-testid="stButton"] button,
    div[data-testid="stDownloadButton"] button {
        background: linear-gradient(90deg, #06b6d4, #2dd4bf);
        color: #041925;
        font-weight: 800;
        border: none;
        border-radius: 10px;
        min-height: 42px;
    }

    hr {
        border-color: #21445a;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------- General helpers ----------------

def safe_float(value: Any) -> float | None:
    """Return a float or None for blank/invalid input."""
    if value is None:
        return None

    try:
        text_value = str(value).strip()
        if not text_value:
            return None
        return float(text_value)
    except (ValueError, TypeError):
        return None


def display_value(value: Any, unit: str = "") -> str:
    """Format a value without displaying None as a measurement."""
    if value is None:
        return "Unavailable"
    return f"{value:.2f} {unit}".strip()


def safe_json(value: Any) -> str:
    """Serialize values safely for st.code, including missing values."""
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def show_evidence(value: Any) -> None:
    """Avoid passing None or arbitrary objects directly into st.json."""
    if value is None:
        st.info("No evidence available for this agent yet.")
        return

    try:
        st.code(safe_json(value), language="json")
    except (TypeError, ValueError):
        st.write(str(value))


def metric_card(label: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{html.escape(label)}</div>
            <div class="metric-value">{html.escape(value)}</div>
            <div class="metric-note">{html.escape(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def agent_card(
    icon: str,
    name: str,
    description: str,
    finding: str,
    status: str,
) -> None:
    st.markdown(
        f"""
        <div class="agent-card">
            <div style="font-size:1.7rem">{html.escape(icon)}</div>
            <div style="font-weight:700;color:#effaff;margin-top:8px">
                {html.escape(name)}
            </div>
            <div class="muted" style="margin:5px 0 10px">
                {html.escape(description)}
            </div>
            <div class="chip">{html.escape(status)}</div>
            <p style="margin-top:12px">{html.escape(finding)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------- Live marine and weather data ----------------

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_live_data(lat: float, lon: float) -> dict[str, Any]:
    """Fetch available Open-Meteo marine and weather observations."""

    result = {
        "source": "unavailable",
        "marine": {},
        "weather": {},
        "errors": [],
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        response = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "wave_height,wave_direction,wave_period",
                "hourly": "wave_height",
                "forecast_days": 2,
                "timezone": "UTC",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        result["marine"] = response.json()

    except (requests.RequestException, ValueError) as exc:
        result["errors"].append(f"Marine API: {exc}")

    try:
        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "current": (
                    "temperature_2m,relative_humidity_2m,"
                    "wind_speed_10m,wind_direction_10m,precipitation"
                ),
                "hourly": "wind_speed_10m",
                "forecast_days": 2,
                "timezone": "UTC",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        result["weather"] = response.json()

    except (requests.RequestException, ValueError) as exc:
        result["errors"].append(f"Weather API: {exc}")

    if result["marine"] or result["weather"]:
        result["source"] = "Open-Meteo live API"

    return result


def extract_conditions(data: dict[str, Any]) -> dict[str, Any]:
    marine = data.get("marine", {}).get("current", {}) or {}
    weather = data.get("weather", {}).get("current", {}) or {}

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


# ---------------- FastAPI integration ----------------

def call_backend(
    region: str,
    lat: float,
    lon: float,
    marine_data: dict[str, Any],
) -> tuple[dict[str, Any] | None, str | None]:
    """Call the existing backend when ORCA_API_URL is configured."""

    if not BACKEND_URL:
        return None, "Backend URL is not configured."

    payload = {
        "region": region,
        "latitude": lat,
        "longitude": lon,
        "marine_data": marine_data,
    }

    try:
        response = requests.post(
            f"{BACKEND_URL}/api/assess",
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict):
            return data, None

        return {"backend_response": data}, None

    except requests.RequestException as exc:
        return None, f"Backend request failed: {exc}"

    except ValueError as exc:
        return None, f"Backend returned invalid JSON: {exc}"


# ---------------- Agent 1: Sea temperature ----------------

def temperature_agent(sst: float | None) -> dict[str, Any]:
    if sst is None:
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

    if sst >= 30:
        status, level = "SCREENING FLAG", "Attention"
        finding = (
            f"Sea-surface temperature is {sst:.1f} °C. "
            "Compare with local seasonal climatology before drawing conclusions."
        )
    else:
        status, level = "OBSERVATION RECEIVED", "Context needed"
        finding = (
            f"Sea-surface temperature is {sst:.1f} °C. "
            "Interpret using local seasonal and habitat baselines."
        )

    return {
        "name": "Sea Temperature Agent",
        "status": status,
        "finding": finding,
        "evidence": {"sea_surface_temperature_c": sst},
        "level": level,
    }


# ---------------- Agent 2: Chlorophyll ----------------

def chlorophyll_agent(chl: float | None) -> dict[str, Any]:
    if chl is None:
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

    if chl >= 5:
        status, level = "SCREENING FLAG", "Attention"
        finding = (
            f"Chlorophyll is {chl:.2f} mg/m³. Check local baselines and "
            "validated bloom products. This alone does not confirm a harmful bloom."
        )
    else:
        status, level = "OBSERVATION RECEIVED", "Context needed"
        finding = (
            f"Chlorophyll is {chl:.2f} mg/m³. Interpret with season, "
            "water type, satellite quality, and local reference values."
        )

    return {
        "name": "Chlorophyll Agent",
        "status": status,
        "finding": finding,
        "evidence": {"chlorophyll_mg_m3": chl},
        "level": level,
    }


# ---------------- Agent 3: Weather and wind ----------------

def weather_agent(conditions: dict[str, Any]) -> dict[str, Any]:
    wind = conditions.get("wind_speed_kmh")
    wave = conditions.get("wave_height_m")
    precipitation = conditions.get("precipitation_mm")

    if wind is None and wave is None and precipitation is None:
        return {
            "name": "Weather & Wind Agent",
            "status": "DATA MISSING",
            "finding": "No usable wind, wave, or precipitation observations were returned.",
            "evidence": None,
            "level": "Unknown",
        }

    details = []

    if wind is not None:
        details.append(f"wind {wind:.1f} km/h")

    if wave is not None:
        details.append(f"waves {wave:.2f} m")

    if precipitation is not None:
        details.append(f"precipitation {precipitation:.1f} mm")

    flag = (
        (wind is not None and wind >= 35)
        or (wave is not None and wave >= 3)
    )

    return {
        "name": "Weather & Wind Agent",
        "status": "SCREENING FLAG" if flag else "OBSERVATIONS RECEIVED",
        "finding": (
            "Available conditions: "
            + ", ".join(details)
            + ". Use official marine forecasts for safety decisions."
        ),
        "evidence": {
            "wind_kmh": wind,
            "wave_height_m": wave,
            "precipitation_mm": precipitation,
        },
        "level": "Attention" if flag else "Context needed",
    }


# ---------------- Agent 4: Historical trends ----------------

def historical_agent(deviation: float | None) -> dict[str, Any]:
    if deviation is None:
        return {
            "name": "Historical Trend Agent",
            "status": "BASELINE NEEDED",
            "finding": (
                "No historical anomaly value was provided. A valid trend "
                "requires comparable time-series data and a documented baseline."
            ),
            "evidence": None,
            "level": "Unknown",
        }

    flag = abs(deviation) >= 10

    return {
        "name": "Historical Trend Agent",
        "status": "SCREENING FLAG" if flag else "OBSERVATION RECEIVED",
        "finding": (
            f"Supplied historical deviation is {deviation:.1f}%. "
            "Verify its source, period, units, and baseline."
        ),
        "evidence": {"historical_deviation_pct": deviation},
        "level": "Attention" if flag else "Context needed",
    }


# ---------------- Agent 5: Satellite intelligence ----------------

def satellite_agent(
    status: str,
    note: str,
) -> dict[str, Any]:
    if status == "Unavailable":
        return {
            "name": "Satellite Intelligence Agent",
            "status": "UNAVAILABLE",
            "finding": (
                "No satellite feed is connected. Add a verified satellite "
                "source or return satellite observations from FastAPI."
            ),
            "evidence": None,
            "level": "Unknown",
        }

    return {
        "name": "Satellite Intelligence Agent",
        "status": status.upper(),
        "finding": (
            note.strip()
            or "Satellite status was entered manually. Verify source, "
            "timestamp, coverage, and observation quality."
        ),
        "evidence": {
            "status": status,
            "observation_note": note.strip() or None,
        },
        "level": "Context needed",
    }


# ---------------- Agent 6: Collaborative reasoning ----------------

def reasoning_agent(
    agents: list[dict[str, Any]],
    backend: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combine specialist outputs without treating missing data as safe."""

    if backend:
        for key in ("summary", "reasoning", "assessment"):
            value = backend.get(key)
            if isinstance(value, str) and value.strip():
                return {
                    "status": "Backend assessment",
                    "summary": value,
                    "basis": (
                        "Summary returned by the configured FastAPI backend. "
                        "Review its supporting evidence and assumptions."
                    ),
                    "backend_used": True,
                }

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

    if len(flagged) >= 2:
        status = "Elevated attention"
        summary = (
            "Multiple available indicators crossed broad screening "
            "thresholds. Verify the measurements and investigate further."
        )
    elif len(flagged) == 1:
        status = "Watch"
        summary = (
            "One available indicator crossed a broad screening threshold. "
            "Check its source and compare it with local baselines."
        )
    elif not available:
        status = "Insufficient data"
        summary = (
            "There is not enough usable evidence for a meaningful assessment. "
            "Connect marine observations or configure the FastAPI backend."
        )
    elif missing:
        status = "Assessment incomplete"
        summary = (
            "Some available indicators can be reviewed, but important "
            "evidence is missing. Do not interpret the absence of flags "
            "as proof that the ecosystem is healthy."
        )
    else:
        status = "No broad screening flags"
        summary = (
            "No broad screening threshold was crossed in the available "
            "indicators. This does not establish that the ecosystem is healthy."
        )

    return {
        "status": status,
        "summary": summary,
        "basis": (
            "This fallback uses transparent screening rules, not a trained "
            "or clinically/ecologically validated predictive model."
        ),
        "flagged": flagged,
        "missing": missing,
        "backend_used": False,
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown("# 🌊 ORCA")
    st.caption("Ocean Reasoning Collaborative Agency")
    st.divider()

    page = st.radio(
        "Navigation",
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

    region = st.selectbox("Marine region", list(REGIONS.keys()))
    coords = REGIONS[region]

    use_live = st.toggle("Fetch live marine/weather data", value=True)

    st.caption(
        "Live values depend on API availability and regional coverage."
    )

    st.divider()
    st.markdown("### Manual observations")

    sst_text = st.text_input(
        "Sea-surface temperature (°C)",
        placeholder="Leave blank if unavailable",
        help="Enter verified sea-surface temperature, not air temperature.",
    )

    chl_text = st.text_input(
        "Chlorophyll (mg/m³)",
        placeholder="Leave blank if unavailable",
        help="Enter a verified chlorophyll concentration.",
    )

    historical_text = st.text_input(
        "Historical deviation (%)",
        placeholder="Leave blank if unavailable",
    )

    satellite_status = st.selectbox(
        "Satellite data status",
        ["Unavailable", "Connected", "Cached"],
    )

    satellite_note = st.text_input(
        "Satellite observation note",
        placeholder="Source, timestamp, observation",
    )

    st.divider()

    if BACKEND_URL:
        st.success("FastAPI URL configured")
        st.caption(BACKEND_URL)
    else:
        st.warning("FastAPI URL not configured")
        st.caption("Set ORCA_API_URL in Streamlit Secrets to enable it.")


# Parse optional manual inputs.
sst = safe_float(sst_text)
chl = safe_float(chl_text)
historical_deviation = safe_float(historical_text)


# ============================================================
# FETCH AVAILABLE DATA
# ============================================================

live_data = {
    "source": "disabled",
    "marine": {},
    "weather": {},
    "errors": [],
}

if use_live:
    with st.spinner("Loading available marine and weather observations..."):
        live_data = fetch_live_data(coords["lat"], coords["lon"])

conditions = extract_conditions(live_data)


# ============================================================
# HEADER
# ============================================================

st.markdown(
    f"""
    <div class="orca-hero">
        <div class="eyebrow">Marine Ecosystem Intelligence Platform</div>
        <div class="hero-title">
            Read the ocean.<br>
            <span style="color:#67e8f9">Connect both worlds.</span>
        </div>
        <div class="hero-copy">
            ORCA brings together marine observations and six collaborative
            agents to investigate ocean conditions, make uncertainty visible,
            and support understanding of life below and above the water.
        </div>
        <div style="margin-top:15px">
            <span class="chip">📍 {html.escape(region)}</span>
            <span class="chip">🤖 SIX AGENTS</span>
            <span class="chip">🌊 ABOVE + BELOW WATER</span>
            <span class="chip">🔎 EVIDENCE FIRST</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    "Updated: "
    + datetime.now().astimezone().strftime("%d %b %Y · %I:%M:%S %p %Z")
)


# ============================================================
# RUN ASSESSMENT
# ============================================================

if st.button(
    "🚀 Run ORCA Assessment",
    type="primary",
    use_container_width=True,
):
    backend_payload = {
        "open_meteo": live_data,
        "current_conditions": conditions,
        "manual_inputs": {
            "sea_surface_temperature_c": sst,
            "chlorophyll_mg_m3": chl,
            "historical_deviation_pct": historical_deviation,
            "satellite_status": satellite_status,
            "satellite_note": satellite_note,
        },
    }

    with st.spinner("Running six collaborative agents..."):
        backend_result, backend_error = call_backend(
            region,
            coords["lat"],
            coords["lon"],
            backend_payload,
        )

        agents = [
            temperature_agent(sst),
            chlorophyll_agent(chl),
            weather_agent(conditions),
            historical_agent(historical_deviation),
            satellite_agent(satellite_status, satellite_note),
        ]

        reasoning = reasoning_agent(agents, backend_result)

        assessment = {
            "region": region,
            "coordinates": coords,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data_source": live_data.get("source", "unavailable"),
            "current_conditions": conditions,
            "agents": agents,
            "reasoning": reasoning,
            "backend_result": backend_result,
            "backend_error": backend_error,
        }

        st.session_state["orca_result"] = assessment

        st.session_state["orca_history"].append({
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "region": region,
            "assessment": reasoning["status"],
            "wave_height_m": conditions["wave_height_m"],
            "wind_speed_kmh": conditions["wind_speed_kmh"],
            "air_temperature_c": conditions["air_temperature_c"],
            "sea_surface_temperature_c": sst,
            "chlorophyll_mg_m3": chl,
            "data_source": live_data.get("source", "unavailable"),
        })

        st.session_state["orca_history"] = (
            st.session_state["orca_history"][-100:]
        )

    st.success("Assessment complete. Review the findings and missing evidence below.")


result = st.session_state.get("orca_result")

if result and result["region"] != region:
    st.info(
        "The displayed assessment belongs to another region. "
        "Run the assessment again to update it for the selected region."
    )


# ============================================================
# PAGE 1 — MISSION CONTROL
# ============================================================

if page == "Mission Control":
    st.markdown("## Mission Control")

    if live_data.get("source") == "Open-Meteo live API":
        st.success("At least one live data endpoint returned a response.")
    elif use_live:
        st.warning(
            "Live data could not be retrieved. Check the API errors below."
        )
    else:
        st.info("Live data fetching is disabled.")

    cols = st.columns(4)

    with cols[0]:
        metric_card(
            "Wave height",
            display_value(conditions["wave_height_m"], "m"),
            "Marine API",
        )

    with cols[1]:
        metric_card(
            "Wind speed",
            display_value(conditions["wind_speed_kmh"], "km/h"),
            "Weather API",
        )

    with cols[2]:
        metric_card(
            "Air temperature",
            display_value(conditions["air_temperature_c"], "°C"),
            "Not sea-surface temperature",
        )

    with cols[3]:
        metric_card(
            "Chlorophyll",
            display_value(chl, "mg/m³"),
            "Verified input required",
        )

    st.markdown("### Available indicator profile")

    chart_data = []

    for label, value, unit in [
        ("Wave height", conditions["wave_height_m"], "m"),
        ("Wind speed", conditions["wind_speed_kmh"], "km/h"),
        ("Air temperature", conditions["air_temperature_c"], "°C"),
        ("Sea-surface temperature", sst, "°C"),
        ("Chlorophyll", chl, "mg/m³"),
    ]:
        if value is not None:
            chart_data.append({
                "Indicator": label,
                "Value": value,
                "Unit": unit,
            })

    if chart_data:
        chart_df = pd.DataFrame(chart_data)

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
            showlegend=False,
            margin=dict(l=10, r=10, t=25, b=10),
        )

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No numeric observations are available to chart.")

    st.markdown("### Collaborative assessment")

    if result:
        reasoning = result["reasoning"]

        st.markdown(f"#### {reasoning['status']}")
        st.write(reasoning["summary"])
        st.caption(reasoning["basis"])

        if result.get("backend_error"):
            st.warning(result["backend_error"])

        st.markdown("### Agent activity")

        icons = ["🌡️", "🟢", "🌬️", "📈", "🛰️"]
        descriptions = [
            "Sea-surface temperature",
            "Chlorophyll and productivity proxy",
            "Wind, waves, and weather",
            "Historical anomalies",
            "Satellite observations",
        ]

        agent_cols = st.columns(3)

        for index, agent in enumerate(result["agents"]):
            with agent_cols[index % 3]:
                agent_card(
                    icons[index],
                    agent["name"],
                    descriptions[index],
                    agent["finding"],
                    agent["status"],
                )

        st.markdown("### 🧠 Reasoning Agent")
        st.write(reasoning["summary"])

        if reasoning.get("missing"):
            st.markdown("#### Missing evidence")
            for agent in reasoning["missing"]:
                st.write(f"- **{agent['name']}:** {agent['finding']}")

    else:
        st.info("Click **Run ORCA Assessment** to activate the agents.")

    st.markdown("### Marine region map")

    map_df = pd.DataFrame([
        {
            "Region": name,
            "Latitude": item["lat"],
            "Longitude": item["lon"],
            "Selected": name == region,
        }
        for name, item in REGIONS.items()
    ])

    fig_map = px.scatter_geo(
        map_df,
        lat="Latitude",
        lon="Longitude",
        color="Selected",
        hover_name="Region",
        projection="natural earth",
        template="plotly_dark",
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
        margin=dict(l=0, r=0, t=10, b=0),
        height=400,
    )

    st.plotly_chart(fig_map, use_container_width=True)

    with st.expander("Debug live data response"):
        st.write("Source:", live_data.get("source"))
        st.write("Current conditions:")
        show_evidence(conditions)
        st.write("API errors:")
        show_evidence(live_data.get("errors", []))


# ============================================================
# PAGE 2 — AGENT LAB
# ============================================================

elif page == "Agent Lab":
    st.markdown("## 🧪 Agent Lab")
    st.write(
        "Inspect each specialist's finding, status, and evidence. "
        "Unavailable data is explicitly identified."
    )

    if not result:
        st.info("Run an ORCA assessment first.")
    else:
        for agent in result["agents"]:
            with st.expander(
                f"{agent['name']} — {agent['status']}",
                expanded=True,
            ):
                st.write(agent["finding"])
                st.markdown("**Evidence / input**")
                show_evidence(agent.get("evidence"))
                st.markdown(
                    f"**Screening level:** {agent.get('level', 'Unknown')}"
                )

        st.markdown("### 🧠 Collaborative Reasoning Agent")
        reasoning = result["reasoning"]

        st.markdown(f"**Assessment:** {reasoning['status']}")
        st.write(reasoning["summary"])
        st.caption(reasoning["basis"])

        if reasoning.get("missing"):
            st.markdown("#### Missing evidence")

            for agent in reasoning["missing"]:
                st.write(f"- {agent['name']}: {agent['finding']}")

        if result.get("backend_result") is not None:
            with st.expander("Raw FastAPI backend response"):
                show_evidence(result["backend_result"])

        if result.get("backend_error"):
            st.warning(result["backend_error"])


# ============================================================
# PAGE 3 — TWO WORLDS
# ============================================================

elif page == "Two Worlds":
    st.markdown("## 🌍 Two Worlds. One Ocean.")
    st.write(
        "Marine conditions connect the atmosphere, ocean surface, "
        "underwater habitats, wildlife, and coastal communities."
    )

    left, right = st.columns(2, gap="large")

    with left:
        st.markdown(
            """
            <div class="info-card">
                <div class="smallcaps">WORLD 01 · UNDERWATER</div>
                <div style="font-size:2rem;margin:12px 0">🐠 🪸 🐢 🐋</div>
                <h3>Life Below the Water</h3>
                <p><b>Fish and biodiversity</b> — require surveys or sightings.</p>
                <p><b>Coral reefs</b> — need habitat maps and field observations.</p>
                <p><b>Plankton</b> — chlorophyll is a proxy, not a species count.</p>
                <p><b>Marine mammals</b> — require verified sightings or tracking.</p>
                <p><b>Habitat stress</b> — should be investigated, not assumed.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            """
            <div class="info-card">
                <div class="smallcaps">WORLD 02 · ABOVE WATER</div>
                <div style="font-size:2rem;margin:12px 0">🐦 🌦️ 🌬️ 🚤</div>
                <h3>Life Above the Water</h3>
                <p><b>Seabirds</b> — require sightings and habitat records.</p>
                <p><b>Weather and wind</b> — provide environmental context.</p>
                <p><b>Ocean surface</b> — waves and satellite products help describe conditions.</p>
                <p><b>Coastal communities</b> — need locally relevant observations.</p>
                <p><b>Marine safety</b> — follow official forecasts and warnings.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### How ORCA connects both worlds")

    st.markdown(
        """
        **Observation → Possible mechanism → Ecological evidence → Confidence → Next action**

        Example: a sea-temperature anomaly may affect habitat suitability.
        ORCA should check habitat and species observations before claiming
        an impact. If that evidence is unavailable, the report must say so.
        """
    )


# ============================================================
# PAGE 4 — OCEAN MEMORY
# ============================================================

elif page == "Ocean Memory":
    st.markdown("## 🧠 Ocean Memory")
    st.write(
        "This history is held in the current Streamlit session. "
        "It is not permanent database storage."
    )

    history = st.session_state["orca_history"]

    if history:
        history_df = pd.DataFrame(history)

        st.dataframe(
            history_df,
            use_container_width=True,
            hide_index=True,
        )

        st.download_button(
            "Download Ocean Memory CSV",
            history_df.to_csv(index=False).encode("utf-8"),
            "orca_ocean_memory.csv",
            "text/csv",
        )

        if st.button("Clear Ocean Memory"):
            st.session_state["orca_history"] = []
            st.rerun()

    else:
        st.info("No assessments recorded in this session yet.")

    st.caption(
        "For permanent historical trends, store timestamped observations "
        "in a database and compare consistent measurements over time."
    )


# ============================================================
# PAGE 5 — EVIDENCE REPORT
# ============================================================

elif page == "Evidence Report":
    st.markdown("## 📄 Evidence-to-Action Report")

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
                "Screening rules are not a validated ecological risk model.",
                "Missing values are not invented.",
                "Air temperature is not sea-surface temperature.",
                "Marine-life impacts require species or habitat evidence.",
                "This prototype is not an official warning service.",
            ],
        }

        st.markdown(
            f"### {result['region']} — {result['reasoning']['status']}"
        )

        st.write(result["reasoning"]["summary"])

        st.markdown("### Available conditions")
        show_evidence(result["current_conditions"])

        st.markdown("### Agent findings")

        for agent in result["agents"]:
            st.markdown(f"**{agent['name']} — {agent['status']}**")
            st.write(agent["finding"])

        st.markdown("### Recommended next steps")
        st.markdown(
            """
            1. Verify data source, timestamp, units, and coverage.
            2. Compare readings with a documented regional baseline.
            3. Check species and habitat observations before claiming ecological impacts.
            4. Investigate missing or conflicting data.
            5. Follow official marine forecasts for safety decisions.
            """
        )

        st.download_button(
            "⬇️ Download complete JSON report",
            data=safe_json(report),
            file_name="orca_assessment_report.json",
            mime="application/json",
        )

        markdown_report = (
            f"# ORCA Marine Ecosystem Assessment\n\n"
            f"- **Region:** {result['region']}\n"
            f"- **Generated (UTC):** {result['timestamp']}\n"
            f"- **Data source:** {result['data_source']}\n"
            f"- **Assessment:** {result['reasoning']['status']}\n\n"
            f"## Summary\n\n{result['reasoning']['summary']}\n\n"
            f"## Conditions\n\n```json\n"
            f"{safe_json(result['current_conditions'])}\n```\n\n"
            f"## Agent findings\n\n"
            + "\n".join(
                f"- **{agent['name']} — {agent['status']}:** {agent['finding']}"
                for agent in result["agents"]
            )
            + "\n\n## Limitations\n\n"
            "This prototype is not a validated ecological forecasting system "
            "or an official marine warning service.\n"
        )

        st.download_button(
            "⬇️ Download Markdown report",
            data=markdown_report,
            file_name="orca_assessment_report.md",
            mime="text/markdown",
        )


# ============================================================
# PAGE 6 — DATA & INTEGRATIONS
# ============================================================

elif page == "Data & Integrations":
    st.markdown("## 🔌 Data & Integrations")

    st.markdown("### Current data source")
    st.write("Status:", live_data.get("source", "unavailable"))
    st.write("Coordinates:", coords)

    if live_data.get("errors"):
        st.markdown("### API errors")

        for error in live_data["errors"]:
            st.warning(error)

    st.markdown("### FastAPI backend")

    st.write(
        "If configured, ORCA sends a POST request to `/api/assess` "
        "containing the region, coordinates, available live data, "
        "and optional manual observations."
    )

    st.code(
        '[secrets]\n'
        'ORCA_API_URL = "https://YOUR-DEPLOYED-BACKEND-URL"',
        language="toml",
    )

    st.write(
        "In Streamlit Community Cloud, add the actual backend URL "
        "in the app's Secrets settings. Do not use localhost for a "
        "backend running on another server."
    )

    if result and result.get("backend_result") is not None:
        st.markdown("### Last backend response")
        show_evidence(result["backend_result"])

    if result and result.get("backend_error"):
        st.error(result["backend_error"])

    st.markdown("### Important data limitations")
    st.markdown(
        """
        - Open-Meteo's requests here retrieve available wave and weather variables.
        - Air temperature is not sea-surface temperature.
        - Chlorophyll requires a suitable satellite or in-situ data source.
        - Historical trends require comparable historical observations.
        - Satellite status entered in the sidebar is not proof of a live satellite connection.
        - The local screening functions are transparent rules, not a trained AI model.
        """
    )

    with st.expander("View raw live API response"):
        show_evidence(live_data)


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.markdown(
    """
    <div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:#83a8ba;font-size:.78rem">
        <span>ORCA · Marine Ecosystem Reasoning with Collaborative Agents</span>
        <span>Evidence-aware prototype · Not a validated alert system</span>
    </div>
    """,
    unsafe_allow_html=True,
)


