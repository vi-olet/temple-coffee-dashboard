"""
dashboard/lib/data.py — snapshot loading, shared lookups, cached Huff inputs.

The app reads only dashboard/data/*.parquet + manifest.json, written by
src/dashboard/export_snapshot.py (D75). TEMPLE_DASHBOARD_DATA_DIR overrides
the folder (tests point it at a synthetic snapshot).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from .huff import HEADLINE_LAMBDA, PERSISTED_LAMBDAS, HuffInputs, build_inputs, verify_against_persisted

HEADLINE_WEIGHT = 0.5  # error_band_rank is identical on every weight row; this picks one row per candidate

FEATURE_LABELS = {
    "population_1mi": "Population within 1 mi",
    "income_weighted_1mi": "Median income, 1 mi",
    "age_weighted_1mi": "Median age, 1 mi",
    "population_3mi": "Population within 3 mi",
    "income_weighted_3mi": "Median income, 3 mi",
    "age_weighted_3mi": "Median age, 3 mi",
    "competitor_count_1mi": "Competitors within 1 mi",
    "nearest_competitor_distance_m": "Nearest competitor (m)",
    "nearest_store_distance_m": "Nearest Temple store (m)",
    "reduced_hours_flag": "Reduced hours (D1)",
}


def data_dir() -> Path:
    env = os.environ.get("TEMPLE_DASHBOARD_DATA_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[1] / "data"


@st.cache_data(show_spinner=False)
def manifest() -> dict | None:
    p = data_dir() / "manifest.json"
    return json.loads(p.read_text()) if p.exists() else None


@st.cache_data(show_spinner=False)
def table(name: str) -> pd.DataFrame:
    return pd.read_parquet(data_dir() / f"{name}.parquet")


def require_snapshot() -> dict:
    m = manifest()
    if m is None:
        st.error(
            "No data snapshot found. From the repo root run "
            "`python -m src.dashboard.export_snapshot`, which writes `dashboard/data/`, then reload.",
            icon=":material/database_off:",
        )
        st.stop()
    return m


# --------------------------------------------------------------------------- lookups

@st.cache_data(show_spinner=False)
def store_names() -> dict[int, str]:
    s = table("stores")
    return dict(zip(s["store_id"].astype(int), s["name"]))


@st.cache_data(show_spinner=False)
def outlet_names() -> dict[tuple[str, int], str]:
    names = {("store", int(k)): v for k, v in store_names().items()}
    c = table("competitors")
    names.update({("competitor", int(i)): (n or f"Competitor {i}") for i, n in zip(c["competitor_id"], c["name"])})
    return names


@st.cache_data(show_spinner=False)
def candidates() -> pd.DataFrame:
    """candidate_sites plus a display name that states distance, not proximity
    (Phase 6 note: `label` names the nearest store even 16 km away)."""
    c = table("candidate_sites").copy()
    code = c["label"].str.extract(r"^(C\d+)", expand=False).fillna("C" + c["shortlist_rank"].astype(str).str.zfill(2))
    c["code"] = code
    c["display_name"] = [
        f"{k} · {d / 1000:.1f} km from {s}" for k, d, s in
        zip(code, c["nearest_store_distance_m"], c["nearest_store_name"])
    ]
    return c


@st.cache_data(show_spinner=False)
def primary_demand_run() -> pd.Series:
    runs = table("demand_model_runs")
    m = manifest() or {}
    scored = m.get("demand_run_id_scored")
    if scored is not None and (runs["run_id"] == scored).any():
        return runs[runs["run_id"] == scored].iloc[0]
    return runs[runs["is_primary"]].sort_values("run_id").iloc[-1]


@st.cache_data(show_spinner=False)
def open_competitors() -> pd.DataFrame:
    """Competitors as every model sees them: closed (D39) and Temple's own OSM
    duplicates (D34) removed."""
    c = table("competitors")
    return c[~c["verified_closed"].astype(bool) & ~c["is_temple_brand_duplicate"].astype(bool)]


# --------------------------------------------------------------------------- rankings

@st.cache_data(show_spinner=False)
def rankings_at(lmbda: float, weight: float = HEADLINE_WEIGHT) -> pd.DataFrame:
    r = table("candidate_rankings")
    r = r[np.isclose(r["lambda_value"].astype(float), lmbda) & np.isclose(r["demand_weight"].astype(float), weight)]
    c = candidates()[["candidate_id", "code", "display_name", "predicted_review_count",
                      "predicted_log_review_count", "lon", "lat", "nearest_store_name", "nearest_store_distance_m"]]
    out = r.merge(c, on="candidate_id", how="left")
    out["worst_store"] = out["max_store_cannibalization_store_id"].map(
        lambda s: store_names().get(int(s)) if pd.notna(s) else None)
    return out


@st.cache_data(show_spinner=False)
def rank_stability() -> pd.DataFrame:
    """Per candidate: error-band rank range across the 4 lambdas, and whether
    pass/fail flips across lambda (Phase 6 D73/D74)."""
    r = table("candidate_rankings")
    r = r[np.isclose(r["demand_weight"].astype(float), HEADLINE_WEIGHT)]
    g = r.groupby("candidate_id")
    out = pd.DataFrame({
        "rank_min": g["error_band_rank"].min(),
        "rank_max": g["error_band_rank"].max(),
        "lambda_sensitive": g["passes_filter"].nunique() > 1,
    }).reset_index()
    out["rank_range"] = [
        (f"{int(a)}–{int(b)}" if a != b else f"{int(a)}") if pd.notna(a) else "—"
        for a, b in zip(out["rank_min"], out["rank_max"])
    ]
    return out


# --------------------------------------------------------------------------- Huff engine

@st.cache_resource(show_spinner="Loading drive-time matrices ...")
def huff_inputs() -> HuffInputs:
    return build_inputs(
        table("attractiveness_snapshot"), table("distance_matrix"), table("huff_origins"),
        table("candidate_sites"), table("candidate_distance_matrix"), outlet_names=outlet_names(),
    )


@st.cache_data(show_spinner="Checking the Huff engine against Phase 4/6 ...")
def live_guard() -> list[dict]:
    """D78, re-run in the app: the engine must reproduce what was persisted.
    The export ran the same check; this catches a snapshot edited by hand or
    an engine change shipped without a re-export."""
    return verify_against_persisted(huff_inputs(), table("huff_cannibalization"), table("candidate_cannibalization"))


# --------------------------------------------------------------------------- geometry

def feature_collection(df: pd.DataFrame, props: list[str], geom_col: str = "geojson") -> list[dict]:
    """Features as a list. `fill` and the tip_* tooltip fields are copied to the
    top level too, so pydeck's tooltip template and accessors find them either way."""
    props = list(props) + [c for c in ("tip_title", "tip_1", "tip_2", "tip_3") if c in df.columns and c not in props]
    feats = []
    for rec in df[[geom_col] + props].to_dict("records"):
        p = {k: _jsonable(rec[k]) for k in props}
        f = {"type": "Feature", "geometry": json.loads(rec[geom_col]), "properties": p}
        for k in ("fill", "line", "tip_title", "tip_1", "tip_2", "tip_3"):
            if k in p:
                f[k] = p[k]
        feats.append(f)
    return feats


def _jsonable(v):
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, np.ndarray):
        return v.tolist()
    if isinstance(v, (list, tuple)):
        return list(v)
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return v


__all__ = [
    "HEADLINE_LAMBDA", "PERSISTED_LAMBDAS", "HEADLINE_WEIGHT", "FEATURE_LABELS", "manifest", "table",
    "require_snapshot", "store_names", "outlet_names", "candidates", "primary_demand_run", "open_competitors",
    "rankings_at", "rank_stability", "huff_inputs", "live_guard", "feature_collection",
]
