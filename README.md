---
title: Temple Coffee Site Selection
emoji: ☕
colorFrom: blue
colorTo: gray
sdk: docker
app_port: 8501
pinned: false
short_description: GIS site selection and Huff cannibalization for a coffee chain
---

# Temple Coffee Roasters — Site Selection & Cannibalization

A five-page Streamlit dashboard over a full site-selection pipeline for a real
9-store Sacramento coffee chain: Census ACS demographics, OSM competitors,
OpenRouteService drive times, a Huff gravity model for cannibalization, a
Ridge demand model, and a ranked shortlist of 30 candidate sites.

Every number is labeled **REAL** (observed), **PROXY** (a dated rating/review
snapshot standing in for foot traffic) or **MODELED** (computed by the project).

| Page | What it shows |
|---|---|
| Market Overview | Block-group demographics, stores, competitors |
| Trade Area Explorer | 5/10/15-min drive-time trade areas per store |
| Cannibalization Explorer | Huff pull share, leave-one-out, and a live what-if (close stores, open candidates, any λ) |
| Site Ranking | The shortlist, the 5% cannibalization filter, error-band ranking, per-site explanation |
| Methodology | Model accuracy, reproducibility checks, limitations |

The app reads a Parquet snapshot in `data/` exported from the project's
PostGIS database; it holds no database credentials.

Source and full methodology: see the GitHub repository's README.
