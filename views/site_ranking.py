"""Site Ranking — the Phase 6 shortlist, the D71 error-band ranking, and why each site scores as it does."""

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from lib import data, ui
from lib.huff import PERSISTED_LAMBDAS

ui.page_header(
    "Screen the region, then rank the shortlist", ("MODELED", "REAL"),
    "30 candidates on real OSM commercial land, screened from a 1 km grid (D61). A site is filtered if any existing "
    "store would lose more than 5% of its Huff demand; the rest are ranked by demand only in whole bands of model "
    "error, then by least Temple demand taken (D71).",
    kicker="Step 6 of 7  ·  The search",
)

cands = data.candidates()
run = data.primary_demand_run()
band_w = float(run["cv_rmse_log"])
stab = data.rank_stability()
names = data.store_names()

c1, c2 = st.columns([2, 3])
lam = c1.segmented_control("λ (distance decay)", list(PERSISTED_LAMBDAS), default=2.5, key="sr_lambda") or 2.5
method = c2.segmented_control("Ranking", ["Headline: error bands (D71)", "Old composite (D63, comparison)"],
                              default="Headline: error bands (D71)", key="sr_method") or "Headline: error bands (D71)"
headline = method.startswith("Headline")
weight = 0.5
if not headline:
    weight = st.select_slider("Composite demand weight w", [0.3, 0.4, 0.5, 0.6, 0.7], value=0.5, key="sr_weight",
                              help="composite = 100 × (w × demand percentile + (1 − w) × cannibalization percentile)")

r = data.rankings_at(lam, weight).merge(stab, on="candidate_id", how="left")
old = data.rankings_at(lam, 0.5)[["candidate_id", "rank"]].rename(columns={"rank": "composite_rank_w50"})
r = r.merge(old, on="candidate_id", how="left")
rank_col = "error_band_rank" if headline else "rank"
passing = r[r["passes_filter"]].sort_values([rank_col, "total_cannibalization_demand"])
filtered = r[~r["passes_filter"]].sort_values("max_store_cannibalization_pct", ascending=False)

# ----------------------------------------------------------------------------- the honest caveat, up front
n_bands = passing["demand_band"].nunique()
spread = passing["predicted_log_review_count"].max() - passing["predicted_log_review_count"].min() if len(passing) else 0
if headline and n_bands == 1:
    st.info(
        f"**Demand can't separate these sites.** All {len(passing)} passing candidates sit within one model error of "
        f"each other (predicted spread {spread:.2f} log units vs. model error {band_w:.2f}), so they share demand band 0 "
        "and the order comes entirely from cannibalization. Read this as *where a new store would hurt the existing "
        "chain least*, not *where it would sell most*.", icon=":material/info:")
elif not headline:
    st.warning("The D63 composite is kept for comparison only. Half its weight comes from demand percentiles that "
               "stretch differences smaller than the model's error onto a full 0–1 scale (D71).", icon=":material/history:")

k1, k2, k3, k4 = st.columns(4)
k1.metric("Grid cells scored", f"{len(data.table('candidate_grid_scores')):,}")
k2.metric("Shortlisted", f"{len(cands)}")
k3.metric(f"Pass the 5% filter at λ={lam}", f"{len(passing)}")
k4.metric("Pass/fail changes with λ", f"{int(r['lambda_sensitive'].sum())}",
          help="Candidates that pass at some λ in {1.5…3.0} and fail at another.")

# ----------------------------------------------------------------------------- table (selectable)
label_of = dict(zip(cands["candidate_id"], cands["display_name"]))
code_of = dict(zip(cands["candidate_id"], cands["code"]))

ui.section("Ranking" if headline else f"Composite ranking (w = {weight})", "The result")
ui.caption("Click a row to highlight that site on the map and open its detail below.")
tbl = passing.copy().reset_index(drop=True)
tbl["rank_shown"] = tbl[rank_col]
cols = ["rank_shown", "display_name", "demand_band", "total_cannibalization_demand", "worst_store",
        "max_store_cannibalization_pct", "predicted_review_count", "rank_range", "lambda_sensitive", "composite_rank_w50"]
if not headline:
    cols = ["rank_shown", "display_name", "composite_score", "demand_percentile", "cannibalization_percentile",
            "total_cannibalization_demand", "worst_store", "max_store_cannibalization_pct", "predicted_review_count",
            "error_band_rank"]
