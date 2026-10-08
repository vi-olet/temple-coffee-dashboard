"""Market Overview — the 4-county study area, stores, competitors, demographics (REAL + PROXY)."""

import numpy as np
import pandas as pd
import streamlit as st

from lib import data, ui

ui.hero("Where should Temple Coffee open its tenth store?",
        "The method, one map layer at a time: from public data to a ranked list of sites",
        "Portfolio study built on public data")
ui.label("The question: a good site must pass two tests")
ui.numbered_cards([
    ("Are there enough customers nearby?",
     "People, income and competition around a site decide how busy a café can be."),
    ("Will it take customers from our own stores?",
     "This is cannibalization. A site that only moves sales between stores adds little."),
])
ui.page_header(
    "Start with who lives where", ("REAL", "PROXY"),
    "Census block groups (ACS 2023 five-year) across Sacramento, Yolo, El Dorado and Placer counties, the nine "
    "Temple stores, and every competing café the models use. Ratings and review counts are a dated, "
    "hand-collected snapshot standing in for popularity.",
    kicker="Step 1 of 7  ·  People, rivals, reach",
)

bg = data.table("block_groups")
stores = data.table("stores")
comp_all = data.table("competitors")
comp = data.open_competitors()
att = data.table("attractiveness_snapshot")

# ----------------------------------------------------------------------------- KPIs
pop_total = pd.to_numeric(bg["population_total"], errors="coerce").sum()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Temple stores", f"{len(stores)}", help="REAL: geocoded with the Census Bureau geocoder, 9/9 matched (D7).")
c2.metric("Competitors (open)", f"{len(comp):,}",
          help=f"REAL: OSM points within 15 km of the stores (D8). Excludes {int(comp_all['verified_closed'].sum())} "
               f"verified closed (D39) and {int(comp_all['is_temple_brand_duplicate'].sum())} Temple OSM duplicate(s) (D34).")
c3.metric("Block groups", f"{len(bg):,}", help="REAL: ACS 2023 5-yr, 4 counties (D5/D6).")
c4.metric("Population covered", f"{pop_total / 1e6:.2f} M", help="REAL: sum of ACS B01003 across the block groups.")

# ----------------------------------------------------------------------------- controls
METRICS = {
    "Population density (people / km²)": ("density", lambda v: f"{v:,.0f}", "population_total_moe_flag"),
    "Median household income": ("median_household_income", lambda v: f"${v / 1000:,.0f}k", "median_household_income_moe_flag"),
    "Median age": ("median_age", lambda v: f"{v:.0f}", "median_age_moe_flag"),
    "Population": ("population_total", lambda v: f"{v:,.0f}", "population_total_moe_flag"),
}
left, right = st.columns([2, 3])
metric_label = left.selectbox("Shade block groups by", list(METRICS), key="mo_metric")
show = right.pills("Show", ["Competitors", "15-min drive-time areas", "Fade MOE-flagged estimates"],
                   selection_mode="multi", default=["Competitors", "15-min drive-time areas"], key="mo_layers")
col, fmt, flag_col = METRICS[metric_label]


@st.cache_data(show_spinner=False)
def bg_features(col: str, flag_col: str, fade_flagged: bool):
    b = data.table("block_groups").copy()
    pop = pd.to_numeric(b["population_total"], errors="coerce")
    b["density"] = pop / b["area_sq_km"].where(b["area_sq_km"] > 0)
    vals = pd.to_numeric(b[col], errors="coerce")
    idx, edges = ui.quantile_classes(vals)
    fills = ui.seq_fill(idx, max(len(edges) - 1, 1))
    flagged = b[flag_col].fillna(False).astype(bool).to_numpy()
    if fade_flagged:
        fills = [f[:3] + [45] if fl and f is not ui.NO_DATA else f for f, fl in zip(fills, flagged)]
    f = METRICS_FMT[col]
    b["fill"] = fills
    ui.set_tips(
        b,
        [f"Block group {g}" for g in b["geoid"]],
        [f"{cn} County" for cn in b["county_name"]],
        [f"{metric_label_for(col)}: {'no estimate' if not np.isfinite(v) else f(v)}" for v in vals],
        ["Margin of error over 30% of the estimate (D10)" if fl else "ACS 2023 5-yr · REAL" for fl in flagged],
    )
    return data.feature_collection(b, ["fill"]), edges, int(flagged.sum()), int((~np.isfinite(vals)).sum())


