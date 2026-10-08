"""Cannibalization Explorer — Huff pull share, persisted leave-one-out, and the live what-if (MODELED)."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st

from lib import data, ui
from lib.huff import PERSISTED_LAMBDAS, run_scenario

ui.page_header(
    "Model how cafés share customers", ("MODELED", "REAL", "PROXY"),
    "Huff gravity model: each block group's population splits across every outlet in proportion to "
    "attractiveness ÷ drive time^λ. Drive times are REAL (ORS), attractiveness is the PROXY rating × ln(reviews + 1), "
    "and every share and demand figure is MODELED.",
    kicker="Step 4 of 7  ·  The Huff model",
)

stores = data.table("stores")
names = data.store_names()
inp = data.huff_inputs()
bg = data.table("block_groups")
hc = data.table("huff_cannibalization")
guard = data.live_guard()

if all(g["passed"] for g in guard):
    worst = max(g["max_abs_diff"] for g in guard)
    st.success(f"The in-app Huff engine reproduces every persisted Phase 4 and Phase 6 value "
               f"({sum(g['n'] for g in guard):,} checks, largest difference {worst:.1g} demand units).",
               icon=":material/verified:")
else:
    st.error("The in-app Huff engine does **not** reproduce the persisted values for this snapshot; see "
             "Methodology → Reproducibility. Treat the what-if below as unverified.", icon=":material/error:")

st.latex(r"P_{ij} = \frac{A_j / D_{ij}^{\lambda}}{\sum_k A_k / D_{ik}^{\lambda}}, \qquad "
         r"A_j = \text{rating}_j \cdot \ln(\text{reviews}_j + 1)")
ui.caption(f"{len(inp.outlet_id)} outlets ({len(inp.store_rows)} Temple stores + competitors) × "
           f"{len(inp.origins)} origin block groups inside the stores' 15-min isochrones. λ = 2.5 is the headline; "
           f"Phase 4 persisted λ ∈ {{1.5, 2.0, 2.5, 3.0}} (D37). Captured demand = population × pull share, summed.")

tab_persisted, tab_whatif = st.tabs(["Persisted results (Phase 4)", "What-if (live)"])


@st.cache_data(show_spinner=False)
def origin_shapes() -> pd.DataFrame:
    o = set(data.huff_inputs().origins)
    b = data.table("block_groups")
    return b[b["geoid"].isin(o)][["geoid", "county_name", "geojson"]].reset_index(drop=True)


# ============================================================================= persisted
with tab_persisted:
    c1, c2 = st.columns([2, 3])
    store_name = c1.selectbox("Store", stores["name"].tolist(), key="cx_store")
    lam = c2.segmented_control("λ (distance decay)", list(PERSISTED_LAMBDAS), default=2.5, key="cx_lambda") or 2.5
    sid = int(stores.loc[stores["name"] == store_name, "store_id"].iloc[0])

    ps = data.table("huff_pull_share")
    ps = ps[(ps["store_id"] == sid) & np.isclose(ps["lambda_value"].astype(float), lam)]
    shapes = origin_shapes().merge(ps[["origin_geoid", "pull_share", "population_captured"]],
                                   left_on="geoid", right_on="origin_geoid", how="left")
    idx, edges = ui.quantile_classes(shapes["pull_share"])
    shapes["fill"] = ui.seq_fill(idx, max(len(edges) - 1, 1))
    ui.set_tips(
        shapes,
        [f"Block group {g}" for g in shapes["geoid"]],
        [f"{store_name} pull share: {'not reachable' if pd.isna(p) else f'{p:.1%}'}" for p in shapes["pull_share"]],
        ["" if pd.isna(c) else f"≈ {c:,.0f} people captured" for c in shapes["population_captured"]],
        [f"Huff, λ = {lam} · MODELED"] * len(shapes),
    )
    s = stores[stores["store_id"] == sid].iloc[0]
    layers = [ui.polygon_layer(data.feature_collection(shapes, ["fill"]), "pull_share",
                               line_hex="#FFFFFF", line_px=0.3),
              ui.store_layer(stores)]
    st.pydeck_chart(ui.deck(layers, ui.view_for(s["lon"], s["lat"], 10.2)), height=470, key="cx_map")
    ui.legend_html(ui.class_legend(edges, lambda v: f"{v:.1%}") + [("dot", ui.STORE, "Temple store")])
    ui.caption(f"{ui.tags('MODELED')} {store_name}'s share of each origin's population at λ = {lam}, from "
               f"`huff_pull_share`. Only the {len(inp.origins)} Huff origins are shaded.")

    h = hc[np.isclose(hc["lambda_value"].astype(float), lam)].copy()
    h["affected"] = h["affected_store_id"].map(names)
    h["removed"] = h["removed_store_id"].map(names)

    a, b = st.columns(2)
    with a:
        base = h.drop_duplicates("affected_store_id").sort_values("baseline_captured_demand")
        fig = go.Figure(go.Bar(x=base["baseline_captured_demand"], y=base["affected"], orientation="h",
                               marker_color=[ui.STORE if n == store_name else ui.MUTED_BAR for n in base["affected"]],
                               hovertemplate="%{y}: %{x:,.0f}<extra></extra>"))
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), bargap=0.35,
                          title=dict(text=f"Captured demand at λ = {lam} (MODELED)", font=dict(size=14)),
                          xaxis=dict(title="population-weighted demand units", gridcolor="#EDE6DF"))
        st.plotly_chart(fig, width="stretch", key="cx_capture")
    with b:
        order = base["affected"].tolist()[::-1]
        mat = h.pivot(index="affected", columns="removed", values="cannibalization_pct").reindex(index=order, columns=order)
        z = mat.to_numpy(dtype=float)
        fig = go.Figure(go.Heatmap(
            z=z, x=mat.columns, y=mat.index, colorscale=[[0, ui.SEQ[0]], [1, ui.SEQ[-1]]],
            text=np.where(np.isnan(z), "", np.vectorize(lambda v: f"{v:.1f}")(np.nan_to_num(z))),
            texttemplate="%{text}", textfont=dict(size=10), xgap=2, ygap=2,
            hovertemplate="If <b>%{x}</b> closed, %{y} would gain %{z:.2f}% of its demand<extra></extra>",
            colorbar=dict(title="%", thickness=10)))
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10),
                          title=dict(text="Leave-one-out: % gain if the column store closed", font=dict(size=14)),
                          xaxis=dict(title="closed store", tickangle=-35), yaxis=dict(title="store that gains", autorange="reversed"))
        st.plotly_chart(fig, width="stretch", key="cx_heat")
    top = h.sort_values("cannibalization_demand", ascending=False).head(3)
    ui.caption(
        f"{ui.tags('MODELED')} Read a cell as: if the column store did not exist, the row store's captured demand would "
        f"grow by that percent of its current baseline (D45). Largest pairs at λ = {lam}: "
        + "; ".join(f"{r.affected} ← {r.removed} ({r.cannibalization_pct:.1f}%)" for r in top.itertuples()) + "."
    )

# ============================================================================= what-if
with tab_whatif:
    st.markdown(
        "Close stores, open shortlisted candidates, and change λ to any value. The engine recomputes Huff over the "
        "same REAL drive-time matrices Phase 4/6 used. Only places with real ORS drive times can be added, so "
        "custom pins aren't possible (D69: no straight-line fallback)."
    )
    cands = data.candidates()
    complete = set(int(c) for c in inp.cand_id)
    cand_opts = cands[cands["candidate_id"].isin(complete)]
    label_of = dict(zip(cands["candidate_id"], cands["display_name"]))

    w1, w2, w3 = st.columns([1.2, 2, 2])
    lam_w = w1.slider("λ", 1.0, 3.5, 2.5, 0.1, key="wi_lambda",
                      help="Higher λ = steeper distance decay = customers stick closer to home.")
    removed_names = w2.multiselect("Close stores", stores["name"].tolist(), key="wi_removed")
    added_ids = w3.multiselect("Open candidates", cand_opts["candidate_id"].tolist(),
                               format_func=lambda c: label_of.get(c, str(c)), key="wi_added")
    if inp.incomplete_candidates:
        ui.caption("Not addable (incomplete ORS rows, D69): "
                   + ", ".join(label_of.get(c, str(c)) for c in inp.incomplete_candidates))
    removed_ids = [int(stores.loc[stores["name"] == n, "store_id"].iloc[0]) for n in removed_names]

    res = run_scenario(inp, lam_w, removed_store_ids=removed_ids, added_candidate_ids=added_ids)
    st_ = res.stores
    open_mask = ~st_["removed"]
    base_open = st_.loc[open_mask, "baseline"].sum()
    kept = st_.loc[open_mask, "scenario"].sum()
    released = st_.loc[~open_mask, "baseline"].sum()
    cand_total = res.candidates["captured_in_footprint"].sum()
    net = kept + cand_total - st_["baseline"].sum()

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Stores still open", f"{kept:,.0f}",
              f"{kept - base_open:+,.0f} ({(kept / base_open - 1) if base_open else 0:+.2%})",
              help="Their demand in the scenario vs. their own baseline. MODELED.")
    k2.metric("Released by closures", f"{released:,.0f}",
              help="Baseline demand of the closed stores, now redistributed across every remaining outlet, "
                   "competitors included. MODELED.")
    k3.metric("Opened candidates capture", f"{cand_total:,.0f}",
              help="PARTIAL (D65): only the 946 origins around existing stores count, so a candidate's draw from "
                   "new markets is missing. Not the site's total demand.")
    k4.metric("Temple network, net", f"{net:+,.0f}",
              help="Open stores + opened candidates − all 9 stores at baseline, inside the 946-origin footprint. "
                   "PARTIAL whenever a candidate is opened.")
    if added_ids:
        ui.caption(f"{ui.tags('PARTIAL')} {ui.KIND_MEANING['PARTIAL']}")

    show = st_.copy()
    show["status"] = np.where(show["removed"], "closed in scenario", "open")
    show = show.sort_values(["removed", "change_pct"])
    st.dataframe(
        show[["name", "status", "baseline", "scenario", "change", "change_pct"]], hide_index=True, width="stretch",
        column_config={
            "name": "Store", "status": "Status",
            "baseline": st.column_config.NumberColumn("Baseline demand", format="%.0f"),
            "scenario": st.column_config.NumberColumn("Scenario demand", format="%.0f"),
            "change": st.column_config.NumberColumn("Change", format="%+.1f"),
            "change_pct": st.column_config.NumberColumn("Change %", format="%+.2f%%"),
        },
    )
    over = show[~show["removed"] & (show["change_pct"] < -5.0)]
    if len(over):
        st.warning("Above the Phase 6 filter line (any store losing more than 5% of its baseline): "
                   + ", ".join(f"{n} ({p:.2f}%)" for n, p in zip(over["name"], over["change_pct"])),
                   icon=":material/report:")

    o = origin_shapes().merge(res.origins, on="geoid")
    lim = float(np.nanmax(np.abs(o["delta"]))) if len(o) else 0.0
    o["fill"], _ = ui.diverging_fill(o["delta"], lim)
    ui.set_tips(
        o,
        [f"Block group {g}" for g in o["geoid"]],
        [f"Existing stores' share: {b:.1%} → {s_:.1%}" for b, s_ in zip(o["temple_share_baseline"], o["temple_share_scenario"])],
        [f"Change: {d * 100:+.2f} percentage points" for d in o["delta"]],
        [f"What-if, λ = {lam_w:g} · MODELED"] * len(o),
    )
    layers = [ui.polygon_layer(data.feature_collection(o, ["fill"]), "whatif_origins",
                               line_hex="#FFFFFF", line_px=0.3)]
    if added_ids:
        ca = cands[cands["candidate_id"].isin(added_ids)].copy()
        capmap = dict(zip(res.candidates["candidate_id"], res.candidates["captured_in_footprint"]))
        ui.set_tips(ca, [label_of[c] for c in ca["candidate_id"]], ["Candidate · opened in this scenario"] * len(ca),
                    [f"Captures {capmap[c]:,.0f} within the 946-origin footprint" for c in ca["candidate_id"]],
                    ["PARTIAL: new-market demand not counted (D65)"] * len(ca))
        layers.append(pdk.Layer("ScatterplotLayer", ca, id="added", get_position=["lon", "lat"],
                                get_fill_color=ui._rgb(ui.CANDIDATE), get_line_color=ui._rgb("#FFFFFF"),
                                stroked=True, line_width_min_pixels=2, get_radius=260, radius_min_pixels=7,
                                pickable=True))
    layers.append(ui.store_layer(stores, removed=set(removed_ids)))
    st.pydeck_chart(ui.deck(layers), height=500, key="wi_map")
    step = lim / 3 if lim else 0
    ui.legend_html(
        [("swatch", ui.DIV_LOSS[0], f"Temple share falls ≥{2 * step * 100:.2g} pts"),
         ("swatch", ui.DIV_LOSS[2], "falls a little"), ("swatch", ui.DIV_MID, "no change"),
         ("swatch", ui.DIV_GAIN[0], "rises a little"), ("swatch", ui.DIV_GAIN[2], f"rises ≥{2 * step * 100:.2g} pts"),
         ("dot", ui.STORE, "Temple store"), ("ring", ui.STORE, "closed in scenario"),
         ("dot", ui.CANDIDATE, "opened candidate")])
    ui.caption(f"{ui.tags('MODELED')} Change in the share of each origin's population captured by the existing "
               "Temple stores (opened candidates not counted): blue where they gain, red where they lose. Conservation "
               f"checked: {res.allocated_population:,.0f} people allocated = {res.reachable_population:,.0f} reachable.")