st.dataframe(tbl[cols], hide_index=True, width="stretch", height=min(38 + 35 * len(tbl), 420),
             key="sr_table", on_select="rerun", selection_mode="single-row", column_config={
    "rank_shown": st.column_config.NumberColumn("Rank", format="%d"),
    "display_name": "Candidate",
    "demand_band": st.column_config.NumberColumn("Demand band", format="%d",
                                                 help=f"Whole model-errors (cv_rmse_log = {band_w:.3f}) below the best passing site."),
    "total_cannibalization_demand": st.column_config.NumberColumn("Temple demand taken", format="%.0f",
                                                                  help="MODELED: sum of losses across all 9 stores (Huff)."),
    "worst_store": "Worst-hit store",
    "max_store_cannibalization_pct": st.column_config.NumberColumn("Worst-hit %", format="%.2f%%"),
    "predicted_review_count": st.column_config.NumberColumn("Pred. reviews", format="%.0f",
                                                            help=f"MODELED from a PROXY target; typical error ~{np.exp(band_w):.1f}×."),
    "rank_range": st.column_config.TextColumn("Rank across λ", help="Error-band rank at λ = 1.5, 2.0, 2.5, 3.0."),
    "lambda_sensitive": st.column_config.CheckboxColumn("Pass/fail flips with λ"),
    "composite_rank_w50": st.column_config.NumberColumn("Old composite rank", format="%d"),
    "composite_score": st.column_config.NumberColumn("Composite", format="%.1f"),
    "demand_percentile": st.column_config.NumberColumn("Demand pct.", format="%.2f"),
    "cannibalization_percentile": st.column_config.NumberColumn("Cannib. pct.", format="%.2f"),
    "error_band_rank": st.column_config.NumberColumn("Headline rank", format="%d"),
})
st.download_button("Download this table (CSV)", tbl[cols].to_csv(index=False).encode(), key="sr_dl",
                   file_name=f"candidate_ranking_lambda{lam}{'' if headline else f'_w{weight}'}.csv", mime="text/csv")

# ----------------------------------------------------------------------------- which site is in focus
# Three ways to pick a site: a table row, a click on the map, or the detail selectbox. Whichever
# changed most recently wins; a table pick or selectbox pick also zooms the map to the site.
opts = passing["candidate_id"].tolist() + filtered["candidate_id"].tolist()


def _rows(state_key):
    try:
        return tuple(st.session_state[state_key].selection.rows)
    except (KeyError, AttributeError):
        return ()


def _map_pick():
    try:
        objs = (st.session_state["sr_map"].selection.objects or {}).get("candidates") or []
        return int(objs[0]["candidate_id"]) if objs else None
    except (KeyError, AttributeError, TypeError, ValueError):
        return None


rows = _rows("sr_table")
if rows != st.session_state.get("_sr_last_rows"):
    st.session_state["_sr_last_rows"] = rows
    if rows and rows[0] < len(tbl):
        st.session_state["sr_detail"] = int(tbl.loc[rows[0], "candidate_id"])
        st.session_state["_sr_zoom"] = True
map_pick = _map_pick()
if map_pick is not None and map_pick != st.session_state.get("_sr_last_click"):
    st.session_state["_sr_last_click"] = map_pick
    st.session_state["sr_detail"] = map_pick
    st.session_state["_sr_zoom"] = False
if st.session_state.get("sr_detail") not in opts:
    st.session_state["sr_detail"] = opts[0]
    st.session_state["_sr_zoom"] = False
focus = st.session_state["sr_detail"]

# ----------------------------------------------------------------------------- map
ui.section("Where the sites are", "Map")
m1, m2 = st.columns([4, 1])
show_layers = m1.pills("Map layers", ["Commercial land (OSM)", "Screened grid cells", "Competitors"],
                       selection_mode="multi", default=["Screened grid cells"], key="sr_layers") or []
if m2.button("Show all sites", key="sr_zoom_out", width="stretch"):
    st.session_state["_sr_zoom"] = False


@st.cache_data(show_spinner=False)
def landuse_features():
    lu = data.table("commercial_landuse").copy()
    lu["fill"] = [ui._rgb(ui.LANDUSE, 80)] * len(lu)
    ui.set_tips(lu, [n if isinstance(n, str) and n else "Commercial / retail land" for n in lu["name"]],
                [f"OSM landuse = {t}" for t in lu["landuse_tag"]], [f"{a:,.0f} m²" for a in lu["area_sq_m"]],
                ["OpenStreetMap · REAL"] * len(lu))
    return data.feature_collection(lu, ["fill"])


layers = []
if "Commercial land (OSM)" in show_layers:
    layers.append(ui.polygon_layer(landuse_features(), "landuse", line_hex=ui.LANDUSE, line_px=0.5))
