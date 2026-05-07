import pandas as pd
import plotly.express as px
import requests
import streamlit as st

st.set_page_config(
    page_title="Utah DAQ Energy Dashboard",
    layout="wide"
)

EIA_API_KEY = st.secrets.get("EIA_API_KEY", "")

UTAH_REGISTRATION_2026 = "https://files.tax.utah.gov/tax/esu/mv-registration/2026registrations.xlsx"

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
    r.raise_for_status()

    rows = r.json()["response"]["data"]
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df["period"] = pd.to_datetime(df["period"])

    fuel_map = {
        "COL": "Coal",
        "NG": "Natural gas",
        "SUN": "Solar",
        "WND": "Wind",
        "HYC": "Hydro",
        "NUC": "Nuclear",
        "PEL": "Petroleum",
        "OOG": "Other",
        "OTH": "Other",
    }

    df["Resource"] = df["fueltype"].map(fuel_map).fillna(df["fueltype"])

    monthly = (
        df.groupby(["period", "Resource"], as_index=False)["generation"]
        .sum()
    )

    monthly["Total"] = monthly.groupby("period")["generation"].transform("sum")
    monthly["Share"] = monthly["generation"] / monthly["Total"] * 100
    monthly["Month"] = monthly["period"].dt.strftime("%b %Y")

    return monthly


@st.cache_data(ttl=60 * 60 * 12)
def get_ev_registration_share():
    try:
        xl = pd.ExcelFile(UTAH_REGISTRATION_2026)
    except Exception:
        return None, None

    all_sheets = []

    for sheet in xl.sheet_names:
        try:
            temp = pd.read_excel(xl, sheet_name=sheet)
            temp["sheet_name"] = sheet
            all_sheets.append(temp)
        except Exception:
            pass

    if not all_sheets:
        return None, None

    df = pd.concat(all_sheets, ignore_index=True)
    df.columns = [str(c).strip().lower() for c in df.columns]

    text_cols = df.select_dtypes(include="object").columns.tolist()
    number_cols = df.select_dtypes(include="number").columns.tolist()

    if not text_cols or not number_cols:
        return None, None

    combined_text = df[text_cols].astype(str).agg(" ".join, axis=1).str.lower()

    ev_mask = combined_text.str.contains(
        r"electric|battery electric|plug.?in|phev|bev",
        regex=True,
        na=False
    )

    ldv_mask = combined_text.str.contains(
        r"passenger|auto|car|truck|light|suv",
        regex=True,
        na=False
    )

    count_col = number_cols[-1]

    total_ldv = df.loc[ldv_mask, count_col].sum()
    ev_ldv = df.loc[ev_mask & ldv_mask, count_col].sum()

    if total_ldv == 0:
        total_all = df[count_col].sum()
        ev_all = df.loc[ev_mask, count_col].sum()

        if total_all == 0:
            return None, None

        return ev_all / total_all * 100, "all registrations, fallback estimate"

    return ev_ldv / total_ldv * 100, "light-duty keyword estimate"


@st.cache_data(ttl=60 * 60 * 12)
def get_gsl_elevation():
    url = "https://waterservices.usgs.gov/nwis/dv/"

    params = {
        "format": "json",
        "sites": "10010000",
        "parameterCd": "62614",
        "startDT": "2015-01-01",
        "siteStatus": "all",
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()

    series = r.json()["value"]["timeSeries"][0]["values"][0]["value"]

    df = pd.DataFrame(series)
    df["date"] = pd.to_datetime(df["dateTime"])
    df["elevation_ft"] = pd.to_numeric(df["value"], errors="coerce")

    return df[["date", "elevation_ft"]].dropna()


st.title("Utah DAQ Energy & Air Quality Dashboard")
st.caption("Internal prototype using live public data where available")

gen = get_eia_generation_mix()
ev_share, ev_note = get_ev_registration_share()

if gen.empty:
    st.warning("EIA generation data did not load. Add your EIA_API_KEY in Streamlit secrets.")
else:
    latest_month = gen["period"].max()
    latest = gen[gen["period"] == latest_month]

    renewable_resources = ["Solar", "Wind", "Hydro"]
    fossil_resources = ["Coal", "Natural gas", "Petroleum"]

    renewable_share = latest.loc[
        latest["Resource"].isin(renewable_resources), "Share"
    ].sum()

    fossil_share = latest.loc[
        latest["Resource"].isin(fossil_resources), "Share"
    ].sum()

    solar_share = latest.loc[
        latest["Resource"].eq("Solar"), "Share"
    ].sum()

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Renewable generation share", f"{renewable_share:.1f}%")
    col2.metric("Fossil generation share", f"{fossil_share:.1f}%")
    col3.metric("Solar generation share", f"{solar_share:.1f}%")

    if ev_share is not None:
        col4.metric("EV registration share", f"{ev_share:.2f}%")
    else:
        col4.metric("EV registration share", "Needs parsing")

    st.subheader("Monthly Utah Electricity Generation Mix")

    fig = px.area(
        gen,
        x="Month",
        y="Share",
        color="Resource",
        labels={
            "Share": "Share of generation (%)",
            "Month": "Month",
            "Resource": "Resource"
        },
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(f"EIA latest month loaded: {latest_month.strftime('%B %Y')}")

st.subheader("Great Salt Lake Elevation")

try:
    gsl = get_gsl_elevation()

    fig_gsl = px.line(
        gsl,
        x="date",
        y="elevation_ft",
        labels={
            "date": "Date",
            "elevation_ft": "Elevation, feet above NGVD 1929"
        },
    )

    st.plotly_chart(fig_gsl, use_container_width=True)

    st.caption(
        f"Latest Great Salt Lake elevation loaded: "
        f"{gsl['elevation_ft'].iloc[-1]:,.2f} feet on "
        f"{gsl['date'].iloc[-1].strftime('%B %d, %Y')}. "
        "Source: USGS station 10010000."
    )

except Exception as e:
    st.warning("Great Salt Lake elevation data could not be loaded.")
    st.caption(str(e))

st.subheader("EV Registration Data")

if ev_share is not None:
    st.success(f"Estimated EV registration share: {ev_share:.2f}% ({ev_note})")
else:
    st.warning(
        "The Utah registration workbook loaded, but the app could not confidently "
        "parse LDV electric registration share. We may need to inspect the workbook "
        "tabs and column names, then hard-code the correct sheet/columns."
    )

st.subheader("Program Updates")

charge_yard, industrial, renewable = st.columns(3)

with charge_yard:
    st.info(
        "**Charge Your Yard**\n\n"
        "The Charge Your Yard program has removed **XXX fuel-based equipment units** "
        "from use, reducing air quality emissions by **XXX per year**. Program staff "
        "are continuing to track equipment retirements, rebate participation, and "
        "estimated emissions benefits."
    )

with industrial:
    st.success(
        "**Industrial Efficiency Improvements**\n\n"
        "DAQ-supported industrial efficiency improvements are helping facilities reduce "
        "fuel use, improve process controls, and lower emissions intensity. Recent "
        "activities include identifying high-priority equipment upgrades, evaluating "
        "cost-effective efficiency opportunities, and coordinating with facility staff "
        "on implementation timelines."
    )

with renewable:
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
    "Sources: EIA electricity API for generation mix; Utah State Tax Commission "
    "vehicle registration workbook for registration data; USGS daily values service "
    "for Great Salt Lake elevation."
)
