
import os
import math
from datetime import datetime, timedelta, timezone

import copernicusmarine
import pandas as pd
import streamlit as st


# Read credentials from Streamlit Cloud Secrets.
# Credentials are never hard-coded into the source file.
username = st.secrets.get(
    "COPERNICUSMARINE_SERVICE_USERNAME", ""
)
password = st.secrets.get(
    "COPERNICUSMARINE_SERVICE_PASSWORD", ""
)

if username and password:
    os.environ["COPERNICUSMARINE_SERVICE_USERNAME"] = username
    os.environ["COPERNICUSMARINE_SERVICE_PASSWORD"] = password


CHLOROPHYLL_DATASET_ID = (
    "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D"
)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_chlorophyll(latitude, longitude):
    """
    Retrieve real Copernicus Marine daily chlorophyll-a data
    near a selected ocean location.

    Returns a dictionary with value, source, time and error.
    No sample or fallback scientific value is generated.
    """

    if not username or not password:
        return {
            "value": None,
            "source": None,
            "time": None,
            "error": "Copernicus Marine credentials are not configured."
        }

    try:
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=8)

        # A small area around the requested point.
        # This keeps the request lightweight.
        radius = 0.05

        ds = copernicusmarine.open_dataset(
            dataset_id=CHLOROPHYLL_DATASET_ID,
            variables=["CHL"],
            minimum_longitude=longitude - radius,
            maximum_longitude=longitude + radius,
            minimum_latitude=latitude - radius,
            maximum_latitude=latitude + radius,
            start_datetime=start_time.strftime("%Y-%m-%d"),
            end_datetime=end_time.strftime("%Y-%m-%d"),
        )

        try:
            if "CHL" not in ds.data_vars:
                return {
                    "value": None,
                    "source": None,
                    "time": None,
                    "error": "CHL variable was not returned by the dataset."
                }

            chl = ds["CHL"]

            # Select the nearest grid cell to the requested coordinates.
            coordinate_names = set(ds.coords)

            lat_name = (
                "latitude" if "latitude" in coordinate_names
                else "lat" if "lat" in coordinate_names
                else None
            )
            lon_name = (
                "longitude" if "longitude" in coordinate_names
                else "lon" if "lon" in coordinate_names
                else None
            )

            if not lat_name or not lon_name:
                return {
                    "value": None,
                    "source": None,
                    "time": None,
                    "error": "Could not identify dataset coordinates."
                }

            chl = chl.sel(
                {
                    lat_name: latitude,
                    lon_name: longitude
                },
                method="nearest"
            )

            # Surface ocean-colour product: choose the latest
            # available time if a time dimension is present.
            if "time" in chl.dims:
                chl = chl.sortby("time")
                observation_time = pd.to_datetime(
                    chl["time"].values[-1], utc=True
                ).isoformat()
                chl = chl.isel(time=-1)
            else:
                observation_time = None

            # Read only the selected grid cell's value.
            raw_value = chl.squeeze().values
            value = float(raw_value)

            if not math.isfinite(value) or value < 0:
                return {
                    "value": None,
                    "source": None,
                    "time": observation_time,
                    "error": (
                        "No valid chlorophyll observation at this location "
                        "and time."
                    )
                }

            return {
                "value": value,
                "source": (
                    "Copernicus Marine — global daily satellite "
                    "ocean-colour L4 dataset"
                ),
                "time": observation_time,
                "error": None
            }

        finally:
            ds.close()

    except Exception as exc:
        return {
            "value": None,
            "source": None,
            "time": None,
            "error": f"Copernicus retrieval failed: {str(exc)[:250]}"
        }






