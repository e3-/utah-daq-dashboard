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

    url = "https://api.eia.gov/v2/electricity/electricity-power-operational-data/data/"

    params = {
        "api_key": EIA_API_KEY,
        "frequency": "monthly",
        "data[0]": "generation",
        "facets[stateid][]": "UT",
        "facets[sectorid][]": "99",
        "start": "2023-01",
        "sort[0][column]": "period",
        "sort[0][direction]": "asc",
        "offset": 0,
        "length": 5000,
    }

    try:
        r = requests.get(url, params=params, timeout=30)

        if r.status_code != 200:
            st.caption(f"EIA status code: {r.status_code}")
            return pd.DataFrame()

        rows = r.json().get("response", {}).get("data", [])
        df = pd.DataFrame(rows)

        if df.empty:
            return pd.DataFrame()

        df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
        df["period"] = pd.to_datetime(df["period"], errors="coerce")

        fuel_col = None
        for col in ["fueltypeid", "fueltype", "fuelTypeId"]:
            if col in df.columns:
                fuel_col = col
                break

        fuel_name_col = None
        for col in ["fuelTypeDescription", "fueltypeDescription", "fueltype"]:
            if col in df.columns:
                fuel_name_col = col
                break

        fuel_map = {
            "COL": "Coal",
            "NG": "Natural gas",
            "SUN": "Solar",
            "WND": "Wind",
            "HYC": "Hydro",
            "NUC": "Nuclear",
            "PEL": "Petroleum",
            "OTH": "Other",
            "OOG": "Other",
        }

        if fuel_col:
            df["Resource"] = df[fuel_col].astype(str).str.upper().map(fuel_map)

        if "Resource" not in df.columns or df["Resource"].isna().all():
            if fuel_name_col:
                df["Resource"] = df[fuel_name_col].astype(str).str.title()
            else:
                return pd.DataFrame()

        df["Resource"] = df["Resource"].fillna("Other")

        monthly = (
            df.dropna(subset=["period", "generation"])
            .groupby(["period", "Resource"], as_index=False)["generation"]
            .sum()
        )

        monthly["Total"] = monthly.groupby("period")["generation"].transform("sum")
        monthly = monthly[monthly["Total"] > 0]
        monthly["Share"] = monthly["generation"] / monthly["Total"] * 100

        return monthly.sort_values("period")

    except Exception as e:
        st.caption(f"EIA connection note: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=60 * 60 * 12)
def get_ev_registration_share():
    try:
        df = pd.read_excel(
            UTAH_REGISTRATION_2026,
            sheet_name="Table 6",
            header=None
        )
    except Exception:
        return None, None

    data = df.iloc[6:].copy()

    vehicle_type_col = 1
    electric_col = 6
    plug_in_hybrid_col = 12
    total_col = 15

    data[vehicle_type_col] = data[vehicle_type_col].astype(str).str.strip()

    ldv = data[
        data[vehicle_type_col].isin(
            ["Passenger - Standard", "Light Truck"]
        )
    ].copy()

    electric = pd.to_numeric(ldv[electric_col], errors="coerce").fillna(0).sum()
    plug_in_hybrid = (
        pd.to_numeric(ldv[plug_in_hybrid_col], errors="coerce").fillna(0).sum()
    )
    total = pd.to_numeric(ldv[total_col], errors="coerce").fillna(0).sum()

    if total == 0:
        return None, None

    share = (electric + plug_in_hybrid) / total * 100

    note = (
        "Utah Tax Commission 2026 registrations, Table 6. "
        "Light-duty proxy includes Passenger - Standard and Light Truck. "
        "ZEV proxy includes Electric and Plug-in Hybrid."
    )

    return share, note


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
    df["date"] = pd.to_datetime(df["dateTime"], errors="coerce")
    df["elevation_ft"] = pd.to_numeric(df["value"], errors="coerce")

    return df.dropna(subset=["date", "elevation_ft"])


st.title("Beehive Emissions Reduction Plan Dashboard")
st.caption(
    "Prototype dashboard for discussion purposes. Data sources are live where available; "
    "some metrics are illustrative or under development."
)

st.header("Electric Generation")
st.write(
    "BERP identified increasing zero emissions generation as a crucial strategy "
    "to reducing generation-related emissions."
)

gen = get_eia_generation_mix()

if gen.empty:
    st.info(
        "Electric generation data connection is under development. Once connected, "
        "this section will display Utah's monthly generation mix by resource."
    )
else:
    latest_month = gen["period"].max()
    latest = gen[gen["period"] == latest_month]

    zero_emissions_resources = ["Solar", "Wind", "Hydro", "Nuclear"]
    fossil_resources = ["Coal", "Natural gas", "Petroleum"]

    zero_emissions_share = latest.loc[
        latest["Resource"].isin(zero_emissions_resources), "Share"
    ].sum()

    fossil_share = latest.loc[
        latest["Resource"].isin(fossil_resources), "Share"
    ].sum()

    col1, col2 = st.columns(2)
    col1.metric("Zero-emissions generation share", f"{zero_emissions_share:.1f}%")
    col2.metric("Fossil generation share", f"{fossil_share:.1f}%")

    fig = px.area(
        gen,
        x="period",
        y="Share",
        color="Resource",
        labels={
            "period": "Month",
            "Share": "Share of generation (%)",
            "Resource": "Resource",
        },
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"EIA latest month loaded: {latest_month.strftime('%B %Y')}")

st.header("Working Lands")
st.write(
    "BERP identified maintaining inflows to the Great Salt Lake as a critical "
    "measure as it supports ecosystem health, dust suppression, and carbon "
    "sequestration in the lakebed."
)

try:
    gsl = get_gsl_elevation()

    fig = px.line(
        gsl,
        x="date",
        y="elevation_ft",
        labels={
            "date": "Date",
            "elevation_ft": "Elevation, feet above NGVD 1929",
        },
    )

    st.plotly_chart(fig, use_container_width=True)

    st.caption(
        f"Latest Great Salt Lake elevation loaded: "
        f"{gsl['elevation_ft'].iloc[-1]:,.2f} feet on "
        f"{gsl['date'].iloc[-1].strftime('%B %d, %Y')}. "
        "Source: USGS station 10010000."
    )

except Exception:
    st.info(
        "Great Salt Lake elevation data connection is under development. Once connected, "
        "this section will display recent lake elevation trends."
    )

st.header("Transportation")
st.write(
    "BERP identified increasing adoption of Zero Emissions Vehicles as a crucial "
    "strategy to reducing transportation-related emissions."
)

ev, note = get_ev_registration_share()

if ev is not None:
    st.metric("EV share of light-duty registrations", f"{ev:.2f}%")
    st.caption(note)
else:
    st.info(
        "EV registration share is under development. Once finalized, this section will "
        "display the share of Utah light-duty vehicle registrations that are zero-emission vehicles."
    )

st.header("Program Updates")

c1, c2, c3 = st.columns(3)

with c1:
    st.info(
        "**Charge Your Yard**\n\n"
        "The Charge Your Yard program has removed **XXX fuel-based equipment units** "
        "from use, reducing air quality emissions by **XXX per year**. Program staff "
        "are continuing to track equipment retirements, rebate participation, and "
        "estimated emissions benefits."
    )

with c2:
    st.success(
        "**Industrial Efficiency Improvements**\n\n"
        "DAQ-supported industrial efficiency improvements are helping facilities reduce "
        "fuel use, improve process controls, and lower emissions intensity. Recent "
        "activities include identifying high-priority equipment upgrades, evaluating "
        "cost-effective efficiency opportunities, and coordinating with facility staff "
        "on implementation timelines."
    )

with c3:
    st.warning(
        "**Utah Renewable Communities**\n\n"
        "The Utah Renewable Communities program has received regulatory approval and "
        "is now moving into implementation. Participating communities include:\n\n"
        + ", ".join(PARTICIPATING_COMMUNITIES)
        + ".\n\n"
        "Together, these communities represent **XX% of statewide electricity demand**. "
        "This placeholder should be replaced once the final demand-share calculation "
        "has been reviewed."
    )

st.divider()

st.caption(
    "Sources: EIA electricity data for generation mix; Utah State Tax Commission "
    "vehicle registration workbook for registration data; USGS daily values service "
    "for Great Salt Lake elevation."
)