if "Screened grid cells" in show_layers:
    g = data.table("candidate_grid_scores")
    g = g[~g["shortlisted"].astype(bool)].copy()
    ui.set_tips(g, [f"Grid cell {i} · not shortlisted" for i in g["grid_cell_id"]],
                [str(e)[:1].upper() + str(e)[1:] if isinstance(e, str) else "" for e in g["exclusion_reason"]],
                [f"Predicted reviews {p:,.0f}" for p in g["predicted_review_count"]], ["MODELED"] * len(g))
    layers.append(pdk.Layer("ScatterplotLayer", g, id="grid", get_position=["lon", "lat"],
                            get_fill_color=ui._rgb(ui.GRID, 120), get_radius=70, radius_min_pixels=2,
                            radius_max_pixels=5, pickable=True))
if "Competitors" in show_layers:
    layers.append(ui.competitor_layer(data.open_competitors()))
layers.append(ui.store_layer(data.table("stores")))

pts = r.copy()
pts["fill"] = [ui._rgb(ui.CANDIDATE) if p else ui._rgb(ui.FILTERED) for p in pts["passes_filter"]]
# Dots show the rank (same number as the table's Rank column); the selected site's tag adds its code.
# Map text is ASCII only: deck.gl's default font atlas has no "·" or "✕", and loading the full character set
# made labels vanish in testing.
pts["text"] = [f"{int(k)}" if p and pd.notna(k) else "X" for p, k in zip(pts["passes_filter"], pts[rank_col])]
pts["focus_text"] = [(f"#{int(k)}  {code_of.get(c, c)}" if p and pd.notna(k) else f"{code_of.get(c, c)}  filtered")
                     for c, p, k in zip(pts["candidate_id"], pts["passes_filter"], pts[rank_col])]
pts["is_focus"] = pts["candidate_id"] == focus
ui.set_tips(
    pts,
    [(f"#{int(k)} of {len(passing)} · {code_of.get(cid, cid)}" if p and pd.notna(k) else f"Filtered · {code_of.get(cid, cid)}")
     for cid, p, k in zip(pts["candidate_id"], pts["passes_filter"], pts[rank_col])],
    [n.split(" · ", 1)[-1] for n in pts["display_name"]],
    [(f"Takes {t:,.0f} demand · most from {ws} ({mp:.2f}%)" if p else f"{ws} would lose {mp:.2f}% (over the 5% limit)")
     for p, t, ws, mp in zip(pts["passes_filter"], pts["total_cannibalization_demand"], pts["worst_store"],
                             pts["max_store_cannibalization_pct"].fillna(0))],
    [f"Predicted reviews {pr:,.0f} (MODELED, ~{np.exp(band_w):.1f}× typical error)" for pr in pts["predicted_review_count"]],
)
layers.append(pdk.Layer("ScatterplotLayer", pts, id="candidates", get_position=["lon", "lat"], get_fill_color="fill",
                        get_line_color=ui._rgb("#FFFFFF"), stroked=True, line_width_min_pixels=1.5,
                        get_radius=330, radius_min_pixels=9, radius_max_pixels=16, pickable=True))
layers.append(pdk.Layer("TextLayer", pts, id="candidate_labels", get_position=["lon", "lat"], get_text="text",
                        get_size=11, get_color=[255, 255, 255, 255], get_text_anchor="'middle'",
                        get_alignment_baseline="'center'", font_weight=700, pickable=False))
fp = pts[pts["is_focus"]]
if len(fp):
    # selected site: dark halo ring + a larger, inverted label so it can't be missed
    layers.append(pdk.Layer("ScatterplotLayer", fp, id="focus_ring", get_position=["lon", "lat"], filled=False,
                            stroked=True, get_line_color=ui._rgb(ui.INK), line_width_min_pixels=3,
                            get_radius=900, radius_min_pixels=17, radius_max_pixels=30, pickable=False))
    layers.append(pdk.Layer("TextLayer", fp, id="focus_label", get_position=["lon", "lat"], get_text="focus_text",
                            get_size=15, get_color=ui._rgb("#FFFFFF"), get_text_anchor="'start'",
                            get_alignment_baseline="'center'", get_pixel_offset=[22, 0], font_weight=700,
                            background=True, get_background_color=ui._rgb(ui.INK, 235),
                            background_padding=[5, 2, 5, 2], pickable=False))

view = None
if st.session_state.get("_sr_zoom") and len(fp):
    view = ui.view_for(fp["lon"].iloc[0], fp["lat"].iloc[0], 11.5)
