
import os
import json
from datetime import datetime, timezone
import requests
import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# ORCA - Ocean Reasoning Collaborative Agency
# Six-agent marine intelligence prototype
# =========================================================

st.set_page_config(
    page_title="ORCA | Marine Intelligence",
    page_icon="🌊",
    layout="wide",
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

# ----------------------- UI styling -----------------------

st.markdown("""
<style>
.stApp {
    background: linear-gradient(145deg, #071522, #0b2638, #071522);
    color: #eaf6ff;
}
[data-testid="stSidebar"] {
    background: #081827;
    border-right: 1px solid #24485d;
}
h1, h2, h3, h4 {
    color: #eaf6ff !important;
}
p, label, li {
    color: #c2d7e7;
}
.hero {
    padding: 28px;
    border: 1px solid #24516a;
    border-radius: 20px;
    background: linear-gradient(120deg, #10334a, #0b1e30);
    margin-bottom: 22px;
}
.agent {
    background: #0c2435;
    border: 1px solid #24485d;
    border-radius: 15px;
    padding: 16px;
    margin-bottom: 12px;
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
</style>
""", unsafe_allow_html=True)


# ------------------------- Helpers -----------------------

def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if pd.notna(value) else None
    except (TypeError, ValueError):
        return None


def fmt(value, unit="", digits=2):
    value = number(value)
    return "Unavailable" if value is None else f"{value:.{digits}f}{unit}"


def safe_json(value):
    return json.dumps(
        value,
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def evidence(title, value):
    # Plain text avoids the JSON syntax highlighter issue.
    with st.expander(title):
        st.text(safe_json(value))


def show_agent(emoji, name, status, message):
    st.markdown(
        f"""
        <div class="agent">
            <div style="font-size:25px">{emoji}</div>
            <h4>{name}</h4>
            <strong>{status}</strong>
            <p>{message}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------- API integrations ------------------

@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def fetch_marine_weather(latitude, longitude):
    result = {
        "marine": {},
        "hourly": {},
        "weather": {},
        "errors": {},
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    marine_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": (
            "wave_height,wave_direction,wave_period,"
            "sea_surface_temperature,ocean_current_velocity"
        ),
        "hourly": "sea_surface_temperature,wave_height",
        "past_days": 7,
        "forecast_days": 1,
        "timezone": "UTC",
        "cell_selection": "sea",
    }

    try:
        response = requests.get(
            "https://marine-api.open-meteo.com/v1/marine",
            params=marine_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        result["marine"] = data.get("current", {}) or {}
        result["hourly"] = data.get("hourly", {}) or {}

    except Exception as exc:
        result["errors"]["marine"] = str(exc)

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
            "https://api.open-meteo.com/v1/forecast",
            params=weather_params,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        result["weather"] = response.json().get("current", {}) or {}

    except Exception as exc:
        result["errors"]["weather"] = str(exc)

    return result


def fetch_chlorophyll(latitude, longitude):
    """
    Optional adapter for a verified chlorophyll service.

    Configure ORCA_CHLOROPHYLL_API_URL to your own deployed
    data endpoint. It must accept latitude and longitude query
    parameters and return JSON containing:
        chlorophyll_a_mg_m3: numeric concentration
        source: source/product name
        observation_time: timestamp (recommended)

    This does not pretend that Open-Meteo provides chlorophyll.
    """
    endpoint = os.getenv("ORCA_CHLOROPHYLL_API_URL", "").strip()

    if not endpoint:
        try:
            endpoint = st.secrets.get(
                "ORCA_CHLOROPHYLL_API_URL", ""
            ).strip()
        except Exception:
            endpoint = ""

    if not endpoint:
        return {
            "value": None,
            "source": None,
            "time": None,
            "error": "No chlorophyll data endpoint configured.",
        }

    try:
        response = requests.get(
            endpoint,
            params={
                "latitude": latitude,
                "longitude": longitude,
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        value = number(data.get("chlorophyll_a_mg_m3"))

        if value is None or value < 0:
            return {
                "value": None,
                "source": data.get("source"),
                "time": data.get("observation_time"),
                "error": (
                    "Endpoint returned no valid non-negative "
                    "chlorophyll_a_mg_m3 value."
                ),
            }

        return {
            "value": value,
            "source": data.get("source", "Configured endpoint"),
            "time": data.get("observation_time"),
            "error": None,
        }

    except Exception as exc:
        return {
            "value": None,
            "source": None,
            "time": None,
            "error": str(exc),
        }


# ------------------------ Agents -------------------------

def sea_temperature_agent(marine):
    sst = number(marine.get("sea_surface_temperature"))

    if sst is None:
        return {
            "name": "Sea Temperature Agent",
            "status": "DATA MISSING",
            "value": None,
            "message": (
                "No SST was returned. Air temperature is not "
                "a substitute for sea-surface temperature."
            ),
        }

    return {
        "name": "Sea Temperature Agent",
        "status": "OBSERVATION RECEIVED",
        "value": sst,
        "message": (
            f"Marine API returned an SST value of {sst:.2f} °C. "
            "This value alone does not establish ecosystem health."
        ),
    }


def chlorophyll_agent(chl):
    value = number(chl.get("value"))

    if value is None:
        return {
            "name": "Chlorophyll Agent",
            "status": "DATA MISSING",
            "value": None,
            "message": (
                "No verified chlorophyll-a observation is available. "
                "Connect a satellite-derived ocean-colour data source."
            ),
        }

    return {
        "name": "Chlorophyll Agent",
        "status": "OBSERVATION RECEIVED",
        "value": value,
        "message": (
            f"Chlorophyll-a: {value:.3f} mg/m³. "
            f"Source: {chl.get('source') or 'Not identified'}. "
            "Check timestamp, quality flags, and product metadata."
        ),
    }


def weather_agent(marine, weather):
    wind = number(weather.get("wind_speed_10m"))
    rain = number(weather.get("precipitation"))
    air = number(weather.get("temperature_2m"))
    wave = number(marine.get("wave_height"))

    available = any(
        x is not None for x in [wind, rain, air, wave]
    )

    details = []
    if wind is not None:
        details.append(f"wind {wind:.1f} km/h")
    if wave is not None:
        details.append(f"waves {wave:.2f} m")
    if rain is not None:
        details.append(f"precipitation {rain:.1f} mm")
    if air is not None:
        details.append(f"air temperature {air:.1f} °C")

    return {
        "name": "Weather & Wind Agent",
        "status": "OBSERVATIONS RECEIVED" if available else "DATA MISSING",
        "wind": wind,
        "wave": wave,
        "rain": rain,
        "air_temperature": air,
        "message": (
            "Available conditions: " + ", ".join(details)
            if details else "No weather or marine conditions returned."
        ),
    }


def historical_agent(hourly):
    times = hourly.get("time", []) or []
    values = hourly.get("sea_surface_temperature", []) or []

    rows = []
    for timestamp, value in zip(times, values):
        value = number(value)
        if value is not None:
            rows.append({"time": timestamp, "sst": value})

    change = None

    if len(rows) >= 2:
        change = rows[-1]["sst"] - rows[0]["sst"]

    if change is None:
        status = "BASELINE NEEDED"
        message = (
            "Not enough valid SST observations to compare the "
            "returned period. A longer historical baseline is "
            "required for a climate anomaly."
        )
    else:
        status = "RECENT PERIOD COMPARISON"
        message = (
            f"SST changed by {change:+.2f} °C across the returned "
            "observations. This is not a long-term climate anomaly."
        )

    return {
        "name": "Historical Trend Agent",
        "status": status,
        "change": change,
        "rows": rows,
        "message": message,
    }


def satellite_agent(chl):
    if chl.get("value") is not None and chl.get("source"):
        return {
            "name": "Satellite Intelligence Agent",
            "status": "CHLOROPHYLL SOURCE PROVIDED",
            "message": (
                "A chlorophyll observation and source label were returned. "
                "Confirm that the source is a satellite product and inspect "
                "its quality flags before treating it as satellite-verified."
            ),
        }

    return {
        "name": "Satellite Intelligence Agent",
        "status": "UNAVAILABLE",
        "message": (
            "No verified satellite feed is connected. A source label "
            "or manually entered value alone does not verify satellite access."
        ),
    }


def reasoning_agent(agents):
    missing = [
        agent["name"] for agent in agents
        if agent["status"] in {
            "DATA MISSING",
            "UNAVAILABLE",
            "BASELINE NEEDED",
        }
    ]

    available = [
        agent["name"] for agent in agents
        if agent["name"] not in missing
    ]

    if missing:
        summary = (
            "Assessment incomplete: some indicators are available, "
            "but important evidence is missing. No screening flags "
            "does not prove that the ecosystem is healthy."
        )
    else:
        summary = (
            "Configured indicators returned observations. This is "
            "not a validated ecological health prediction."
        )

    return {
        "summary": summary,
        "missing_agents": missing,
        "available_agents": available,
        "method": (
            "Evidence availability screening only; not a validated "
            "ecological prediction model."
        ),
    }


# ----------------------- Sidebar -------------------------

st.sidebar.markdown("## 🌊 ORCA")
st.sidebar.caption("Ocean Reasoning Collaborative Agency")

page = st.sidebar.radio(
    "Navigation",
    [
        "Mission Control",
        "Agent Lab",
        "Ocean Memory",
        "Evidence Report",
        "Data & Integrations",
    ],
)

region = st.sidebar.selectbox("Marine region", list(REGIONS.keys()))
latitude, longitude = REGIONS[region]

if st.sidebar.button("🔄 Refresh live data", width="stretch"):
    fetch_marine_weather.clear()
    st.rerun()


# --------------------- Retrieve data ---------------------

with st.spinner("Fetching marine and weather observations..."):
    live = fetch_marine_weather(latitude, longitude)
    chlorophyll = fetch_chlorophyll(latitude, longitude)

marine = live["marine"]
hourly = live["hourly"]
weather = live["weather"]

sst_agent = sea_temperature_agent(marine)
chl_agent = chlorophyll_agent(chlorophyll)
weather_result = weather_agent(marine, weather)
history_result = historical_agent(hourly)
satellite_result = satellite_agent(chlorophyll)

agents = [
    sst_agent,
    history_result,
    chl_agent,
    satellite_result,
    weather_result,
]

assessment = reasoning_agent(agents)

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
                    "chlorophyll": chlorophyll,
                },
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        backend_result = response.json()
    except Exception as exc:
        backend_error = str(exc)


# ------------------------- Header ------------------------

st.markdown(
    f"""
    <div class="hero">
        <div style="letter-spacing:3px;color:#70d6ff">
            OCEAN REASONING COLLABORATIVE AGENCY
        </div>
        <h1 style="font-size:40px">🌊 ORCA Mission Control</h1>
        <p>Six-agent marine intelligence · Live observations · Evidence-based screening</p>
        <p>Region: {region} · Coordinates: {latitude:.2f}, {longitude:.2f}</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# --------------------- Mission Control -------------------

if page == "Mission Control":
    st.subheader("Mission Control")

    if live["errors"]:
        st.warning("Some API requests failed. See Data & Integrations for details.")
    elif any([marine, weather]):
        st.success("At least one live API endpoint returned data.")
    else:
        st.error("No live observations were returned.")

    a, b, c, d = st.columns(4)

    a.metric("Wave height", fmt(marine.get("wave_height"), " m"))
    b.metric("Wind speed", fmt(weather.get("wind_speed_10m"), " km/h"))
    c.metric("Air temperature", fmt(weather.get("temperature_2m"), " °C"))
    d.metric(
        "Sea-surface temperature",
        fmt(marine.get("sea_surface_temperature"), " °C"),
    )

    e, f = st.columns(2)
    e.metric(
        "Chlorophyll-a",
        fmt(chlorophyll.get("value"), " mg/m³", 3),
    )
    f.metric(
        "Recent SST change",
        fmt(history_result.get("change"), " °C"),
    )

    st.subheader("Collaborative assessment")
    st.info(assessment["summary"])
    st.caption(assessment["method"])

    if not backend_url:
        st.warning(
            "Backend URL is not configured. Local screening is active."
        )
    elif backend_error:
        st.error(f"Backend request failed: {backend_error}")
    elif backend_result is not None:
        st.success("FastAPI backend responded successfully.")
        evidence("Backend response", backend_result)

    st.subheader("Agent activity")

    left, right = st.columns(2)

    with left:
        show_agent("🌡️", "Sea Temperature Agent",
                   sst_agent["status"], sst_agent["message"])
        show_agent("📈", "Historical Trend Agent",
                   history_result["status"], history_result["message"])
        show_agent("🟢", "Chlorophyll Agent",
                   chl_agent["status"], chl_agent["message"])

    with right:
        show_agent("🛰️", "Satellite Intelligence Agent",
                   satellite_result["status"], satellite_result["message"])
        show_agent("🌬️", "Weather & Wind Agent",
                   weather_result["status"], weather_result["message"])
        show_agent("🧠", "Reasoning Agent",
                   "SCREENING COMPLETE", assessment["summary"])

    st.subheader("Marine region map")

    map_df = pd.DataFrame([{
        "Region": region,
        "Latitude": latitude,
        "Longitude": longitude,
        "Wave height (m)": number(marine.get("wave_height")),
        "SST (°C)": number(marine.get("sea_surface_temperature")),
    }])

    fig = px.scatter_geo(
        map_df,
        lat="Latitude",
        lon="Longitude",
        hover_name="Region",
        hover_data=["Wave height (m)", "SST (°C)"],
        projection="natural earth",
        title="Selected marine region",
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font_color="#eaf6ff",
        geo=dict(
            bgcolor="rgba(0,0,0,0)",
            showocean=True,
            oceancolor="#092b40",
            showland=True,
            landcolor="#183447",
            showcoastlines=True,
        ),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    st.plotly_chart(fig, width="stretch")

    evidence("Debug live data response", live)
    evidence("Chlorophyll response", chlorophyll)


# ------------------------- Agent Lab ---------------------

elif page == "Agent Lab":
    st.subheader("Agent Lab")

    for agent in agents:
        st.markdown(f"### {agent['name']}")
        st.write(f"**Status:** {agent['status']}")
        st.write(agent["message"])
        evidence(f"Inspect {agent['name']}", agent)

    st.subheader("Reasoning Agent")
    st.info(assessment["summary"])
    st.write("**Available agents:**", assessment["available_agents"])
    st.write("**Missing or incomplete agents:**", assessment["missing_agents"])


# ----------------------- Ocean Memory --------------------

elif page == "Ocean Memory":
    st.subheader("Ocean Memory")

    rows = history_result.get("rows", [])

    if rows:
        history_df = pd.DataFrame(rows)

        st.line_chart(
            history_df.set_index("time")["sst"],
            width="stretch",
        )

        st.dataframe(history_df, width="stretch")

        st.download_button(
            "Download SST observations CSV",
            history_df.to_csv(index=False).encode("utf-8"),
            file_name="orca_sst_observations.csv",
            mime="text/csv",
            width="stretch",
        )
        st.info(history_result["message"])
    else:
        st.warning("No valid SST time series was returned.")

    st.caption(
        "A short-period SST difference is not a long-term climate anomaly. "
        "A climate anomaly needs a documented historical reference baseline."
    )


# ---------------------- Evidence Report ------------------

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
        "marine": marine,
        "weather": weather,
        "chlorophyll": chlorophyll,
        "agents": agents,
        "assessment": assessment,
        "backend_configured": bool(backend_url),
        "backend_result": backend_result,
        "api_errors": live["errors"],
        "backend_error": backend_error,
    }

    st.download_button(
        "Download evidence report JSON",
        safe_json(report),
        file_name="orca_evidence_report.json",
        mime="application/json",
        width="stretch",
    )

    evidence("Full evidence report", report)


# ------------------ Data & Integrations ------------------

elif page == "Data & Integrations":
    st.subheader("Data & Integrations")

    st.markdown("### Marine API")
    if "marine" in live["errors"]:
        st.error(live["errors"]["marine"])
    else:
        st.success("Marine endpoint returned a response.")
        evidence("Marine current data", marine)
        evidence("Marine hourly data", hourly)

    st.markdown("### Weather API")
    if "weather" in live["errors"]:
        st.error(live["errors"]["weather"])
    else:
        st.success("Weather endpoint returned a response.")
        evidence("Weather current data", weather)

    st.markdown("### Chlorophyll integration")
    if chlorophyll.get("value") is not None:
        st.success(
            f"Chlorophyll value returned by: {chlorophyll.get('source')}"
        )
        st.write("Observation time:", chlorophyll.get("time"))
    else:
        st.warning("Chlorophyll endpoint is not returning a verified value.")
        st.write(chlorophyll.get("error"))

    st.markdown("### FastAPI backend")
    if not backend_url:
        st.warning("ORCA_API_URL is not configured.")
    elif backend_error:
        st.error(backend_error)
    else:
        st.success("Backend responded.")
        evidence("Backend response", backend_result)

    st.markdown("### Data limitations")
    st.markdown("""
    - SST and waves: Open-Meteo Marine API.
    - Wind and air temperature: Open-Meteo Weather API.
    - Chlorophyll: requires a separate, verified ocean-colour source.
    - Satellite status: requires source and product verification.
    - Historical anomaly: requires a documented reference baseline.
    - Assessment: data-availability screening, not a validated ecological model.
    """)

    st.markdown("### Official data resources")
    st.markdown(
        "- [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api)\n"
        "- [Copernicus Marine Data Store](https://data.marine.copernicus.eu/)\n"
        "- [Copernicus satellite-derived chlorophyll-a data](https://www.copernicus.eu/en/access-data/copernicus-services-catalogue/ocean-colour-daily-data-1997-present-derived-satellite)"
    )


# --------------------------- Footer ----------------------

st.markdown("---")
st.caption(
    "ORCA · Ocean Reasoning Collaborative Agency · "
    "Not for navigation, emergency response, or definitive ecological diagnosis."
)






