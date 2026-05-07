import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(
    page_title="Utah DAQ Energy Dashboard",
    layout="wide"
)

st.title("Utah DAQ Energy & Air Quality Dashboard")
st.caption("Internal prototype | Mock data until live data connections are added")

data = pd.DataFrame({
    "Month": ["Jan 2026", "Feb 2026", "Mar 2026"],
    "Coal": [52, 50, 47],
    "Natural gas": [24, 24, 23],
    "Solar": [8, 10, 13],
    "Wind": [8, 8, 8],
    "Hydro": [4, 4, 5],
    "Other": [4, 4, 4],
})

latest = data.iloc[-1]
renewables = latest["Solar"] + latest["Wind"] + latest["Hydro"]
fossil = latest["Coal"] + latest["Natural gas"]

col1, col2, col3 = st.columns(3)
col1.metric("Renewable generation share", f"{renewables}%")
col2.metric("Fossil generation share", f"{fossil}%")
col3.metric("Solar generation share", f"{latest['Solar']}%")

st.subheader("Monthly Utah Electricity Generation Mix")

fig = px.area(
    data,
    x="Month",
    y=["Coal", "Natural gas", "Solar", "Wind", "Hydro", "Other"],
    labels={"value": "Share of generation (%)", "variable": "Resource"}
)

st.plotly_chart(fig, use_container_width=True)

st.subheader("Program Updates")

st.info(
    "The Charge Your Yard program has removed XXX fuel-based equipment units "
    "from use, reducing air quality emissions by XXX per year."
)

c1, c2 = st.columns(2)
with c1:
    st.warning("Program Placeholder 1: Add monthly update, milestone, risks, and next steps.")
with c2:
    st.warning("Program Placeholder 2: Add program owner, metric, and data source.")