st.pydeck_chart(ui.deck(layers, view), height=540, key="sr_map", on_select="rerun", selection_mode="single-object")
ui.legend_html([("dot", ui.CANDIDATE, "Candidate, passes (number = rank)"), ("dot", ui.FILTERED, "Candidate, filtered X (a store loses > 5%)"),
                ("ring", ui.INK, "Selected: " + pts.loc[pts["is_focus"], "focus_text"].iloc[0] if pts["is_focus"].any() else "Selected"), ("dot", ui.STORE, "Temple store")]
               + ([("dot", ui.GRID, "Screened grid cell, not shortlisted")] if "Screened grid cells" in show_layers else [])
               + ([("swatch", ui.LANDUSE, "OSM commercial / retail land")] if "Commercial land (OSM)" in show_layers else []))
ui.caption("Numbers on the dots are ranks, matching the table's Rank column (not candidate codes); hover a dot for its "
           "code. Select a table row or click a dot to highlight a site. Untagged "
           "commercial strips were never screened, so gaps over the basemap mean *not in OSM*, not *scored low* (D61).")

if len(filtered):
    st.markdown(f"**Filtered at λ = {lam}** — each would take more than 5% of one store's demand:")
    st.dataframe(filtered[["display_name", "worst_store", "max_store_cannibalization_pct", "lambda_sensitive"]],
                 hide_index=True, width="stretch", column_config={
                     "display_name": "Candidate", "worst_store": "Store hurt",
                     "max_store_cannibalization_pct": st.column_config.NumberColumn("Loss", format="%.2f%%"),
                     "lambda_sensitive": st.column_config.CheckboxColumn("Passes at another λ")})

# ----------------------------------------------------------------------------- rank across lambda
with st.expander("How stable is each rank across λ?"):
    allr = data.table("candidate_rankings")
    allr = allr[np.isclose(allr["demand_weight"].astype(float), 0.5)]
    piv = allr.pivot(index="candidate_id", columns="lambda_value", values="error_band_rank")
    order_ids = passing["candidate_id"].tolist() + filtered["candidate_id"].tolist()
    piv = piv.reindex(order_ids)
    labels_y = [cands.set_index("candidate_id")["code"].get(c, str(c)) for c in piv.index]
    z = piv.to_numpy(dtype=float)
    fig = go.Figure(go.Heatmap(
        z=z, x=[f"λ={v:g}" for v in piv.columns], y=labels_y, colorscale=[[0, ui.SEQ[-1]], [1, ui.SEQ[0]]],
        text=np.where(np.isnan(z), "✕", np.vectorize(lambda v: f"{v:.0f}")(np.nan_to_num(z))), texttemplate="%{text}",
        textfont=dict(size=10), xgap=2, ygap=2, showscale=False,
        hovertemplate="%{y} at %{x}: rank %{z}<extra></extra>"))
    fig.update_layout(height=max(260, 22 * len(labels_y) + 60), margin=dict(l=10, r=10, t=10, b=10),
                      yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch", key="sr_stability")
    ui.caption("Headline (error-band) rank at each λ; ✕ = filtered at that λ. Far-out sites lead because they overlap "
               "least with existing stores; their own demand in new markets isn't measured (D65).")

# ----------------------------------------------------------------------------- detail
st.divider()
ui.section("What the rank rests on", "Candidate detail")
cid = st.selectbox("Candidate", opts, format_func=lambda c: label_of.get(c, str(c)), key="sr_detail",
                   on_change=lambda: st.session_state.update(_sr_zoom=True),
                   help="Also highlights and zooms to the site on the map above.")
c = cands.set_index("candidate_id").loc[cid]
rr = r.set_index("candidate_id").loc[cid]

d1, d2, d3, d4 = st.columns(4)
d1.metric("Rank" if rr["passes_filter"] else "Status",
          f"#{int(rr[rank_col])}" if rr["passes_filter"] and pd.notna(rr[rank_col]) else "Filtered")
d2.metric("Temple demand taken", f"{rr['total_cannibalization_demand']:,.0f}")
d3.metric("Worst-hit store", f"{rr['worst_store']}", f"-{rr['max_store_cannibalization_pct']:.2f}%", delta_color="normal")
lo, hi = c["predicted_review_count"] / np.exp(band_w), c["predicted_review_count"] * np.exp(band_w)
d4.metric("Predicted reviews", f"{c['predicted_review_count']:,.0f}", help=f"MODELED. ±1 model error spans {lo:,.0f}–{hi:,.0f}.")
ui.caption(f"{ui.tags('MODELED')} {c['display_name']} · ({c['lat']:.4f}, {c['lon']:.4f}) · "
           f"{c['commercial_area_sq_m']:,.0f} m² of mapped commercial land in its cell · no street address "
           f"(not reverse-geocoded). Assumed Huff attractiveness {c['assumed_attractiveness']:.2f} = chain mean rating "
           f"{c['assumed_rating']:.2f} × ln(predicted reviews + 1) (D64).")

left, right = st.columns(2)
with left:
    att = data.table("candidate_demand_attributions")
    att = att[att["candidate_id"] == cid].copy()
    att["label"] = att["feature_name"].map(data.FEATURE_LABELS).fillna(att["feature_name"])
    att = att.reindex(att["attribution_value"].abs().sort_values(ascending=False).index)
    base = float(c["demand_base_value"])
    total = base + att["attribution_value"].sum()
    fig = go.Figure(go.Waterfall(
        orientation="h", measure=["absolute"] + ["relative"] * len(att) + ["total"],
        y=["Average outlet (intercept)"] + att["label"].tolist() + ["Prediction"],
        x=[base] + att["attribution_value"].tolist() + [total],
        increasing=dict(marker=dict(color=ui.DIV_GAIN[2])), decreasing=dict(marker=dict(color=ui.DIV_LOSS[0])),
        totals=dict(marker=dict(color=ui.INK2)), connector=dict(line=dict(color=ui.MUTED_BAR, width=1)),
        hovertemplate="%{y}: %{x:+.3f}<extra></extra>"))
    x0 = min(base, total) - max(0.15, att["attribution_value"].abs().sum() * 1.2)
    x1 = max(base, total) + max(0.15, att["attribution_value"].abs().sum() * 1.2)
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10), showlegend=False,
                      title=dict(text="Why the demand score is what it is (log reviews)", font=dict(size=14)),
                      xaxis=dict(range=[x0, x1], gridcolor="#EDE6DF"), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, width="stretch", key="sr_waterfall")
    gap = abs(total - float(c["predicted_log_review_count"]))
    ui.caption(f"Ridge decomposition: intercept + Σ(coef × standardized feature) = {total:.4f} = predicted "
               f"log(reviews + 1){'' if gap < 1e-6 else f' — MISMATCH {gap:.2g}, check the export'} (D67). Bars are "
               f"small next to the model error of ±{band_w:.2f}: the reason demand can't rank these sites.")
