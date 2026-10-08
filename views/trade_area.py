"""Trade Area Explorer — 5/10/15-min drive-time trade areas per store (REAL geometry, MODELED scores)."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, ui

ui.page_header(
    "Draw each store's territory", ("REAL", "MODELED"),
    "Drive-time isochrones from OpenRouteService (REAL) with block-group demographics apportioned by area overlap "
    "(D24). The market-attractiveness score is a MODELED composite of income, population density and competitor "
    "scarcity (D25–D27).",
    kicker="Step 3 of 7  ·  Trade areas",
)

stores = data.table("stores")
ta = data.table("trade_areas")
iso = data.table("isochrones")
names = data.store_names()

c1, c2 = st.columns([2, 3])
store_name = c1.selectbox("Store", stores["name"].tolist(), key="ta_store")
band = c2.segmented_control("Drive time", [5, 10, 15], default=10, format_func=lambda b: f"{b} min", key="ta_band") or 10
sid = int(stores.loc[stores["name"] == store_name, "store_id"].iloc[0])
row = ta[(ta["store_id"] == sid) & (ta["time_band_minutes"] == band)]
if row.empty:
    st.warning(f"No trade_areas row for {store_name} at {band} min.")
    st.stop()
r = row.iloc[0]


def _fmt(v, f):
    return "—" if pd.isna(v) else f(v)


m1, m2, m3, m4 = st.columns(4)
m1.metric("Population covered", _fmt(r["population_covered"], lambda v: f"{v:,.0f}"),
          help="Area-weighted sum of ACS population across the block groups the isochrone touches (D24).")
m2.metric("Pop.-weighted median income", _fmt(r["population_weighted_income"], lambda v: f"${v:,.0f}"))
m3.metric("Pop.-weighted median age", _fmt(r["population_weighted_age"], lambda v: f"{v:.1f}"))
m4.metric("Density (people / km²)", _fmt(r["population_density"], lambda v: f"{v:,.0f}"))
m5, m6, m7, m8 = st.columns(4)
m5.metric("Competitors inside", _fmt(r["competitor_count"], lambda v: f"{v:.0f}"),
          help="Open OSM competitors inside the isochrone; closed (D39) and Temple duplicates (D34) excluded.")
m6.metric("Nearest competitor", _fmt(r["nearest_competitor_distance_m"], lambda v: f"{v:,.0f} m"))
m7.metric("Attractiveness (across stores)", _fmt(r["market_attractiveness_score"], lambda v: f"{v:.0f} / 100"),
          help="MODELED. Min-max scaled across all 27 store×band rows, so comparable store to store (D27).")
m8.metric("Attractiveness (within store)", _fmt(r["market_attractiveness_within_store"], lambda v: f"{v:.0f} / 100"),
          help="MODELED. Scaled within this store's own three bands only — shows how the market changes with "
               "distance, not how it compares to other stores.")
touched = r["block_groups_touched"]
ui.caption(
    f"{ui.tags('REAL')} for population, income, age, competitors · {ui.tags('MODELED')} for the two scores. "
    f"{_fmt(touched, lambda v: f'{v:.0f}')} block groups touched; margin of error above 30% in "
    f"{_fmt(r['population_moe_flagged_block_group_count'], lambda v: f'{v:.0f}')} (population), "
    f"{_fmt(r['income_moe_flagged_block_group_count'], lambda v: f'{v:.0f}')} (income) and "
    f"{_fmt(r['age_moe_flagged_block_group_count'], lambda v: f'{v:.0f}')} (age) of them (D10)."
)

# ----------------------------------------------------------------------------- map
s = stores[stores["store_id"] == sid].iloc[0]
mine = iso[iso["store_id"] == sid].sort_values("time_band_minutes", ascending=False).copy()
mine["fill"] = [ui._rgb(ui.ISO_FILL[b], 200 if b == band else 40) for b in mine["time_band_minutes"]]
ui.set_tips(mine, [store_name] * len(mine), [f"{b}-minute drive time" for b in mine["time_band_minutes"]],
            [f"{a:,.1f} km²" for a in mine["area_sq_km"]], ["OpenRouteService · REAL"] * len(mine))
layers = [ui.polygon_layer(data.feature_collection(mine, ["fill"]), "isochrones",
                           line_hex=ui.ISO_LINE, line_px=1.4)]
layers.append(ui.competitor_layer(data.open_competitors()))
layers.append(ui.store_layer(stores))
zoom = {5: 12.3, 10: 11.3, 15: 10.6}[band]
st.pydeck_chart(ui.deck(layers, ui.view_for(s["lon"], s["lat"], zoom)), height=470, key="ta_map")
ui.legend_html([("swatch", ui.ISO_FILL[band], f"{band}-minute drive (selected)"),
                ("line", ui.ISO_LINE, "other drive-time bands"), ("dot", ui.STORE, "Temple store"),
                ("dot", ui.COMPETITOR, "Competitor (open)")])
ui.caption("Isochrones follow the real street network, which is why they bend around the American and Sacramento "
           "Rivers and the I-80 causeway instead of forming circles (outline Sec. 7).")

# ----------------------------------------------------------------------------- compare
ui.section(f"All nine stores at {band} minutes", "Compare")
cmp_ = ta[ta["time_band_minutes"] == band].copy()
cmp_["store"] = cmp_["store_id"].map(names)
cmp_ = cmp_.sort_values("market_attractiveness_score")
colors = [ui.STORE if n == store_name else ui.MUTED_BAR for n in cmp_["store"]]
fig = go.Figure(go.Bar(
    x=cmp_["market_attractiveness_score"], y=cmp_["store"], orientation="h", marker_color=colors,
    marker_line_width=0, hovertemplate="%{y}: %{x:.0f} / 100<extra></extra>",
))
fig.update_layout(height=330, margin=dict(l=10, r=10, t=30, b=10), bargap=0.35,
                  title=dict(text="Market attractiveness, across-store scale (MODELED)", font=dict(size=14)),
                  xaxis=dict(range=[0, 100], title=None, gridcolor="#EDE6DF"), yaxis=dict(title=None))
st.plotly_chart(fig, width="stretch", key="ta_bar")

tbl = cmp_.sort_values("market_attractiveness_score", ascending=False)[[
    "store", "population_covered", "population_weighted_income", "population_weighted_age", "population_density",
    "competitor_count", "nearest_competitor_distance_m", "market_attractiveness_score"]]
st.dataframe(tbl, hide_index=True, width="stretch", column_config={
    "store": "Store",
    "population_covered": st.column_config.NumberColumn("Population", format="%d"),
    "population_weighted_income": st.column_config.NumberColumn("Income", format="$%d"),
    "population_weighted_age": st.column_config.NumberColumn("Age", format="%.1f"),
    "population_density": st.column_config.NumberColumn("People / km²", format="%d"),
    "competitor_count": st.column_config.NumberColumn("Competitors", format="%d"),
    "nearest_competitor_distance_m": st.column_config.NumberColumn("Nearest comp. (m)", format="%d"),
    "market_attractiveness_score": st.column_config.ProgressColumn("Attractiveness (MODELED)", min_value=0,
                                                                   max_value=100, format="%.0f"),
})
ui.caption("Phase 3 finding: Davis is a separate, lower-density micro-market about 15 miles from the rest of the "
           "chain, and its scores are the weakest at every band.")
ui.note("People counted = Σ population × share of the neighborhood's area inside the zone (area-weighted "
        "apportionment, D24). Income and age are averaged with those people as weights. Score = equal-weighted sum "
        "of z-scores for income, density and rival scarcity across all 27 zones, rescaled 0–100. Assumes people are "
        "spread evenly within a block group.")