METRICS_FMT = {v[0]: v[1] for v in METRICS.values()}


def metric_label_for(c: str) -> str:
    return next(k for k, v in METRICS.items() if v[0] == c)


feats, edges, n_flagged, n_null = bg_features(col, flag_col, "Fade MOE-flagged estimates" in (show or []))

layers = [ui.polygon_layer(feats, "block_groups", line_hex="#FFFFFF", line_px=0.3)]
if "15-min drive-time areas" in (show or []):
    iso = data.table("isochrones")
    iso = iso[iso["time_band_minutes"] == 15].copy()
    names = data.store_names()
    ui.set_tips(iso, [names.get(int(s)) for s in iso["store_id"]], ["15-minute drive time"] * len(iso), None,
                ["OpenRouteService · REAL"] * len(iso))
    layers.append(ui.polygon_layer(data.feature_collection(iso, []), "isochrones", filled=False,
                                   line_hex=ui.ISO_LINE, line_px=1.5, pickable=False))
if "Competitors" in (show or []):
    layers.append(ui.competitor_layer(comp))
layers.append(ui.store_layer(stores))

st.pydeck_chart(ui.deck(layers), height=560, key="mo_map")
legend = ui.class_legend(edges, fmt) + [("dot", ui.STORE, "Temple store")]
if "Competitors" in (show or []):
    legend.append(("dot", ui.COMPETITOR, "Competitor (open)"))
if "15-min drive-time areas" in (show or []):
    legend.append(("line", ui.ISO_LINE, "15-minute drive time"))
ui.legend_html(legend)
ui.caption(
    f"{ui.tags('REAL')} Classes are quantiles (7 bins). {n_flagged:,} of {len(bg):,} block groups have a margin of error "
    f"above 30% of the estimate for this variable (D10) — expected at block-group resolution, not a data bug. "
    f"{n_null:,} block group(s) have no published estimate (gray)."
)

# ----------------------------------------------------------------------------- store table
ui.section("The nine stores", "The setting")
a = att[att["entity_type"] == "store"].set_index("entity_id")
t = stores[["store_id", "name", "area", "address", "hours", "reduced_hours_flag"]].copy()
t["rating"] = t["store_id"].map(a["rating"])
t["review_count"] = t["store_id"].map(a["review_count"])
snap_date = pd.to_datetime(a["snapshot_date"]).max()
st.dataframe(
    t.drop(columns="store_id"), hide_index=True, width="stretch",
    column_config={
        "name": "Store", "area": "Area", "address": "Address", "hours": "Hours",
        "reduced_hours_flag": st.column_config.CheckboxColumn("Reduced hours", help="D1: only 16th Street."),
        "rating": st.column_config.NumberColumn("Rating (PROXY)", format="%.1f"),
        "review_count": st.column_config.NumberColumn("Reviews (PROXY)", format="%d"),
    },
)
ui.caption(
    f"{ui.tags('REAL', 'PROXY')} Addresses and hours from Temple's locations page. Rating and review count are a "
    f"manual snapshot dated {snap_date:%b %d, %Y} (D2), not a live feed and not sales."
)

with st.expander("Known gaps in this layer"):
    st.markdown(
        "- **OSM competitor coverage likely undercounts.** Tagging completeness varies; widening the radius to "
        "15 km (D8) fixed reach into Roseville, not tagging gaps.\n"
        "- **Block-group margins of error are large.** About three in four block groups have at least one flagged "
        "variable. Flags are carried per variable (D10) rather than aggregating to tracts.\n"
        "- **Geometry here is simplified for display** (~11 m tolerance). Every analysis used the full-resolution "
        "geometry in PostGIS."
    )
