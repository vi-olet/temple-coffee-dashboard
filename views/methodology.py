"""Methodology — how every number was made, how good it is, and what it can't tell you."""

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from lib import data, ui

ui.page_header(
    "How every number was made", ("REAL", "PROXY", "MODELED"),
    "The pipeline behind every page, the models' measured accuracy, the reproducibility checks this snapshot "
    "passed, and the limits a site committee should know before acting on a rank.",
    kicker="The method",
)

m = data.manifest() or {}
run = data.primary_demand_run()

ui.section("Every number carries one of three labels", "Three kinds of number")
ui.kind_cards(("REAL", "PROXY", "MODELED", "PARTIAL"))

ui.section("Seven steps from public data to a ranked list", "The pipeline")
ui.numbered_cards([
    ("Gather the evidence", "1,568 Census block groups in 4 counties, 9 geocoded stores, 378 cafés from "
     "OpenStreetMap, 27 drive-time zones. <b>REAL</b> · D5–D10"),
    ("Build the map room", "PostGIS on Supabase; every shape stored twice, in degrees for display and meters for "
     "measurement. Structural · Q3–Q9"),
    ("Draw each store's territory", "5/10/15-minute zones split over neighborhoods by area; a 0–100 market score. "
     "<b>REAL</b> inputs, <b>MODELED</b> score · D24–D27"),
    ("Model how cafés share customers", "Huff pull share for 9 stores × 946 neighborhoods; leave-one-out "
     "cannibalization. <b>MODELED</b> · D41–D48"),
    ("Predict how busy any spot would be", "Ridge vs LightGBM on review count for 118 cafés, tested region by "
     "region. <b>MODELED</b> from a <b>PROXY</b> · D51–D60"),
    ("Search the region, rank the shortlist", "483 commercial grid cells → 30 sites → 5% harm limit → error-band "
     "rank. <b>MODELED</b> · D61–D74"),
    ("Put it where others can test it", "This dashboard: frozen snapshot, live what-if, and a guard that "
     "re-checks 1,404 stored results. D75–D81"),
], cols=4)

ui.section("Each model answers only the question it can", "The two models")
a, b = st.columns(2)
with a:
    st.markdown("**Huff gravity model → cannibalization**")
    st.latex(r"P_{ij} = \frac{A_j / D_{ij}^{\lambda}}{\sum_k A_k / D_{ik}^{\lambda}}")
    st.markdown(
        "- $A_j$ = rating × ln(reviews + 1) from the dated snapshot (PROXY, D41)\n"
        "- $D_{ij}$ = ORS drive time in seconds, floored at 1 s; no route = unreachable (D44)\n"
        "- Origins = the 946 block groups inside the stores' 15-min isochrones\n"
        "- Right for cannibalization, because demand a new site takes from a store can only come from where that "
        "store already draws (D65)\n"
        "- Wrong for a new site's total demand: new-market origins aren't in the set"
    )
with b:
    st.markdown("**Ridge regression → demand potential**")
    st.markdown(
        "- Target: log(review count + 1) for 118 outlets (PROXY for foot traffic, D51/D56)\n"
        "- Features: 1 mi / 3 mi buffer demographics, competitors within 1 mi, nearest competitor and Temple store, "
        "reduced hours (D55). Computable for any point, which is the point\n"
        "- Validation: leave-one-region-out over 6 merged nearest-store regions (D59)\n"
        "- Ridge beat LightGBM on held-out error before and after the CV fix (D60)"
    )

ui.section("The test showed where the model's limit is", "How accurate is the demand model?")
runs = data.table("demand_model_runs")
latest = runs.sort_values("run_id").groupby("model_name").tail(1)
k = st.columns(len(latest) * 2)
for i, (_, rr) in enumerate(latest.sort_values("is_primary", ascending=False).iterrows()):
    nice = {"ridge": "Ridge", "lightgbm": "LightGBM"}.get(rr["model_name"], rr["model_name"])
    k[2 * i].metric(f"{nice}{' (chosen)' if rr['is_primary'] else ''} · log error",
                    f"{rr['cv_rmse_log']:.3f}", help=f"≈ {np.exp(rr['cv_rmse_log']):.1f}× typical multiplicative error")
    k[2 * i + 1].metric("CV MAE (reviews)", f"{rr['cv_mae_count']:,.0f}")

pred = data.table("demand_model_predictions")
pred = pred[pred["run_id"] == run["run_id"]].copy()
pred["actual_log"] = np.log1p(pred["actual_review_count"])
fig = go.Figure()
for et, color, name in (("competitor", "#A8A09A", "Competitor"), ("store", ui.STORE, "Temple store")):
    p = pred[pred["entity_type"] == et]
    fig.add_trace(go.Scatter(
        x=p["actual_log"], y=p["predicted_log_review_count"], mode="markers", name=name,
        marker=dict(color=color, size=8, line=dict(color="#FFFFFF", width=1)),
        customdata=np.stack([p["outlet_name"].fillna(""), p["actual_review_count"], p["predicted_review_count"]], axis=1),
        hovertemplate="<b>%{customdata[0]}</b><br>actual %{customdata[1]:,} · held-out prediction "
                      "%{customdata[2]:,.0f}<extra></extra>"))
