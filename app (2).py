import os
import json
import math
from datetime import datetime, timezone

import requests
import pandas as pd
import plotly.express as px
import streamlit as st


# =========================================================
# ORCA - Ocean Reasoning Collaborative Agency
# Six-agent marine intelligence prototype
# =========================================================

st.set_page_config(page_title="ORCA | Marine Intelligence", page_icon="🌊", layout="wide")

REQUEST_TIMEOUT = 25
CACHE_SECONDS = 1800

# NOAA CoastWatch ERDDAP: VIIRS (S-NPP + NOAA-20) chlorophyll OCI, 4 km, daily, near real-time.
# Override with env/secrets if you prefer another dataset.
ERDDAP_BASE = "https://coastwatch.noaa.gov/erddap/griddap/"
CHL_DATASET = os.getenv("ORCA_CHL_DATASET", "noaacwNPPN20VIIRSchlociDaily")
CHL_VARIABLE = os.getenv("ORCA_CHL_VARIABLE", "chlor_a")
CHL_BOX_DEG = 0.5  # half-width of the box averaged around the selected point

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

# Missing-evidence statuses
MISSING = {"DATA MISSING", "UNAVAILABLE", "BASELINE NEEDED"}

# ----------------------- UI styling -----------------------

st.markdown("""
<style>
.stApp { background: linear-gradient(145deg, #071522, #0b2638, #071522); color: #eaf6ff; }
[data-testid="stSidebar"] { background: #081827; border-right: 1px solid #24485d; }
h1, h2, h3, h4 { color: #eaf6ff !important; }
p, label, li { color: #c2d7e7; }
.hero { padding: 24px 28px; border: 1px solid #24516a; border-radius: 20px;
        background: linear-gradient(120deg, #10334a, #0b1e30); margin-bottom: 18px;
        display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
.hero .txt { flex: 1; min-width: 260px; }
.agent { background: #0c2435; border: 1px solid #24485d; border-radius: 15px;
         padding: 16px; margin-bottom: 12px; }
div[data-testid="stMetric"] { background: #0c2435; border: 1px solid #21465c;
         border-radius: 14px; padding: 14px; }
div[data-testid="stMetric"] label { color: #a9c9de !important; }
.zone { border-radius: 14px; padding: 18px; border: 1px solid #24485d; }
</style>
""", unsafe_allow_html=True)


# ------------------------- Helpers -----------------------

def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if pd.notna(value) and math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def fmt(value, unit="", digits=2):
    value = number(value)
    return "Unavailable" if value is None else f"{value:.{digits}f}{unit}"


def safe_json(value):
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


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


def get_setting(name):
    value = os.getenv(name, "").strip()
    if value:
        return value
    try:
        return str(st.secrets.get(name, "")).strip()
    except Exception:
        return ""


def completeness_ring(percent):
    """Honest ring: share of agents that have evidence. Not an ecosystem health score."""
    circ = 314.16
    offset = circ * (1 - percent / 100)
    return f"""
    <svg width="150" height="150" viewBox="0 0 120 120" role="img"
         aria-label="Evidence completeness {percent:.0f} percent">
      <circle cx="60" cy="60" r="50" fill="none" stroke="#12394a" stroke-width="10"/>
      <circle cx="60" cy="60" r="50" fill="none" stroke="#5ce1ff" stroke-width="10"
              stroke-linecap="round" stroke-dasharray="{circ}" stroke-dashoffset="{offset:.1f}"
              transform="rotate(-90 60 60)"/>
      <text x="60" y="62" text-anchor="middle" fill="#eaf6ff" font-size="26" font-weight="800">{percent:.0f}%</text>
      <text x="60" y="80" text-anchor="middle" fill="#8fb5b9" font-size="9">evidence complete</text>
    </svg>
    """


# --------------------- API integrations ------------------

