
import os
import json
from datetime import datetime, timezone

import requests
import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# ORCA - Marine Ecosystem Intelligence
# Six-agent collaborative screening prototype
# =========================================================

st.set_page_config(
    page_title="ORCA | Marine Intelligence",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

REQUEST_TIMEOUT = 20
CACHE_SECONDS = 1800

REGIONS = {
    "Arabian Sea": (15.0, 65.0),
    "Bay of Bengal": (15.0, 88.0),
    "Indian Ocean": (-10.0, 75.0),
    "Andaman Sea": (10.0, 97.0),
    "North Atlantic": (35.0, -40.0),
    "Coral Triangle": (-2.0, 125.0),
    "Gulf of Mexico": (25.0, -90.0),
    "Southern Ocean": (-55.0, 30.0),
}

# ----------------------- Styling -------------------------

st.markdown("""
<style>
.stApp {
    background: linear-gradient(150deg, #071522 0%, #0a2235 55%, #071522 100%);
    color: #eaf6ff;
}
[data-testid="stSidebar"] {
    background: #081827;
    border-right: 1px solid #193c50;
}
h1, h2, h3 {
    color: #e9f7ff !important;
}
p, label, li {
    color: #c2d7e7;
}
.orca-hero {
    padding: 28px;
    border: 1px solid #24516a;
    border-radius: 20px;
    background: linear-gradient(120deg, #10334a, #0b1e30);
    margin-bottom: 20px;
}
.orca-subtitle {
    color: #a7c7dc;
    font-size: 15px;
}
.agent-box {
    background: #0c2435;
    border: 1px solid #24485d;
    border-radius: 15px;
    padding: 16px;
    margin-bottom: 10px;
}
.status {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}
div[data-testid="stMetric"] {
    background: #0c2435;
    border: 1px solid #21465c;
    border-radius: 14px;
    padding: 14px;
}
div[data-testid="stMetric"] label {
    color: #a9c9de !important;
}
hr {
    border-color: #234358;
}
</style>
""", unsafe_allow_html=True)


# ----------------------- Helpers -------------------------

def safe_float(value):
    """Convert a real numeric value to float; otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
        if pd.isna(number):
            return None
        return number
    except (TypeError, ValueError):
        return None


def fmt(value, unit="", digits=2):
    value = safe_float(value)
    if value is None:
        return "Unavailable"
    return f"{value:.{digits}f}{unit}"


def get_nested(data, *keys):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def safe_json(data):
    try:
        return json.dumps(data, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(data)


def show_evidence(title, data):
    """Use plain text rather than Streamlit's JSON syntax renderer."""
    with st.expander(title):
        st.text(safe_json(data))


def agent_card(emoji, title, status, message):
    st.markdown(
        f"""
        <div class="agent-box">
            <div style="font-size:25px">{emoji}</div>
            <h4 style="margin-bottom:6px">{title}</h4>
            <div class="status">{status}</div>
            <p style="margin-top:10px">{message}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# -------------------- Live data API ----------------------

@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def fetch_live_data(latitude, longitude):
    result = {
        "marine": {},
        "marine_hourly": {},
        "weather": {},
        "marine_error": None,
        "weather_error": None,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    marine_url = "https://marine-api.open-meteo.com/v1/marine"

    marine_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "wave_height,wave_direction,wave_period,"
            "sea_surface_temperature,ocean_current_velocity"
        ),
        "hourly": (
            "sea_surface_temperature,wave_height"
        ),
        "past_days": 7,
        "forecast_days": 1,
        "timezone": "UTC",
        "cell_selection": "sea",
    }

    try:
        response = requests.get(
            marine_url,
            params=marine_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()

        result["marine"] = payload.get("current", {}) or {}
        result["marine_hourly"] = payload.get("hourly", {}) or {}

    except Exception as exc:
        result["marine_error"] = str(exc)

    weather_url = "https://api.open-meteo.com/v1/forecast"

    weather_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "temperature_2m,relative_humidity_2m,"
            "wind_speed_10m,wind_direction_10m,precipitation"
        ),
        "timezone": "UTC",
    }

    try:
        response = requests.get(
            weather_url,
            params=weather_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        result["weather"] = payload.get("current", {}) or {}

    except Exception as exc:
        result["weather_error"] = str(exc)

    return result


# ----------------------- Agents --------------------------

def temperature_agent(marine):
    sst = safe_float(marine.get("sea_surface_temperature"))

    if sst is None:
        return {
            "name": "Sea Temperature Agent",
            "status": "DATA MISSING",
            "value": None,
            "message": (
                "No sea-surface temperature was returned. "
                "Air temperature is not a substitute."
            ),
        }

    return {
        "name": "Sea Temperature Agent",
        "status": "OBSERVATION RECEIVED",
        "value": sst,
        "message": (
            f"Marine API reported sea-surface temperature "
            f"of {sst:.2f} °C. This is an observation/model "
            "product, not by itself an ecological health verdict."
        ),
    }


def chlorophyll_agent(chlorophyll):
    value = safe_float(chlorophyll)

    if value is None:
        return {
            "name": "Chlorophyll Agent",
            "status": "DATA MISSING",
            "value": None,
            "message": (
                "No verified chlorophyll-a concentration was supplied. "
                "A dedicated ocean-colour data source is required."
            ),
        }

    if value < 0:
        return {
            "name": "Chlorophyll Agent",
            "status": "INVALID INPUT",
            "value": None,
            "message": "Chlorophyll concentration cannot be negative.",
        }

    return {
        "name": "Chlorophyll Agent",
        "status": "INPUT RECEIVED",
        "value": value,
        "message": (
            f"Supplied chlorophyll-a value: {value:.3f} mg/m³. "
            "Use only a verified measurement and record its source."
        ),
    }


def weather_agent(marine, weather):
    wind = safe_float(weather.get("wind_speed_10m"))
    rain = safe_float(weather.get("precipitation"))
    waves = safe_float(marine.get("wave_height"))
    air_temp = safe_float(weather.get("temperature_2m"))

    available = any(
        v is not None for v in [wind, rain, waves, air_temp]
    )

    if not available:
        status = "DATA MISSING"
        message = "No usable weather or marine observations were returned."
    else:
        status = "OBSERVATIONS RECEIVED"
        parts = []
        if wind is not None:
            parts.append(f"wind {wind:.1f} km/h")
        if waves is not None:
            parts.append(f"waves {waves:.2f} m")
        if rain is not None:
            parts.append(f"precipitation {rain:.1f} mm")
        if air_temp is not None:
            parts.append(f"air temperature {air_temp:.1f} °C")

        message = "Available conditions: " + ", ".join(parts) + "."

    return {
        "name": "Weather & Wind Agent",
        "status": status,
        "wind_kmh": wind,
        "wave_height_m": waves,
        "precipitation_mm": rain,
        "air_temperature_c": air_temp,
        "message": message + (
            " These observations do not replace official marine forecasts."
        ),
    }


def historical_agent(hourly, manual_anomaly=None):
    times = hourly.get("time", []) or []
    values = hourly.get("sea_surface_temperature", []) or []

    observations = []
    for t, v in zip(times, values):
        number = safe_float(v)
        if number is not None:
            observations.append({"time": t, "sst": number})

    recent_change = None
    if len(observations) >= 2:
        recent_change = (
            observations[-1]["sst"] - observations[0]["sst"]
        )

    anomaly = safe_float(manual_anomaly)

    if anomaly is not None:
        status = "BASELINE INPUT RECEIVED"
        message = (
            f"Supplied anomaly: {anomaly:+.2f} °C. "
            "Verify the source, reference period, and calculation."
        )
    elif recent_change is not None:
        status = "RECENT PERIOD COMPARISON"
        message = (
            f"SST changed by {recent_change:+.2f} °C between the "
            "first and latest available hourly values in the returned "
            "period. This is not a long-term climate anomaly."
        )
    else:
        status = "BASELINE NEEDED"
        message = (
            "Insufficient valid SST observations for a comparison. "
            "A documented historical baseline is needed for an anomaly."
        )

    return {
        "name": "Historical Trend Agent",
        "status": status,
        "observations": observations,
        "recent_sst_change_c": recent_change,
        "supplied_anomaly_c": anomaly,
        "message": message,
    }


def satellite_agent(chlorophyll):
    if safe_float(chlorophyll) is None:
        return {
            "name": "Satellite Intelligence Agent",
            "status": "UNAVAILABLE",
            "message": (
                "No verified satellite data feed is connected. "
                "Chlorophyll input alone does not establish a live "
                "satellite connection."
            ),
        }

    return {
        "name": "Satellite Intelligence Agent",
        "status": "SATELLITE FEED NOT VERIFIED",
        "message": (
            "A chlorophyll value was supplied, but the satellite feed "
            "itself is not verified by this app. Confirm the product, "
            "date, coordinates, and data provider."
        ),
    }


def reasoning_agent(agents):
    missing = []
    available = []

    for agent in agents:
        if agent["status"] in [
            "DATA MISSING",
            "UNAVAILABLE",
            "BASELINE NEEDED",
        ]:
            missing.append(agent["name"])
        else:
            available.append(agent["name"])

    if missing:
        summary = (
            "Assessment incomplete: some indicators are available, "
            "but important evidence is missing. No screening flags "
            "does not prove that the ecosystem is healthy."
        )
    else:
        summary = (
            "The configured indicators have values, but this does "
            "not establish ecosystem health or ecological safety."
        )

    return {
        "summary": summary,
        "available_agents": available,
        "missing_agents": missing,
        "method": (
            "Transparent data-availability screening. "
            "Not a validated ecological prediction model."
        ),
    }


# ------------------------ Sidebar ------------------------

st.sidebar.markdown("## 🌊 ORCA")
st.sidebar.caption("Marine Ecosystem Intelligence")

page = st.sidebar.radio(
    "Navigate",
    [
        "Mission Control",
        "Agent Lab",
        "Ocean Memory",
        "Evidence Report",
        "Data & Integrations",
    ],
)

region = st.sidebar.selectbox(
    "Marine region",
    list(REGIONS.keys()),
)

latitude, longitude = REGIONS[region]

st.sidebar.markdown("---")
st.sidebar.markdown("### Optional verified inputs")

st.sidebar.caption(
    "Leave blank when you do not have a trustworthy source."
)

chlorophyll_text = st.sidebar.text_input(
    "Chlorophyll-a (mg/m³)",
    placeholder="e.g. 0.45",
)

anomaly_text = st.sidebar.text_input(
    "SST anomaly (°C)",
    placeholder="e.g. +1.2",
)

chlorophyll_input = safe_float(chlorophyll_text.strip()) \
    if chlorophyll_text.strip() else None

anomaly_input = safe_float(anomaly_text.strip()) \
    if anomaly_text.strip() else None

if chlorophyll_input is not None and chlorophyll_input < 0:
    st.sidebar.error("Chlorophyll cannot be negative.")
    chlorophyll_input = None

if st.sidebar.button("🔄 Refresh live data", use_container_width=True):
    fetch_live_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Live data depends on API availability and region coverage.")


# ---------------------- Fetch data -----------------------

with st.spinner("Connecting to marine and weather APIs..."):
    live = fetch_live_data(latitude, longitude)

marine = live.get("marine", {})
hourly = live.get("marine_hourly", {})
weather = live.get("weather", {})

temp_agent = temperature_agent(marine)
chl_agent = chlorophyll_agent(chlorophyll_input)
weather_result = weather_agent(marine, weather)
history_result = historical_agent(hourly, anomaly_input)
satellite_result = satellite_agent(chlorophyll_input)

agents = [
    temp_agent,
    history_result,
    chl_agent,
    satellite_result,
    weather_result,
]

assessment = reasoning_agent(agents)

# Optional FastAPI backend.
# Set ORCA_API_URL to the deployed backend base URL.
backend_url = os.getenv("ORCA_API_URL", "").strip()

if not backend_url:
    try:
        backend_url = st.secrets.get("ORCA_API_URL", "").strip()
    except Exception:
        backend_url = ""

backend_result = None
backend_error = None

if backend_url:
    try:
        response = requests.post(
            backend_url.rstrip("/") + "/api/assess",
            json={
                "region": region,
                "latitude": latitude,
                "longitude": longitude,
                "marine_data": {
                    "current": marine,
                    "hourly": hourly,
                    "weather": weather,
                    "manual_chlorophyll_mg_m3": chlorophyll_input,
                    "manual_sst_anomaly_c": anomaly_input,
                },
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        backend_result = response.json()
    except Exception as exc:
        backend_error = str(exc)


# ---------------------- Header ---------------------------

st.markdown(
    f"""
    <div class="orca-hero">
        <div style="font-size:14px; letter-spacing:3px; color:#70d6ff">
            OCEAN REASONING COLLABORATIVE AGENCY
        </div>
        <h1 style="font-size:42px; margin-bottom:5px">
            🌊 ORCA Mission Control
        </h1>
        <div class="orca-subtitle">
            Six-agent marine intelligence · Live observations ·
            Transparent evidence · {region}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.caption(
    f"Coordinates: {latitude:.2f}, {longitude:.2f} · "
    f"Data fetch: {live.get('fetched_at_utc', 'unknown')}"
)


# --------------------- Mission Control -------------------

if page == "Mission Control":
    st.subheader("Mission Control")

    if live["marine_error"] and live["weather_error"]:
        st.error("Both live API requests failed. Check connectivity and API responses.")
    elif live["marine_error"]:
        st.warning("Marine API unavailable; weather data may still be available.")
    elif live["weather_error"]:
        st.warning("Weather API unavailable; marine data may still be available.")
    else:
        st.success("At least one live API endpoint returned data.")

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Wave height",
        fmt(marine.get("wave_height"), " m"),
        help="Marine API observation/model output",
    )
    c2.metric(
        "Wind speed",
        fmt(weather.get("wind_speed_10m"), " km/h"),
        help="Weather API wind speed",
    )
    c3.metric(
        "Air temperature",
        fmt(weather.get("temperature_2m"), " °C"),
        help="Air temperature is not sea-surface temperature",
    )
    c4.metric(
        "Sea-surface temperature",
        fmt(marine.get("sea_surface_temperature"), " °C"),
        help="Marine API SST; may be unavailable for some locations",
    )

    c5, c6 = st.columns(2)
    c5.metric(
        "Chlorophyll-a",
        fmt(chlorophyll_input, " mg/m³", 3),
    )
    c6.metric(
        "Recent SST change",
        fmt(history_result.get("recent_sst_change_c"), " °C"),
    )

    st.markdown("### Collaborative assessment")
    st.info(assessment["summary"])
    st.caption(assessment["method"])

    if backend_url:
        if backend_result is not None:
            st.success("FastAPI backend responded successfully.")
            show_evidence("Backend response", backend_result)
        else:
            st.warning("Backend URL is configured, but the request failed.")
            st.caption(str(backend_error))
    else:
        st.warning(
            "Backend URL is not configured. The local six-agent "
            "screening logic is being used."
        )

    st.markdown("### Agent activity")

    col_a, col_b = st.columns(2)

    with col_a:
        agent_card(
            "🌡️",
            "Sea Temperature Agent",
            temp_agent["status"],
            temp_agent["message"],
        )
        agent_card(
            "📈",
            "Historical Trend Agent",
            history_result["status"],
            history_result["message"],
        )
        agent_card(
            "🟢",
            "Chlorophyll Agent",
            chl_agent["status"],
            chl_agent["message"],
        )

    with col_b:
        agent_card(
            "🛰️",
            "Satellite Intelligence Agent",
            satellite_result["status"],
            satellite_result["message"],
        )
        agent_card(
            "🌬️",
            "Weather & Wind Agent",
            weather_result["status"],
            weather_result["message"],
        )
        agent_card(
            "🧠",
            "Reasoning Agent",
            "SCREENING COMPLETE",
            assessment["summary"],
        )

    st.markdown("### Marine region map")

    map_df = pd.DataFrame([{
        "Region": region,
        "Latitude": latitude,
        "Longitude": longitude,
        "Wave height (m)": safe_float(marine.get("wave_height")),
        "SST (°C)": safe_float(
            marine.get("sea_surface_temperature")
        ),
    }])

    fig = px.scatter_geo(
        map_df,
        lat="Latitude",
        lon="Longitude",
        hover_name="Region",
        hover_data=["Wave height (m)", "SST (°C)"],
        projection="natural earth",
        title=f"Selected marine region: {region}",
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#eaf6ff",
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            showocean=True,
            oceancolor="#092b40",
            showland=True,
            landcolor="#183447",
            showcoastlines=True,
            coastlinecolor="#5d879d",
        ),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    st.plotly_chart(fig, use_container_width=True)

    show_evidence("Debug live data response", live)


# ----------------------- Agent Lab -----------------------

elif page == "Agent Lab":
    st.subheader("Agent Lab")
    st.write(
        "Each specialist agent evaluates its own evidence. "
        "Missing observations remain missing rather than being fabricated."
    )

    for item in agents:
        st.markdown(f"### {item['name']}")
        st.write(f"**Status:** {item['status']}")
        st.write(item["message"])
        with st.expander("Inspect agent evidence"):
            st.text(safe_json(item))

    st.markdown("### Collaborative reasoning")
    st.info(assessment["summary"])
    st.write("**Available agents:**")
    st.write(assessment["available_agents"] or "None confirmed")
    st.write("**Missing or incomplete agents:**")
    st.write(assessment["missing_agents"] or "No missing status reported")
    st.caption(assessment["method"])


# --------------------- Ocean Memory ----------------------

elif page == "Ocean Memory":
    st.subheader("Ocean Memory")
    st.write(
        "Recent SST observations returned by the marine API. "
        "This is a short-period comparison, not a climate anomaly."
    )

    times = hourly.get("time", []) or []
    values = hourly.get("sea_surface_temperature", []) or []

    rows = []
    for t, v in zip(times, values):
        number = safe_float(v)
        if number is not None:
            rows.append({"Time (UTC)": t, "SST (°C)": number})

    if rows:
        history_df = pd.DataFrame(rows)
        st.line_chart(
            history_df.set_index("Time (UTC)")["SST (°C)"]
        )

        first = history_df.iloc[0]["SST (°C)"]
        last = history_df.iloc[-1]["SST (°C)"]

        st.metric(
            "Change across returned observations",
            f"{last - first:+.2f} °C",
        )
        st.dataframe(history_df, use_container_width=True)
        st.download_button(
            "Download SST observations CSV",
            history_df.to_csv(index=False).encode("utf-8"),
            file_name="orca_sst_observations.csv",
            mime="text/csv",
        )
    else:
        st.warning(
            "No SST time series returned. Check the marine API response "
            "or select another region."
        )

    st.info(
        "A real anomaly requires a documented reference baseline, "
        "such as a multi-year climatology for the same location and season."
    )


# -------------------- Evidence Report --------------------

elif page == "Evidence Report":
    st.subheader("Evidence Report")

    report = {
        "application": "ORCA Marine Ecosystem Intelligence",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "coordinates": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "live_observations": {
            "marine": marine,
            "weather": weather,
        },
        "agents": agents,
        "assessment": assessment,
        "backend_configured": bool(backend_url),
        "backend_response": backend_result,
        "api_errors": {
            "marine": live.get("marine_error"),
            "weather": live.get("weather_error"),
            "backend": backend_error,
        },
    }

    st.write("Export the evidence for inspection or demo review.")
    st.download_button(
        "Download evidence report (JSON)",
        data=safe_json(report),
        file_name="orca_evidence_report.json",
        mime="application/json",
    )

    show_evidence("Full evidence report", report)


# ------------------ Data & Integrations ------------------

elif page == "Data & Integrations":
    st.subheader("Data & Integrations")

    st.markdown("### Live API status")
    st.write("**Marine API:**")
    if live["marine_error"]:
        st.error(live["marine_error"])
    else:
        st.success("Marine endpoint returned a response.")
        show_evidence("Marine API response", {
            "current": marine,
            "hourly_keys": list(hourly.keys()),
        })

    st.write("**Weather API:**")
    if live["weather_error"]:
        st.error(live["weather_error"])
    else:
        st.success("Weather endpoint returned a response.")
        show_evidence("Weather API response", weather)

    st.markdown("### Backend")
    if backend_url:
        st.write("Backend URL is configured.")
        if backend_error:
            st.error(f"Backend request failed: {backend_error}")
        elif backend_result is not None:
            st.success("Backend responded.")
            show_evidence("Backend result", backend_result)
    else:
        st.warning(
            "ORCA_API_URL is not configured. If your FastAPI backend "
            "is deployed, add its base URL in Streamlit Cloud Secrets."
        )

    st.markdown("### Data limitations")
    st.markdown("""
    - **SST:** Requested from Open-Meteo Marine API; availability varies by location.
    - **Chlorophyll:** Requires a verified ocean-colour source or documented input.
    - **Historical anomaly:** Requires a documented reference baseline.
    - **Satellite status:** Not treated as connected merely because a value is manually entered.
    - **Ecological risk:** This application is a screening prototype, not a validated prediction model.
    """)

    st.markdown("### Useful official data sources")
    st.markdown(
        "- [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api)\n"
        "- [Copernicus Marine ocean-colour products](https://data.marine.copernicus.eu/)\n"
        "- [Copernicus satellite ocean-colour information](https://www.copernicus.eu/en/access-data/copernicus-services-catalogue/ocean-colour-daily-data-1997-present-derived-satellite)"
    )


# ------------------------ Footer -------------------------

st.markdown("---")
st.caption(
    "ORCA · Ocean Reasoning Collaborative Agency · "
    "Live data availability depends on source coverage. "
    "Not for navigation, emergency response, or definitive ecological diagnosis."
)





