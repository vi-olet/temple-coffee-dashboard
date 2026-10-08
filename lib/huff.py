"""
dashboard/lib/huff.py — Phase 7 (D77)

The in-app Huff "what-if" engine. Pure numpy, no database, no Streamlit, so
the same file is imported by the dashboard, by the snapshot export's guard
(src/dashboard/export_snapshot.py) and by the tests.

It reproduces, rather than approximates, the two Huff implementations the
pipeline already persisted:

  * Phase 4 huff_model.run(): Aj = rating * ln(review_count + 1) over every
    attractiveness_snapshot outlet with both values present (D41/D44);
    Dij = ORS drive time, floored at 1 s; a NULL drive time is unreachable
    (utility 0); NULL/negative origin population counts as 0 demand; an
    origin whose denominator is 0 is skipped. Leave-one-out = drop one store's
    utility from every denominator (D42).
  * Phase 6 huff_with_candidate(): add one candidate with
    A = candidate_sites.assumed_attractiveness (D64) and its own ORS row set;
    a candidate missing any origin row is "incomplete" and can't be added
    (D69: never a straight-line fallback).

What the dashboard adds is only generality: any lambda (not just the four
swept values), any set of stores removed and any set of candidates added at
once. verify_against_persisted() proves that, restricted to what Phase 4/6
actually computed, this engine returns the persisted numbers (D78).

Every output here is MODELED.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_DRIVE_TIME_SECONDS = 1.0          # huff_model.MIN_DRIVE_TIME_SECONDS
PERSISTED_LAMBDAS = (1.5, 2.0, 2.5, 3.0)  # huff_model.LAMBDAS (D37)
HEADLINE_LAMBDA = 2.5
GUARD_REL_TOL = 1e-6                  # same tolerance as Phase 6's D68 baseline guard
GUARD_ABS_TOL = 1e-6


@dataclass(frozen=True)
class HuffInputs:
    outlet_type: np.ndarray          # 'store' | 'competitor'
    outlet_id: np.ndarray            # int
    outlet_name: np.ndarray          # str
    attractiveness: np.ndarray       # Aj
    origins: np.ndarray              # geoid, sorted
    population: np.ndarray           # NULL/negative -> 0 (D44)
    drive_time: np.ndarray           # [outlet, origin] seconds, NaN = unreachable, floored at 1 s
    store_rows: np.ndarray           # row indices of outlet_type == 'store'
    cand_id: np.ndarray              # candidate_id of COMPLETE candidates only
    cand_attractiveness: np.ndarray  # D64 assumed_attractiveness
    cand_drive_time: np.ndarray      # [candidate, origin], NaN = unreachable
    incomplete_candidates: dict      # candidate_id -> origins with a row (D69)

    @property
    def store_ids(self) -> np.ndarray:
        return self.outlet_id[self.store_rows]


def build_inputs(
    attractiveness: pd.DataFrame,
    distance_matrix: pd.DataFrame,
    origins: pd.DataFrame,
    candidates: pd.DataFrame | None = None,
    candidate_distance_matrix: pd.DataFrame | None = None,
    outlet_names: dict | None = None,
) -> HuffInputs:
    """attractiveness: entity_type, entity_id, rating, review_count
    distance_matrix: outlet_type, outlet_id, origin_geoid, drive_time_seconds
    origins: geoid, population_total (huff_model.FETCH_ORIGIN_POPULATION_SQL)
    candidates: candidate_id, assumed_attractiveness
    candidate_distance_matrix: candidate_id, origin_geoid, drive_time_seconds"""
    a = attractiveness.dropna(subset=["rating", "review_count"]).sort_values(["entity_type", "entity_id"])
    outlet_type = a["entity_type"].to_numpy(dtype=object)
    outlet_id = a["entity_id"].to_numpy(dtype=np.int64)
    A = a["rating"].astype(float).to_numpy() * np.log(a["review_count"].astype(float).to_numpy() + 1.0)
    names = outlet_names or {}
    outlet_name = np.array([names.get((t, int(i)), f"{t} {i}") for t, i in zip(outlet_type, outlet_id)], dtype=object)

    o = origins.drop_duplicates("geoid").sort_values("geoid")
    geoids = o["geoid"].to_numpy(dtype=object)
    pop = pd.to_numeric(o["population_total"], errors="coerce").to_numpy(dtype=float)
    pop = np.where(np.isfinite(pop) & (pop >= 0), pop, 0.0)

    origin_idx = pd.Index(geoids)
    outlet_idx = pd.MultiIndex.from_arrays([outlet_type, outlet_id])

    T = np.full((len(outlet_id), len(geoids)), np.nan)
    dm = distance_matrix
    rows = outlet_idx.get_indexer(pd.MultiIndex.from_arrays([dm["outlet_type"].to_numpy(dtype=object),
                                                             dm["outlet_id"].to_numpy(dtype=np.int64)]))
    cols = origin_idx.get_indexer(dm["origin_geoid"].to_numpy(dtype=object))
    keep = (rows >= 0) & (cols >= 0)   # outlets excluded for missing rating / origins outside the set
    t = pd.to_numeric(dm["drive_time_seconds"], errors="coerce").to_numpy(dtype=float)[keep]
    T[rows[keep], cols[keep]] = np.where(np.isnan(t), np.nan, np.maximum(t, MIN_DRIVE_TIME_SECONDS))

    store_rows = np.flatnonzero(outlet_type == "store")

    cand_id, cand_A, cand_T, incomplete = [], [], [], {}
    if candidates is not None and len(candidates):
        cdm = candidate_distance_matrix if candidate_distance_matrix is not None else pd.DataFrame(
            columns=["candidate_id", "origin_geoid", "drive_time_seconds"])
        by_cand = {cid: g for cid, g in cdm.groupby("candidate_id")}
        for _, c in candidates.sort_values("candidate_id").iterrows():
            cid = int(c["candidate_id"])
            g = by_cand.get(cid)
            row = np.full(len(geoids), np.nan)
            seen = 0
            if g is not None:
                j = origin_idx.get_indexer(g["origin_geoid"].to_numpy(dtype=object))
                ok = j >= 0
                seen = len(np.unique(j[ok]))
                tt = pd.to_numeric(g["drive_time_seconds"], errors="coerce").to_numpy(dtype=float)[ok]
                row[j[ok]] = np.where(np.isnan(tt), np.nan, np.maximum(tt, MIN_DRIVE_TIME_SECONDS))
            if seen != len(geoids) or pd.isna(c["assumed_attractiveness"]):
                incomplete[cid] = seen
                continue
            cand_id.append(cid)
            cand_A.append(float(c["assumed_attractiveness"]))
            cand_T.append(row)

    return HuffInputs(
        outlet_type=outlet_type, outlet_id=outlet_id, outlet_name=outlet_name, attractiveness=A,
        origins=geoids, population=pop, drive_time=T, store_rows=store_rows,
        cand_id=np.array(cand_id, dtype=np.int64), cand_attractiveness=np.array(cand_A, dtype=float),
        cand_drive_time=np.array(cand_T, dtype=float).reshape(len(cand_id), len(geoids)),
        incomplete_candidates=incomplete,
    )


def _utility(A: np.ndarray, T: np.ndarray, lmbda: float) -> np.ndarray:
    reachable = ~np.isnan(T)
    return np.where(reachable, A[:, None] / np.power(np.where(reachable, T, 1.0), lmbda), 0.0)


def _captured(pop: np.ndarray, U: np.ndarray, denom: np.ndarray) -> np.ndarray:
    ok = denom > 0
    safe = np.where(ok, denom, 1.0)
    return np.where(ok, pop * U / safe, 0.0).sum(axis=-1)


@dataclass
class ScenarioResult:
    lmbda: float
    stores: pd.DataFrame       # store_id, name, removed, baseline, scenario, change, change_pct
    candidates: pd.DataFrame   # candidate_id, captured_in_footprint (PARTIAL, D65)
    origins: pd.DataFrame      # geoid, population, temple_share_baseline, temple_share_scenario, delta
    reachable_population: float
    allocated_population: float


def run_scenario(inp: HuffInputs, lmbda: float, removed_store_ids=(), added_candidate_ids=()) -> ScenarioResult:
    """Baseline = every existing outlet. Scenario = baseline minus removed
    Temple stores plus added candidates. Raises if population isn't conserved
    (Phase 6 D68 conservation guard) or an unknown/incomplete candidate is
    requested."""
    removed = set(int(s) for s in removed_store_ids)
    unknown = removed - set(int(s) for s in inp.store_ids)
    if unknown:
        raise KeyError(f"Unknown store_id(s): {sorted(unknown)}")
    added = [int(c) for c in added_candidate_ids]
    cand_pos = {int(c): k for k, c in enumerate(inp.cand_id)}
    bad = [c for c in added if c not in cand_pos]
    if bad:
        raise KeyError(f"Candidate(s) {bad} have no complete ORS drive times and can't be added (D69).")

    U = _utility(inp.attractiveness, inp.drive_time, lmbda)
    denom = U.sum(axis=0)
    base_cap = _captured(inp.population, U[inp.store_rows], denom)

    U2 = U.copy()
    removed_rows = [r for r in inp.store_rows if int(inp.outlet_id[r]) in removed]
    U2[removed_rows] = 0.0
    if added:
        k = [cand_pos[c] for c in added]
        Uc = _utility(inp.cand_attractiveness[k], inp.cand_drive_time[k], lmbda)
    else:
        Uc = np.zeros((0, len(inp.origins)))
    denom2 = U2.sum(axis=0) + Uc.sum(axis=0)
    scen_cap = _captured(inp.population, U2[inp.store_rows], denom2)
    cand_cap = _captured(inp.population, Uc, denom2) if len(Uc) else np.zeros(0)

    ok2 = denom2 > 0
    allocated = float(_captured(inp.population, U2, denom2).sum() + cand_cap.sum())
    reachable = float(np.where(ok2, inp.population, 0.0).sum())
    if not math.isclose(allocated, reachable, rel_tol=1e-9, abs_tol=1e-6):
        raise AssertionError(f"Huff conservation violated: allocated {allocated} vs reachable {reachable}.")

    store_ids = inp.store_ids
    change = scen_cap - base_cap
    pct = np.where(base_cap > 0, 100.0 * change / np.where(base_cap > 0, base_cap, 1.0), np.nan)
    stores = pd.DataFrame({
        "store_id": store_ids.astype(int),
        "name": inp.outlet_name[inp.store_rows],
        "removed": [int(s) in removed for s in store_ids],
        "baseline": base_cap, "scenario": scen_cap, "change": change, "change_pct": pct,
    })

    ok = denom > 0
    share_base = np.where(ok, U[inp.store_rows].sum(axis=0) / np.where(ok, denom, 1.0), 0.0)
    share_scen = np.where(ok2, U2[inp.store_rows].sum(axis=0) / np.where(ok2, denom2, 1.0), 0.0)
    origins = pd.DataFrame({
        "geoid": inp.origins, "population": inp.population,
        "temple_share_baseline": share_base, "temple_share_scenario": share_scen,
        "delta": share_scen - share_base,
    })
    return ScenarioResult(
        lmbda=lmbda, stores=stores,
        candidates=pd.DataFrame({"candidate_id": added, "captured_in_footprint": cand_cap}),
        origins=origins, reachable_population=reachable, allocated_population=allocated,
    )


def pull_shares(inp: HuffInputs, lmbda: float, store_id: int) -> pd.DataFrame:
    """Pij for one store at every origin, the same quantity huff_pull_share
    stores at the four swept lambdas."""
    U = _utility(inp.attractiveness, inp.drive_time, lmbda)
    denom = U.sum(axis=0)
    row = int(np.flatnonzero((inp.outlet_type == "store") & (inp.outlet_id == int(store_id)))[0])
    ok = denom > 0
    share = np.where(ok, U[row] / np.where(ok, denom, 1.0), np.nan)
    return pd.DataFrame({"geoid": inp.origins, "pull_share": share, "population_captured": inp.population * share})


# -----------------------------------------------------------------------------
# D78: the engine must reproduce what Phase 4/6 persisted, or it says so
# -----------------------------------------------------------------------------

def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=GUARD_REL_TOL, abs_tol=GUARD_ABS_TOL)


def verify_against_persisted(inp: HuffInputs, huff_cannibalization: pd.DataFrame,
                             candidate_cannibalization: pd.DataFrame | None = None) -> list[dict]:
    """Three checks, each a dict(check, passed, n, n_failed, max_abs_diff, detail):
      1. store baselines vs huff_cannibalization.baseline_captured_demand
      2. leave-one-out deltas vs huff_cannibalization.cannibalization_demand
      3. single-candidate losses vs candidate_cannibalization.cannibalization_demand
    """
    results = []
    hc = huff_cannibalization.copy()
    hc["lambda_value"] = hc["lambda_value"].astype(float)
    lambdas = sorted(hc["lambda_value"].unique())

    base_fail, base_n, base_max = [], 0, 0.0
    loo_fail, loo_n, loo_max = [], 0, 0.0
    for lm in lambdas:
        base = run_scenario(inp, lm).stores.set_index("store_id")["baseline"]
        ref = hc[hc["lambda_value"] == lm].drop_duplicates("affected_store_id").set_index("affected_store_id")
        for sid, r in ref.iterrows():
            base_n += 1
            got = float(base.get(int(sid), np.nan))
            diff = abs(got - float(r["baseline_captured_demand"]))
            base_max = max(base_max, diff if np.isfinite(diff) else np.inf)
            if not _close(got, float(r["baseline_captured_demand"])):
                base_fail.append((int(sid), lm))
        for removed_id, grp in hc[hc["lambda_value"] == lm].groupby("removed_store_id"):
            gain = run_scenario(inp, lm, removed_store_ids=[int(removed_id)]).stores.set_index("store_id")["change"]
            for _, r in grp.iterrows():
                loo_n += 1
                got = max(float(gain.get(int(r["affected_store_id"]), np.nan)), 0.0)  # huff_model clamps at 0
                diff = abs(got - float(r["cannibalization_demand"]))
                loo_max = max(loo_max, diff if np.isfinite(diff) else np.inf)
                if not _close(got, float(r["cannibalization_demand"])):
                    loo_fail.append((int(r["affected_store_id"]), int(removed_id), lm))
    results.append(dict(check="Phase 4 store baselines (huff_cannibalization)", passed=not base_fail and base_n > 0,
                        n=base_n, n_failed=len(base_fail), max_abs_diff=base_max,
                        detail=f"first failures: {base_fail[:5]}" if base_fail else ""))
    results.append(dict(check="Phase 4 leave-one-out cannibalization", passed=not loo_fail and loo_n > 0,
                        n=loo_n, n_failed=len(loo_fail), max_abs_diff=loo_max,
                        detail=f"first failures: {loo_fail[:5]}" if loo_fail else ""))

    if candidate_cannibalization is not None and len(candidate_cannibalization):
        cc = candidate_cannibalization.copy()
        cc["lambda_value"] = cc["lambda_value"].astype(float)
        c_fail, c_n, c_max, skipped = [], 0, 0.0, set()
        complete = set(int(c) for c in inp.cand_id)
        for (cid, lm), grp in cc.groupby(["candidate_id", "lambda_value"]):
            if int(cid) not in complete:
                skipped.add(int(cid))
                continue
            loss = -run_scenario(inp, lm, added_candidate_ids=[int(cid)]).stores.set_index("store_id")["change"]
            for _, r in grp.iterrows():
                c_n += 1
                got = max(float(loss.get(int(r["affected_store_id"]), np.nan)), 0.0)
                diff = abs(got - float(r["cannibalization_demand"]))
                c_max = max(c_max, diff if np.isfinite(diff) else np.inf)
                if not _close(got, float(r["cannibalization_demand"])):
                    c_fail.append((int(cid), int(r["affected_store_id"]), lm))
        detail = []
        if c_fail:
            detail.append(f"first failures: {c_fail[:5]}")
        if skipped:
            detail.append(f"persisted rows for incomplete candidate(s) {sorted(skipped)} not checked")
        results.append(dict(check="Phase 6 candidate cannibalization", passed=not c_fail and c_n > 0,
                            n=c_n, n_failed=len(c_fail), max_abs_diff=c_max, detail="; ".join(detail)))
    return results