@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def fetch_marine_weather(latitude, longitude):
    result = {
        "marine": {}, "hourly": {}, "weather": {}, "errors": {},
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    marine_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "wave_height,wave_direction,wave_period,sea_surface_temperature,ocean_current_velocity",
        "hourly": "sea_surface_temperature,wave_height",
        "past_days": 7,
        "forecast_days": 1,
        "timezone": "UTC",
        "cell_selection": "sea",
    }

    try:
        response = requests.get("https://marine-api.open-meteo.com/v1/marine",
                                params=marine_params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        result["marine"] = data.get("current", {}) or {}
        result["hourly"] = data.get("hourly", {}) or {}
    except Exception as exc:
        result["errors"]["marine"] = str(exc)

    weather_params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation",
        "timezone": "UTC",
    }

    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast",
                                params=weather_params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        result["weather"] = response.json().get("current", {}) or {}
    except Exception as exc:
        result["errors"]["weather"] = str(exc)

    return result


def _chl_from_custom_endpoint(endpoint, latitude, longitude):
    """Your own service. Must return JSON: chlorophyll_a_mg_m3, source, observation_time."""
    response = requests.get(endpoint, params={"latitude": latitude, "longitude": longitude},
                            timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    value = number(data.get("chlorophyll_a_mg_m3"))
    if value is None or value < 0:
        return {"value": None, "source": data.get("source"), "time": data.get("observation_time"),
                "error": "Endpoint returned no valid non-negative chlorophyll_a_mg_m3 value."}
    return {"value": value, "source": data.get("source", "Configured endpoint"),
            "time": data.get("observation_time"), "pixels": None, "error": None}


def _chl_from_erddap(latitude, longitude):
    """
    Median chlorophyll-a in a small box around the point, latest day with valid pixels in the
    last ~4 days. Tries axis-order variants because ERDDAP datasets differ on latitude order
    and on whether an altitude dimension exists.
    """
    lon = ((longitude + 180) % 360) - 180  # dataset assumed to use -180..180
    la_lo, la_hi = latitude - CHL_BOX_DEG, latitude + CHL_BOX_DEG
    lo_lo, lo_hi = lon - CHL_BOX_DEG, lon + CHL_BOX_DEG
    url = f"{ERDDAP_BASE}{CHL_DATASET}.json"

    attempts = []
    for alt in ("[(0.0):1:(0.0)]", ""):
        for lat_a, lat_b in ((la_lo, la_hi), (la_hi, la_lo)):
            query = (f"{CHL_VARIABLE}[(now-4days):1:(last)]{alt}"
                     f"[({lat_a:.3f}):1:({lat_b:.3f})][({lo_lo:.3f}):1:({lo_hi:.3f})]")
            attempts.append(query)

    last_error = "No attempt was made."
    for query in attempts:
        try:
            response = requests.get(url + "?" + query, timeout=REQUEST_TIMEOUT)
            if response.status_code != 200:
                last_error = f"HTTP {response.status_code} for query {query}"
                continue
            table = response.json().get("table", {})
            cols = table.get("columnNames", [])
            rows = table.get("rows", [])
            if CHL_VARIABLE not in cols or "time" not in cols:
                last_error = f"Unexpected columns: {cols}"
                continue
            ti, vi = cols.index("time"), cols.index(CHL_VARIABLE)
            by_day = {}
            for row in rows:
                v = number(row[vi])
                if v is not None and v >= 0:
                    by_day.setdefault(row[ti], []).append(v)
            if not by_day:
                return {"value": None, "source": None, "time": None, "pixels": 0,
                        "error": "ERDDAP responded, but all pixels in the box were empty "
                                 "(cloud, glint or land mask) for the last ~4 days."}
            day = max(by_day)
            vals = sorted(by_day[day])
            median = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
            return {
                "value": median,
                "source": f"NOAA CoastWatch ERDDAP · {CHL_DATASET} · {CHL_VARIABLE} (VIIRS near-real-time, ~4 km daily)",
                "time": day,
                "pixels": len(vals),
                "error": None,
            }
        except Exception as exc:
            last_error = str(exc)

    return {"value": None, "source": None, "time": None, "pixels": None,
            "error": f"ERDDAP request failed. Last error: {last_error}"}


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def fetch_chlorophyll(latitude, longitude):
    endpoint = get_setting("ORCA_CHLOROPHYLL_API_URL")
    try:
        if endpoint:
            return _chl_from_custom_endpoint(endpoint, latitude, longitude)
        return _chl_from_erddap(latitude, longitude)
    except Exception as exc:
        return {"value": None, "source": None, "time": None, "pixels": None, "error": str(exc)}


@st.cache_data(ttl=CACHE_SECONDS, show_spinner=False)
def call_backend(base_url, payload_json):
    response = requests.post(base_url.rstrip("/") + "/api/assess",
                             json=json.loads(payload_json), timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


# ------------------------ Agents -------------------------

def sea_temperature_agent(marine):
    sst = number(marine.get("sea_surface_temperature"))
    if sst is None:
        return {"name": "Sea Temperature Agent", "status": "DATA MISSING", "value": None,
                "message": "No SST was returned. Air temperature is not a substitute for sea-surface temperature."}
    return {"name": "Sea Temperature Agent", "status": "MODEL VALUE RECEIVED", "value": sst,
            "message": f"Open-Meteo marine model returned an SST of {sst:.2f} °C. "
                       "This is model output, and one value alone does not establish ecosystem health."}


def chlorophyll_agent(chl):
    value = number(chl.get("value"))
    if value is None:
        return {"name": "Chlorophyll Agent", "status": "DATA MISSING", "value": None,
                "message": "No chlorophyll-a value is available right now. "
                           f"Reason: {chl.get('error') or 'unknown'}"}
    pixels = chl.get("pixels")
    pix = f" Median of {pixels} valid pixels." if pixels else ""
    return {"name": "Chlorophyll Agent", "status": "OBSERVATION RECEIVED", "value": value,
            "message": f"Chlorophyll-a: {value:.3f} mg/m³ on {chl.get('time')}.{pix} "
                       f"Source: {chl.get('source') or 'Not identified'}. "
                       "Near-real-time product: check quality flags before relying on it."}


def weather_agent(marine, weather):
    wind = number(weather.get("wind_speed_10m"))
    rain = number(weather.get("precipitation"))
    air = number(weather.get("temperature_2m"))
    wave = number(marine.get("wave_height"))

    details = []
    if wind is not None:
        details.append(f"wind {wind:.1f} km/h")
    if wave is not None:
        details.append(f"waves {wave:.2f} m")
    if rain is not None:
        details.append(f"precipitation {rain:.1f} mm")
    if air is not None:
        details.append(f"air temperature {air:.1f} °C")

    available = bool(details)
    return {"name": "Weather & Wind Agent",
            "status": "MODEL VALUES RECEIVED" if available else "DATA MISSING",
            "wind_kmh": wind, "wave_m": wave, "rain_mm": rain, "air_temperature_c": air,
            "message": ("Available conditions: " + ", ".join(details)) if details
            else "No weather or marine conditions returned."}


def historical_agent(hourly):
    times = hourly.get("time", []) or []
    values = hourly.get("sea_surface_temperature", []) or []
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)

    rows = []
    for timestamp, value in zip(times, values):
        value = number(value)
        t = pd.to_datetime(timestamp, errors="coerce")
        # Drop future hours: they are forecast, not past data.
        if value is not None and pd.notna(t) and t <= now:
            rows.append({"time": timestamp, "sst": value})

    change = rows[-1]["sst"] - rows[0]["sst"] if len(rows) >= 2 else None

    if change is None:
        status = "BASELINE NEEDED"
        message = ("Not enough valid past SST values to compare. A longer historical "
                   "baseline is required for a climate anomaly.")
    else:
        status = "RECENT PERIOD COMPARISON"
        message = (f"Modelled SST changed by {change:+.2f} °C over the past ~7 days "
                   "(forecast hours excluded). This is not a long-term climate anomaly.")

    return {"name": "Historical Trend Agent", "status": status, "change": change,
            "rows": rows, "message": message}


def satellite_agent(chl):
    if chl.get("value") is not None and chl.get("source"):
        return {"name": "Satellite Intelligence Agent", "status": "SATELLITE PRODUCT RECEIVED",
                "message": "A chlorophyll value was returned with a named source and observation date. "
                           "Satellite ocean colour is cloud-limited, so gaps are normal."}
    return {"name": "Satellite Intelligence Agent", "status": "UNAVAILABLE",
            "message": "No satellite chlorophyll value was returned for this region and window."}


def reasoning_agent(agents):
    missing = [a["name"] for a in agents if a["status"] in MISSING]
    available = [a["name"] for a in agents if a["status"] not in MISSING]
    percent = 100 * len(available) / len(agents) if agents else 0

    if missing:
        status = "INCOMPLETE"
        summary = ("Assessment incomplete: some indicators are available, but important evidence is missing. "
                   "Having no warning flags does not prove that the ecosystem is healthy.")
    else:
        status = "ALL INDICATORS PRESENT"
        summary = ("All configured indicators returned values. This is still a data-availability screening, "
                   "not a validated ecological health prediction.")

    return {"status": status, "summary": summary, "percent_complete": percent,
            "missing_agents": missing, "available_agents": available,
            "method": "Evidence availability screening only; not a validated ecological prediction model."}


# ----------------------- Sidebar -------------------------

st.sidebar.markdown("## 🌊 ORCA")
st.sidebar.caption("Ocean Reasoning Collaborative Agency")

page = st.sidebar.radio(
    "Navigation",
    ["Mission Control", "Agent Lab", "Dive Explorer", "Ocean Memory", "Evidence Report", "Data & Integrations"],
)

region = st.sidebar.selectbox("Marine region", list(REGIONS.keys()))
latitude, longitude = REGIONS[region]

if st.sidebar.button("🔄 Refresh live data", width="stretch"):
    fetch_marine_weather.clear()
    fetch_chlorophyll.clear()
    call_backend.clear()
    st.rerun()


# --------------------- Retrieve data ---------------------

with st.spinner("Fetching marine, weather and satellite data..."):
    live = fetch_marine_weather(latitude, longitude)
    chlorophyll = fetch_chlorophyll(latitude, longitude)

marine, hourly, weather = live["marine"], live["hourly"], live["weather"]

sst_agent = sea_temperature_agent(marine)
chl_agent = chlorophyll_agent(chlorophyll)
weather_result = weather_agent(marine, weather)
history_result = historical_agent(hourly)
satellite_result = satellite_agent(chlorophyll)

agents = [sst_agent, history_result, chl_agent, satellite_result, weather_result]
assessment = reasoning_agent(agents)

backend_url = get_setting("ORCA_API_URL")
backend_result, backend_error = None, None

if backend_url:
    payload = {
        "region": region, "latitude": latitude, "longitude": longitude,
        "marine_data": {"current": marine, "hourly": hourly, "weather": weather, "chlorophyll": chlorophyll},
    }
    try:
        backend_result = call_backend(backend_url, json.dumps(payload, default=str, sort_keys=True))
    except Exception as exc:
        backend_error = str(exc)


# ------------------------- Header ------------------------

st.markdown(
    f"""
    <div class="hero">
      <div class="txt">
        <div style="letter-spacing:3px;color:#70d6ff">OCEAN REASONING COLLABORATIVE AGENCY</div>
        <h1 style="font-size:38px;margin:6px 0">🌊 ORCA Mission Control</h1>
        <p>Six-agent marine intelligence · Live data · Evidence-based screening</p>
        <p>Region: {region} · Coordinates: {latitude:.2f}, {longitude:.2f}</p>
      </div>
      {completeness_ring(assessment["percent_complete"])}
    </div>
    """,
    unsafe_allow_html=True,
)


# --------------------- Mission Control -------------------

if page == "Mission Control":
    st.subheader("Mission Control")

    if live["errors"]:
        st.warning("Some API requests failed. See Data & Integrations for details.")
    elif marine or weather:
        st.success("Live endpoints returned data.")
    else:
        st.error("No live observations were returned.")

    a, b, c, d = st.columns(4)
    a.metric("Wave height (model)", fmt(marine.get("wave_height"), " m"))
    b.metric("Wind speed (model)", fmt(weather.get("wind_speed_10m"), " km/h"))
    c.metric("Air temperature", fmt(weather.get("temperature_2m"), " °C"))
    d.metric("Sea-surface temp (model)", fmt(marine.get("sea_surface_temperature"), " °C"))

    e, f = st.columns(2)
    e.metric("Chlorophyll-a (satellite)", fmt(chlorophyll.get("value"), " mg/m³", 3))
    f.metric("SST change, past ~7 days", fmt(history_result.get("change"), " °C"))

    st.subheader("Collaborative assessment")
    st.info(f"**{assessment['status']}** — {assessment['summary']}")
    st.caption(assessment["method"])

    if not backend_url:
        st.warning("Backend URL is not configured. Local screening is active.")
    elif backend_error:
        st.error(f"Backend request failed: {backend_error}")
    elif backend_result is not None:
        st.success("FastAPI backend responded successfully.")
        evidence("Backend response", backend_result)

    st.subheader("Agent activity")
    left, right = st.columns(2)
    with left:
        show_agent("🌡️", "Sea Temperature Agent", sst_agent["status"], sst_agent["message"])
        show_agent("📈", "Historical Trend Agent", history_result["status"], history_result["message"])
        show_agent("🟢", "Chlorophyll Agent", chl_agent["status"], chl_agent["message"])
    with right:
        show_agent("🛰️", "Satellite Intelligence Agent", satellite_result["status"], satellite_result["message"])
        show_agent("🌬️", "Weather & Wind Agent", weather_result["status"], weather_result["message"])
        show_agent("🧠", "Reasoning Agent", assessment["status"], assessment["summary"])

    st.subheader("Marine region map")
    map_df = pd.DataFrame([{
        "Region": region, "Latitude": latitude, "Longitude": longitude,
        "Wave height (m)": number(marine.get("wave_height")),
        "SST (°C)": number(marine.get("sea_surface_temperature")),
    }])
    fig = px.scatter_geo(map_df, lat="Latitude", lon="Longitude", hover_name="Region",
                         hover_data=["Wave height (m)", "SST (°C)"],
                         projection="natural earth", title="Selected marine region")
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", font_color="#eaf6ff",
        geo=dict(bgcolor="rgba(0,0,0,0)", showocean=True, oceancolor="#092b40",
                 showland=True, landcolor="#183447", showcoastlines=True),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    st.plotly_chart(fig, width="stretch")


# ------------------------- Agent Lab ---------------------

elif page == "Agent Lab":
    st.subheader("Agent Lab")
    for agent in agents:
        st.markdown(f"### {agent['name']}")
        st.write(f"**Status:** {agent['status']}")
        st.write(agent["message"])
        evidence(f"Inspect {agent['name']}", agent)

    st.subheader("Reasoning Agent")
    st.info(f"**{assessment['status']}** — {assessment['summary']}")
    st.write("**Agents with evidence:**", assessment["available_agents"])
    st.write("**Missing or incomplete:**", assessment["missing_agents"])


# ----------------------- Dive Explorer -------------------

elif page == "Dive Explorer":
    st.subheader("Dive Explorer")
    st.caption("General ocean-science reference for open-ocean zones. Not live data for the selected region.")

    ZONES = [
        (0, "Sunlit (epipelagic)", "#0f6a80",
         "Enough light for photosynthesis. Phytoplankton, small fish and surface predators live here."),
        (200, "Twilight (mesopelagic)", "#0a3f55",
         "Dim light. Many animals migrate up at night to feed. Oxygen can be low in some basins."),
        (1000, "Midnight (bathypelagic)", "#061f2e",
         "No sunlight. Cold, high pressure, and food arrives mostly as sinking particles."),
    ]
    depth = st.slider("Depth (m)", 0, 1000, 0, step=10)
    zone = ZONES[0]
    for z in ZONES:
        if depth >= z[0] and z[0] < 1000:
            zone = z
    if depth >= 1000:
        zone = ZONES[2]

    st.markdown(
        f"""<div class="zone" style="background:linear-gradient({zone[2]},#04101a)">
        <div style="font-size:40px;font-weight:800;color:#eaf6ff">{depth} m</div>
        <h3>{zone[1]}</h3><p>{zone[3]}</p></div>""",
        unsafe_allow_html=True,
    )
    sst = number(marine.get("sea_surface_temperature"))
    if sst is not None:
        st.caption(f"Live surface reading for {region}: {sst:.1f} °C (model). Temperature at depth is not measured here.")


# ----------------------- Ocean Memory --------------------

elif page == "Ocean Memory":
    st.subheader("Ocean Memory")
    rows = history_result.get("rows", [])

    if rows:
        history_df = pd.DataFrame(rows)
        st.line_chart(history_df.set_index("time")["sst"], width="stretch")
        st.dataframe(history_df, width="stretch")
        st.download_button("Download SST CSV", history_df.to_csv(index=False).encode("utf-8"),
                           file_name="orca_sst_model_values.csv", mime="text/csv", width="stretch")
        st.info(history_result["message"])
    else:
        st.warning("No valid past SST time series was returned.")

    st.caption("A short-period SST difference is not a long-term climate anomaly. "
               "A climate anomaly needs a documented historical reference baseline.")


# ---------------------- Evidence Report ------------------

elif page == "Evidence Report":
    st.subheader("Evidence Report")

    report = {
        "application": "ORCA Marine Ecosystem Intelligence",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "region": region,
        "coordinates": {"latitude": latitude, "longitude": longitude},
        "marine": marine, "weather": weather, "chlorophyll": chlorophyll,
        "agents": agents, "assessment": assessment,
        "backend_configured": bool(backend_url), "backend_result": backend_result,
        "api_errors": live["errors"], "backend_error": backend_error,
    }

    st.download_button("Download evidence report JSON", safe_json(report),
                       file_name="orca_evidence_report.json", mime="application/json", width="stretch")
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

    st.markdown("### Chlorophyll (NOAA CoastWatch ERDDAP)")
    if chlorophyll.get("value") is not None:
        st.success(f"Chlorophyll value from: {chlorophyll.get('source')}")
        st.write("Observation day:", chlorophyll.get("time"), "· valid pixels:", chlorophyll.get("pixels"))
    else:
        st.warning("No chlorophyll value returned.")
        st.write(chlorophyll.get("error"))
    st.caption(f"Dataset: {CHL_DATASET} · variable: {CHL_VARIABLE}. Change with ORCA_CHL_DATASET / ORCA_CHL_VARIABLE.")
    evidence("Chlorophyll response", chlorophyll)

    st.markdown("### FastAPI backend")
    if not backend_url:
        st.warning("ORCA_API_URL is not configured.")
    elif backend_error:
        st.error(backend_error)
    else:
        st.success("Backend responded.")
        evidence("Backend response", backend_result)

    evidence("Debug live data response", live)

    st.markdown("### Data limitations")
    st.markdown("""
    - SST, waves, wind and air temperature: Open-Meteo model data, not in-situ measurements.
    - Chlorophyll: VIIRS near-real-time ocean colour via NOAA CoastWatch; cloud gaps are common.
    - Historical anomaly: requires a documented reference baseline.
    - Assessment: data-availability screening, not a validated ecological model.
    """)

    st.markdown("### Official data resources")
    st.markdown(
        "- [Open-Meteo Marine API](https://open-meteo.com/en/docs/marine-weather-api)\n"
        "- [NOAA CoastWatch ERDDAP](https://coastwatch.noaa.gov/erddap/)\n"
        "- [Copernicus Marine Data Store](https://data.marine.copernicus.eu/)"
    )


# --------------------------- Footer ----------------------

st.markdown("---")
st.caption("ORCA · Ocean Reasoning Collaborative Agency · "
           "Not for navigation, emergency response, or definitive ecological diagnosis.")






