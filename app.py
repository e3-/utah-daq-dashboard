import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="Beehive Emissions Reduction Plan Dashboard",
    layout="wide"
)

EIA_API_KEY = st.secrets.get("EIA_API_KEY", "")

UTAH_REGISTRATION_2026 = (
    "https://files.tax.utah.gov/tax/esu/mv-registration/2026registrations.xlsx"
)

PARTICIPATING_COMMUNITIES = [
    "Town of Alta",
    "Town of Castle Valley",
    "Coalville City",
    "Cottonwood Heights",
    "Francis City",
    "Grand County (unincorporated)",
    "City of Emigration Canyon",
    "City of Holladay",
    "Kearns City",
    "Midvale City",
    "Millcreek City",
    "Moab City",
    "Oakley City",
    "Ogden City",
    "Park City",
    "Salt Lake City",
    "Salt Lake County (unincorporated)",
    "Springdale Town",
    "Summit County (unincorporated)",
]


@st.cache_data(ttl=60 * 60 * 12)
def get_eia_generation_mix():
    if not EIA_API_KEY:
        return pd.DataFrame()

    url = "https://api.eia.gov/v2/electricity/electric-power-operational-data/data/"

    params = {
        "api_key": EIA_API_KEY,
        "frequency": "monthly",
        "data[0]": "generation",
        "facets[stateid][]": "UT",
        "start": "2023-01",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }

    r = requests.get(url, params=params, timeout=30)

    # SAFE ERROR HANDLING (fixes your crash)
    if r.status_code != 200:
        st.warning(
            "EIA generation data did not load. This is usually caused by an invalid API key, "
            "a Streamlit secrets formatting issue, or an EIA API endpoint change."
        )
        st.caption(f"EIA status code: {r.status_code}")
        return pd.DataFrame()

    rows = r.json().get("response", {}).get("data", [])
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df.columns = [str(c).strip() for c in df.columns]

    fuel_col = None
    for col in ["fueltype", "fueltypeid", "fueltypeDescription"]:
        if col in df.columns:
            fuel_col = col
            break

    if fuel_col is None:
        return pd.DataFrame()

    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df["period"] = pd.to_datetime(df["period"], errors="coerce")

    fuel_map = {
        "COL": "Coal",
        "NG": "Natural gas",
        "SUN": "Solar",
        "WND": "Wind",
        "HYC": "Hydro",
        "NUC": "Nuclear",
        "PEL": "Petroleum",
        "OTH": "Other",
    }

    df["Resource"] = df[fuel_col].map(fuel_map).fillna(df[fuel_col])

    monthly = (
        df.dropna(subset=["period", "generation"])
        .groupby(["period", "Resource"], as_index=False)["generation"]
        .sum()
    )

    monthly["Total"] = monthly.groupby("period")["generation"].transform("sum")
    monthly = monthly[monthly["Total"] > 0]
    monthly["Share"] = monthly["generation"] / monthly["Total"] * 100

    return monthly


@st.cache_data(ttl=60 * 60 * 12)
def get_ev_registration_share():
    try:
        xl = pd.ExcelFile(UTAH_REGISTRATION_2026)
    except Exception:
        return None, None

    dfs = []
    for sheet in xl.sheet_names:
        try:
            temp = pd.read_excel(xl, sheet_name=sheet)
            dfs.append(temp)
        except Exception:
            pass

    if not dfs:
        return None, None

    df = pd.concat(dfs, ignore_index=True)
    df.columns = [str(c).lower() for c in df.columns]

    text_cols = df.select_dtypes(include="object").columns
    num_cols = df.select_dtypes(include="number").columns

    if len(text_cols) == 0 or len(num_cols) == 0:
        return None, None

    combined = df[text_cols].astype(str).agg(" ".join, axis=1).str.lower()

    ev_mask = combined.str.contains("electric|bev|phev", na=False)
    ldv_mask = combined.str.contains("car|truck|suv|passenger", na=False)

    count_col = num_cols[-1]

    total = df.loc[ldv_mask, count_col].sum()
    ev = df.loc[ev_mask & ldv_mask, count_col].sum()

    if total == 0:
        return None, None

    return ev / total * 100, "estimated from workbook"


@st.cache_data(ttl=60 * 60 * 12)
def get_gsl_elevation():
    url = "https://waterservices.usgs.gov/nwis/dv/"

    params = {
        "format": "json",
        "sites": "10010000",
        "parameterCd": "62614",
        "startDT": "2015-01-01",
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()

    series = r.json()["value"]["timeSeries"][0]["values"][0]["value"]

    df = pd.DataFrame(series)
    df["date"] = pd.to_datetime(df["dateTime"])
    df["elevation_ft"] = pd.to_numeric(df["value"], errors="coerce")

    return df.dropna()


# ===========================
# DASHBOARD
# ===========================

st.title("Beehive Emissions Reduction Plan Dashboard")

# -------- ELECTRIC GENERATION --------
st.header("Electric Generation")
st.write(
    "BERP identified increasing zero emissions generation as a crucial strategy "
    "to reducing generation-related emissions."
)

gen = get_eia_generation_mix()

if gen.empty:
    st.warning("EIA data unavailable. Check API key.")
else:
    fig = px.area(gen, x="period", y="Share", color="Resource")
    st.plotly_chart(fig, use_container_width=True)

# -------- WORKING LANDS --------
st.header("Working Lands")
st.write(
    "BERP identified maintaining inflows to the Great Salt Lake as a critical "
    "measure as it supports ecosystem health, dust suppression, and carbon "
    "sequestration in the lakebed."
)

gsl = get_gsl_elevation()
fig = px.line(gsl, x="date", y="elevation_ft")
st.plotly_chart(fig, use_container_width=True)

# -------- TRANSPORTATION --------
st.header("Transportation")
st.write(
    "BERP identified increasing adoption of Zero Emissions Vehicles as a crucial "
    "strategy to reducing transportation-related emissions."
)

ev, note = get_ev_registration_share()

if ev:
    st.metric("EV Share", f"{ev:.2f}%")
else:
    st.warning("Could not parse EV share")

# -------- PROGRAMS --------
st.header("Program Updates")

c1, c2, c3 = st.columns(3)

with c1:
    st.info("Charge Your Yard: XXX units removed, XXX emissions reduced")

with c2:
    st.success("Industrial efficiency improvements underway across sectors")

with c3:
    st.warning(
        "Utah Renewable Communities approved and under implementation. "
        "Participants: " + ", ".join(PARTICIPATING_COMMUNITIES)
    )
