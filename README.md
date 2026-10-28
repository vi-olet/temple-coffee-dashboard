# Where should Temple Coffee open its tenth store?

**[Open the live dashboard →]([YOUR-APP-LINK](https://temple-coffee-dashboard-9eatayew7d9vqztbbb9ggn.streamlit.app/))**

A GIS site-selection and cannibalization study for Temple Coffee Roasters, a nine-store specialty coffee chain in the Sacramento region, built entirely on public data.

> Portfolio project. Not affiliated with or endorsed by Temple Coffee Roasters. No company sales data was used.

## The question

A good new site has to pass two tests:

1. **Are there enough customers nearby?** People, income and competition around a site decide how busy a café can be.
2. **Will it take customers from our own stores?** A site that only moves sales between existing stores adds little.

## What the study found

- **Three sites lead at every setting tested:** C23 in far south Sacramento, and C14 and C04 on the Citrus Heights side.
- **The existing stores barely overlap.** Closing any one store would shift only 0.3% to 2.9% of another's demand.
- **Hazel Ave is the most exposed store.** All three rejected sites were rejected because they would take more than 5% of its demand.
- **The demand model couldn't tell the shortlisted sites apart**, so the ranking orders them by least harm to existing stores. It answers "where would a new store hurt the chain least," not "where would it sell most."

## How it works

| Step | What was done | Data |
|---|---|---|
| 1 | Gathered 1,568 Census block groups in 4 counties, 9 store locations, 357 rival cafés and 27 drive-time zones | Census ACS, OpenStreetMap, OpenRouteService |
| 2 | Stored everything in a spatial database | PostGIS on Supabase |
| 3 | Built 5, 10 and 15-minute trade areas and a market score for each store | Area-weighted Census overlay |
| 4 | Modeled how 946 neighborhoods split their visits across 118 cafés | Huff gravity model |
| 5 | Predicted how busy any location would be, tested region by region | Ridge regression vs. LightGBM |
| 6 | Screened 483 commercial grid cells, shortlisted 30, ranked the 27 that passed a 5% cannibalization limit | Error-band ranking |
| 7 | Published this interactive dashboard with a live what-if tool | Streamlit, pydeck |

Every number in the dashboard is labeled **REAL** (observed), **PROXY** (a stand-in, such as review counts for popularity) or **MODELED** (calculated by the study).

## Dashboard pages

- **Market Overview:** demographics, stores and competitors
- **Trade Areas:** drive-time territories for each store
- **Cannibalization:** how stores share customers, plus a what-if tool to close stores or open candidate sites
- **Site Ranking:** the shortlist, the ranking and what each site's rank rests on
- **Methodology:** model accuracy, reproducibility checks and limitations

## Limitations

- Review counts stand in for sales, so demand is a proxy
- Demand in new markets far from today's stores was not measured
- OpenStreetMap may miss some cafés and commercial land
- Only residents are counted, not daytime workers

## Run it locally

The app reads a Parquet snapshot in `data/` exported from the project's
PostGIS database; it holds no database credentials.

Source and full methodology: see the GitHub repository's README.