with right:
    cc = data.table("candidate_cannibalization")
    cc = cc[(cc["candidate_id"] == cid) & np.isclose(cc["lambda_value"].astype(float), lam)].copy()
    cc["store"] = cc["affected_store_id"].map(names)
    cc = cc.sort_values("cannibalization_pct")
    fig = go.Figure(go.Bar(
        x=cc["cannibalization_pct"], y=cc["store"], orientation="h",
        marker_color=[ui.FILTERED if v > 5 else ui.SEQ[4] for v in cc["cannibalization_pct"]],
        customdata=cc["cannibalization_demand"],
        hovertemplate="%{y}: loses %{x:.2f}% (%{customdata:,.0f} demand)<extra></extra>"))
    fig.add_vline(x=5, line_dash="dot", line_color=ui.FILTERED,
                  annotation_text="5% filter", annotation_position="top", annotation_font_size=11)
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10), bargap=0.35,
                      title=dict(text=f"Demand each store loses at λ = {lam} (MODELED)", font=dict(size=14)),
                      xaxis=dict(title="% of store's baseline", range=[0, max(6.0, float(cc['cannibalization_pct'].max()) * 1.15)],
                                 gridcolor="#EDE6DF"))
    st.plotly_chart(fig, width="stretch", key="sr_cann")
    ui.caption("From `candidate_cannibalization`: Huff with this candidate added to every origin's denominator, "
               "relative to each store's Phase 4 baseline (D45/D63).")

with st.expander("Feature values behind the score"):
    att2 = data.table("candidate_demand_attributions")
    att2 = att2[att2["candidate_id"] == cid].copy()
    att2["feature"] = att2["feature_name"].map(data.FEATURE_LABELS).fillna(att2["feature_name"])
    st.dataframe(att2[["feature", "feature_value", "attribution_value"]], hide_index=True, width="stretch",
                 column_config={"feature": "Feature",
                                "feature_value": st.column_config.NumberColumn("Value", format="%.1f"),
                                "attribution_value": st.column_config.NumberColumn("Contribution (log)", format="%+.4f")})
    ui.caption("Features are straight-line 1 mi / 3 mi buffers, not isochrones: a candidate has no isochrone, and "
               "the model had to score any point (D55).")

params = data.table("site_ranking_runs")
p = params[params["ranking_run_id"] == (data.manifest() or {}).get("ranking_run_id")]
if len(p):
    with st.expander("Screening parameters (this ranking run)"):
        st.json(json.loads(p.iloc[0]["parameters"]))
