"""
dashboard/app.py — Temple Coffee Roasters site-selection dashboard (Phase 7)

One multipage Streamlit app (D3): Market Overview, Trade Area Explorer,
Cannibalization Explorer, Site Ranking, Methodology. Reads only the exported
snapshot in dashboard/data/ (D75). Run locally:

    python -m src.dashboard.export_snapshot      # from the repo root, once per pipeline re-run
    cd dashboard && streamlit run app.py         # from dashboard/ so .streamlit/config.toml applies
"""

import sys
from pathlib import Path

# Make `lib` importable however the app is launched (streamlit run, AppTest on
# Windows, Docker). `streamlit run` usually adds this folder itself; not every
# launcher does.
APP_DIR = str(Path(__file__).resolve().parent)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import streamlit as st  # noqa: E402

from lib import data, ui  # noqa: E402

st.set_page_config(page_title="Temple Coffee · Site Selection", page_icon=":material/coffee:", layout="wide")

ui.inject_css()
data.require_snapshot()

pages = [
    st.Page("views/market_overview.py", title="1 · Market Overview", icon=":material/map:", default=True,
            url_path="market_overview"),
    st.Page("views/trade_area.py", title="2 · Trade Areas", icon=":material/radar:", url_path="trade_area"),
    st.Page("views/cannibalization.py", title="3 · Cannibalization", icon=":material/compare_arrows:",
            url_path="cannibalization"),
    st.Page("views/site_ranking.py", title="4 · Site Ranking", icon=":material/format_list_numbered:",
            url_path="site_ranking"),
    st.Page("views/methodology.py", title="5 · Methodology", icon=":material/menu_book:", url_path="methodology"),
]
ui.sidebar_brand()
nav = st.navigation(pages)
ui.sidebar_footer()
nav.run()
