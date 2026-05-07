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

    series_map = {
        "Coal": "ELEC.GEN.COW-UT-99.M",
        "Natural gas": "ELEC.GEN.NG-UT-99.M",
        "Solar": "ELEC.GEN.SUN-UT-99.M",
        "Wind": "ELEC.GEN.WND-UT-99.M",
        "Hydro": "ELEC.GEN.HYC-UT-99.M",
        "Petroleum": "ELEC.GEN.PEL-UT-99.M",
        "Other": "ELEC.GEN.OTH-UT-99.M",
    }

    all_rows = []

    for resource, series_id in series_map.items():
        url = f"https://api.eia.gov/v2/seriesid/{series_id}"

        try:
            r = requests.get(
                url,
                params={"api_key": EIA_API_KEY},
                timeout=30,
            )

            if r.status_code != 200:
                continue

            data = r.json().get("response", {}).get("data", [])

            for row in data:
                all_rows.append(
                    {
                        "period": row.get("period"),
                        "Resource": resource,
                        "generation": row.get("value"),
                    }
                )

        except Exception:
            continue

    df = pd.DataFrame(all_rows)

    if df.empty:
        return pd.DataFrame()

    df["generation"] = pd.to_numeric(df["generation"], errors="coerce")
    df["period"] = pd.to_datetime(df["period"], errors="coerce")
    df = df.dropna(subset=["period", "generation"])

    monthly = (
        df.groupby(["period", "Resource"], as_index=False)["generation"]
        .sum()
    )

    monthly["Total"] = monthly.groupby("period")["generation"].transform("sum")
    monthly = monthly[monthly["Total"] > 0]
    monthly["Share"] = monthly["generation"] / monthly["Total"] * 100

    return monthly.sort_values("period")


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

    zero_emissions_resources = ["Solar", "Wind", "Hydro"]
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
    st.metric("Estimated EV registration share", f"{ev:.2f}%")
    st.caption(f"Calculation note: {note}")
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