lo = float(min(pred["actual_log"].min(), pred["predicted_log_review_count"].min())) - 0.2
hi = float(max(pred["actual_log"].max(), pred["predicted_log_review_count"].max())) + 0.2
band = float(run["cv_rmse_log"])
fig.add_trace(go.Scatter(x=[lo, hi, hi, lo], y=[lo + band, hi + band, hi - band, lo - band], fill="toself",
                         fillcolor="rgba(47,107,94,0.12)", line=dict(width=0), hoverinfo="skip",
                         name="± 1 model error"))
fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", line=dict(color=ui.MUTED_BAR, width=1, dash="dot"),
                         hoverinfo="skip", name="perfect"))
fig.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10),
                  title=dict(text=f"Held-out (out-of-sample) predictions, {run['model_name']} run {int(run['run_id'])}",
                             font=dict(size=14)),
                  xaxis=dict(title="actual log(reviews + 1)", range=[lo, hi], gridcolor="#EDE6DF"),
                  yaxis=dict(title="predicted", range=[lo, hi], gridcolor="#EDE6DF"),
                  legend=dict(orientation="h", y=-0.2))
st.plotly_chart(fig, width="stretch", key="me_scatter")
ui.caption(
    f"{ui.tags('MODELED')} Each dot was predicted by a model that never saw its region. The shaded band is ±1 CV RMSE "
    f"(~{np.exp(band):.1f}× either way). The worst real misses (18–21× over) are low-review competitors in "
    "high-traffic areas, which geography alone can't explain (D60). That is why Phase 6 counts demand only in whole "
    "bands of this error (D71)."
)

ui.section("Screen, shortlist, filter, rank", "How the shortlist is ranked")
st.markdown(
    f"1. **Screen**: every 1 km grid cell with ≥ 2,000 m² of OSM commercial/retail land inside the study area, "
    "scored by the Ridge model at a point on that land (D61).\n"
    "2. **Shortlist**: greedy by predicted demand, ≥ 2 km apart and ≥ 800 m from any store, top 30.\n"
    "3. **Drive times**: real ORS matrix from each candidate to the 946 origins (D62).\n"
    "4. **Filter**: drop a candidate if any one store would lose > 5% of its Huff demand (D63).\n"
    f"5. **Rank**: demand band = ⌊(best predicted log − predicted log) ÷ {band:.3f}⌋, then least total Temple demand "
    "taken (D71). The older 50/50 percentile composite (D63) stays available for comparison."
)

ui.section("A guard at the door", "Reproducibility")
st.markdown("Before a snapshot is accepted, the dashboard's Huff engine re-derives Phase 4 and Phase 6 outputs from "
            "the exported inputs (D78). The app repeats the check on load.")
live = data.live_guard()
exp = (m.get("guard") or {}).get("checks", [])
rows = []
for g in live:
    e = next((x for x in exp if x["check"] == g["check"]), None)
    rows.append({"Check": g["check"], "Values compared": g["n"], "Failures": g["n_failed"],
                 "Largest difference": g["max_abs_diff"], "At export": "pass" if e and e["passed"] else ("fail" if e else "—"),
                 "In app now": "pass" if g["passed"] else "fail", "Notes": g["detail"]})
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
             column_config={"Largest difference": st.column_config.NumberColumn(format="%.2e")})
ui.caption("Phase 5/6's own guards also passed on the real run: the Ridge refit matched Phase 5 on all 118 rows "
           "(D66/D73) and every store baseline matched Phase 4 at all four λ (D68/D73).")

ui.section("What the study shows, and what stays open", "The takeaway")
ui.list_cards([
    ("It shows", [
        "Three sites (C23, C14, C04) lead at every distance-decay setting tested",
        "Existing stores overlap by only 0.3% to 2.9%",
        "The demand model's weakness was measured and designed around",
        "Hazel Ave is the most exposed store: every rejected site would hurt it",
    ]),
    ("Still open", [
        "Demand in new markets far from today's stores (D65)",
        "Cafés and commercial land missing from OpenStreetMap",
        "λ is tested across a range, not calibrated",
        "Only residents are counted, not daytime workers",
        "Candidates have no street address yet",
    ]),
    ("With real company data", [
        "Sales would replace review counts",
        "Loyalty or mobile data would calibrate λ",
        "Past store openings would test the forecasts",
    ]),
])

ui.section("What this app is reading", "This snapshot")
files = m.get("files", {})
ft = pd.DataFrame([{"Table": k, "Rows": v["rows"], "Character": v["data_character"], "Size (KB)": v["bytes"] / 1024}
                   for k, v in files.items()])
c1, c2, c3 = st.columns(3)
c1.metric("Exported (UTC)", str(m.get("exported_at", "?"))[:10], help=str(m.get("exported_at")))
c2.metric("Ranking run", str(m.get("ranking_run_id")))
c3.metric("Demand model run", str(m.get("demand_run_id_scored")))
if m.get("source") != "supabase":
    st.warning(f"Source: **{m.get('source')}**. These are not the project's real numbers.", icon=":material/science:")
st.dataframe(ft, hide_index=True, width="stretch",
             column_config={"Size (KB)": st.column_config.NumberColumn(format="%.0f")})
with st.expander("manifest.json"):
    st.code(json.dumps({k: v for k, v in m.items() if k != "files"}, indent=2, default=str), language="json")
