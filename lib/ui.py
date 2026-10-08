"""
dashboard/lib/ui.py — REAL / PROXY / MODELED labeling, colors, pydeck helpers.

The labels are the project's governing rule (outline Sec. 1, D3): every number
on every page says what kind of number it is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from . import data

# ----------------------------------------------------------------------------- deck palette
# Same system as the study deck (reading_notes.pptx / Temple_Coffee_Study_*.pptx):
# espresso ink, cream cards, burnt-orange accent, teal / gold / orange label pills.

INK = "#2B1D14"        # dk1: headings, body text
INK2 = "#5A4636"       # dk2: secondary text
CREAM = "#F3EEE9"      # lt2: cards
PAPER = "#F7F4F0"      # map/page plane
BORDER = "#D9CFC6"
ACCENT = "#C8692B"     # accent1: kicker line, MODELED pill, Temple stores
TEAL = "#2F6B5E"       # accent2: REAL pill, sequential ramp end
BROWN = "#6F4E37"      # accent3: small section labels
GOLD = "#D9A441"       # accent4: PROXY pill, commercial land
PLUM = "#8E2F6B"       # accent5: filtered candidates
SLATE = "#8A8F98"      # accent6: PARTIAL pill, muted text
MUTED_BAR = "#D9CFC6"  # non-highlighted bars

KIND_STYLE = {  # (fill, text)
    "REAL": (TEAL, "#FFFFFF"), "PROXY": (GOLD, INK), "MODELED": (ACCENT, "#FFFFFF"), "PARTIAL": (SLATE, "#FFFFFF"),
}
KIND_SHORT = {
    "REAL": "Directly observed",
    "PROXY": "A visible stand-in for something hidden",
    "MODELED": "Calculated by the study",
    "PARTIAL": "Counted only near existing stores",
}
KIND_MEANING = {
    "REAL": "Census counts, store addresses, café locations, drive times.",
    "PROXY": "Ratings and review counts standing in for popularity (dated snapshot).",
    "MODELED": "Market scores, customer shares, demand predictions, ranks. Defensible, not ground truth.",
    "PARTIAL": "Counts only the 946 neighborhoods around existing stores (D65), so it understates any site's "
               "draw from new markets.",
}


def tag(kind: str) -> str:
    fill, text = KIND_STYLE[kind]
    return f'<span class="tc-tag" style="background:{fill};color:{text};">{kind}</span>'


def tags(*kinds: str) -> str:
    """HTML pills. Use inside ui.caption / ui.md (they allow HTML), not plain st.caption."""
    return " ".join(tag(k) for k in kinds)


def caption(text: str) -> None:
    st.caption(text, unsafe_allow_html=True)


def md(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def _esc(t: str) -> str:
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def page_header(title: str, kinds: tuple[str, ...], lede: str, kicker: str = "") -> None:
    """Deck slide header: orange letter-spaced kicker, serif title, label pills, lede."""
    k = f'<div class="tc-kicker">{_esc(kicker)}</div>' if kicker else ""
    md(f'{k}<h1 class="tc-title">{_esc(title)}</h1>'
       f'<div class="tc-lede">{tags(*kinds)}<span>{lede}</span></div>')
    guard_banner()


def label(text: str) -> None:
    """Small uppercase brown section label (deck: 'HOW THE LIST WAS CLEANED')."""
    md(f'<div class="tc-label">{_esc(text)}</div>')


def section(title: str, kicker: str = "") -> None:
    k = f'<div class="tc-kicker tc-kicker-sm">{_esc(kicker)}</div>' if kicker else ""
    md(f'{k}<h3 class="tc-h3">{_esc(title)}</h3>')


def stat_cards(items: list[tuple[str, str]], cols: int | None = None) -> None:
    """Big serif orange number + gray description, on cream cards (deck stat blocks)."""
    cards = "".join(f'<div class="tc-stat"><div class="tc-stat-num">{_esc(big)}</div>'
                    f'<div class="tc-stat-txt">{text}</div></div>' for big, text in items)
    n = cols or len(items)
    md(f'<div class="tc-stats" style="grid-template-columns:repeat({n},minmax(0,1fr));">{cards}</div>')


def note(text: str, title: str = "TECHNICAL NOTE") -> None:
    md(f'<div class="tc-note"><div class="tc-note-h">{_esc(title)}</div><div>{text}</div></div>')


def callout(text: str, kind: str = "info") -> None:
    """Cream card with a colored left rule; kind in info / warn / ok / bad."""
    color = {"info": TEAL, "warn": GOLD, "ok": TEAL, "bad": PLUM}[kind]
    md(f'<div class="tc-callout" style="border-left-color:{color};">{text}</div>')


def numbered_cards(items: list[tuple[str, str]], cols: int | None = None) -> None:
    """Orange numbered badges with a bold line and gray text (deck '1 / 2 / 3' cards)."""
    cards = "".join(f'<div class="tc-card"><div class="tc-badge">{i}</div><div><div class="tc-card-h">{h}</div>'
                    f'<div class="tc-card-t">{t}</div></div></div>' for i, (h, t) in enumerate(items, 1))
    md(f'<div class="tc-cards" style="grid-template-columns:repeat({cols or len(items)},minmax(0,1fr));">{cards}</div>')


def list_cards(items: list[tuple[str, list[str]]]) -> None:
    """Deck takeaway columns: a serif heading over a short bullet list, one cream card each."""
    cards = "".join(f'<div class="tc-card tc-card-col"><div class="tc-list-h">{_esc(h)}</div><ul class="tc-list">'
                    + "".join(f"<li>{b}</li>" for b in bullets) + "</ul></div>" for h, bullets in items)
    md(f'<div class="tc-cards" style="grid-template-columns:repeat({len(items)},minmax(0,1fr));">{cards}</div>')


def kind_cards(kinds=("REAL", "PROXY", "MODELED")) -> None:
    cards = "".join(f'<div class="tc-card tc-card-col">{tag(k)}<div class="tc-card-h">{KIND_SHORT[k]}</div>'
                    f'<div class="tc-card-t">{KIND_MEANING[k]}</div></div>' for k in kinds)
    md(f'<div class="tc-cards" style="grid-template-columns:repeat({len(kinds)},minmax(0,1fr));">{cards}</div>')


def hero(title: str, subtitle: str, foot: str = "") -> None:
    """Dark title-slide band with the deck's concentric rings and gold pin."""
    rings = "".join(f'<circle cx="160" cy="160" r="{r}" fill="{ACCENT}" fill-opacity="{a}" stroke="{ACCENT}" '
                    f'stroke-width="1.5"/>' for r, a in ((150, 0.12), (106, 0.18), (62, 0.24)))
    svg = (f'<svg class="tc-hero-rings" viewBox="0 0 320 320" aria-hidden="true">{rings}'
           f'<circle cx="160" cy="160" r="9" fill="{GOLD}"/></svg>')
    f = f'<div class="tc-hero-foot">{_esc(foot)}</div>' if foot else ""
    md(f'<div class="tc-hero">{svg}<div class="tc-hero-body"><div class="tc-hero-title">{_esc(title)}</div>'
       f'<div class="tc-hero-sub">{_esc(subtitle)}</div>{f}</div></div>')


CSS = f"""
<style>
:root {{ --tc-ink:{INK}; --tc-ink2:{INK2}; --tc-cream:{CREAM}; --tc-border:{BORDER}; --tc-accent:{ACCENT};
         --tc-brown:{BROWN}; --tc-slate:{SLATE}; }}
.block-container {{ padding-top: 4.2rem; max-width: 1320px; }}
.tc-kicker {{ color: var(--tc-accent); font-weight: 700; font-size: .78rem; letter-spacing: .14em;
              text-transform: uppercase; margin: 0 0 .15rem; }}
.tc-kicker-sm {{ font-size: .7rem; margin-top: 1.4rem; }}
h1.tc-title, h3.tc-h3, [data-testid="stMarkdownContainer"] h1, [data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3 {{ font-family: Cambria, Caladea, Georgia, serif !important; }}
h1.tc-title {{ font-size: 2.25rem; line-height: 1.15; margin: 0 0 .55rem; padding: 0; color: var(--tc-ink); }}
h3.tc-h3 {{ font-size: 1.45rem; margin: .2rem 0 .6rem; padding: 0; color: var(--tc-ink); }}
.tc-lede {{ color: var(--tc-ink2); font-size: 1.02rem; line-height: 1.5; max-width: 980px; margin-bottom: 1.1rem; }}
.tc-lede .tc-tag {{ margin-right: .35rem; vertical-align: 2px; }}
.tc-lede span:last-child {{ margin-left: .2rem; }}
.tc-tag {{ display: inline-block; font-weight: 700; font-size: .68rem; letter-spacing: .08em; line-height: 1;
           padding: .32em .7em; border-radius: .35rem; vertical-align: 1px; white-space: nowrap; }}
.tc-label {{ color: var(--tc-brown); font-weight: 700; font-size: .74rem; letter-spacing: .1em;
             text-transform: uppercase; margin: 1rem 0 .35rem; }}
.tc-stats, .tc-cards {{ display: grid; gap: .9rem; margin: .3rem 0 1rem; }}
.tc-stat {{ background: var(--tc-cream); border-radius: .6rem; padding: .85rem 1rem; display: flex;
            align-items: center; gap: .9rem; }}
.tc-stat-num {{ font-family: Cambria, Caladea, Georgia, serif; font-weight: 700; font-size: 2.1rem;
                color: var(--tc-accent); line-height: 1; white-space: nowrap; }}
.tc-stat-txt {{ color: var(--tc-ink2); font-size: .92rem; line-height: 1.3; }}
.tc-card {{ background: var(--tc-cream); border-radius: .6rem; padding: 1rem 1.1rem; display: flex; gap: .85rem; }}
.tc-card-col {{ flex-direction: column; gap: .45rem; align-items: flex-start; }}
.tc-badge {{ flex: 0 0 auto; width: 2rem; height: 2rem; border-radius: 50%; background: var(--tc-accent);
             color: #fff; font-weight: 700; display: flex; align-items: center; justify-content: center; }}
.tc-card-h {{ font-weight: 700; color: var(--tc-ink); font-size: 1.02rem; line-height: 1.3; }}
.tc-card-t {{ color: var(--tc-ink2); font-size: .92rem; line-height: 1.4; margin-top: .15rem; }}
.tc-list-h {{ font-family: Cambria, Caladea, Georgia, serif; font-weight: 700; font-size: 1.2rem; color: var(--tc-accent); }}
.tc-list {{ margin: 0; padding-left: 1.1rem; color: var(--tc-ink2); font-size: .93rem; line-height: 1.45; }}
.tc-list li {{ margin-bottom: .35rem; }}
.tc-note {{ border: 1px solid var(--tc-border); border-radius: .5rem; padding: .7rem .95rem; color: var(--tc-ink2);
            font-size: .88rem; line-height: 1.45; margin: .6rem 0 1rem; background: #fff; }}
.tc-note-h {{ color: var(--tc-slate); font-weight: 700; font-size: .7rem; letter-spacing: .12em; margin-bottom: .2rem; }}
.tc-callout {{ background: var(--tc-cream); border-left: 4px solid; border-radius: .45rem; padding: .8rem 1rem;
               color: var(--tc-ink); line-height: 1.5; margin: .3rem 0 1rem; }}
/* dark hero = deck title slide */
.tc-hero {{ position: relative; overflow: hidden; background: var(--tc-ink); border-radius: .8rem;
            padding: 2.2rem 2.4rem; margin: 0 0 1.4rem; min-height: 210px; }}
.tc-hero-rings {{ position: absolute; right: -30px; top: 50%; transform: translateY(-50%); width: 330px; height: 330px; }}
.tc-hero-body {{ position: relative; max-width: 62%; }}
.tc-hero-title {{ font-family: Cambria, Caladea, Georgia, serif; font-weight: 700; color: #fff; font-size: 2.3rem;
                  line-height: 1.15; }}
.tc-hero-sub {{ color: var(--tc-cream); font-size: 1.1rem; margin-top: .7rem; line-height: 1.45; }}
.tc-hero-foot {{ color: {GOLD}; font-size: .85rem; margin-top: 1.2rem; }}
/* st.metric -> deck stat card */
[data-testid="stMetric"] {{ background: var(--tc-cream); border-radius: .6rem; padding: .75rem 1rem .8rem; }}
[data-testid="stMetricValue"] {{ font-family: Cambria, Caladea, Georgia, serif; color: var(--tc-accent);
                                 font-weight: 700; }}
[data-testid="stMetricLabel"] p {{ color: var(--tc-ink2); font-weight: 600; }}
/* headings from st.subheader */
[data-testid="stMarkdownContainer"] h2, [data-testid="stMarkdownContainer"] h3 {{ color: var(--tc-ink); }}
[data-testid="stCaptionContainer"] {{ color: var(--tc-ink2); opacity: 1 !important; font-size: .86rem; }}
/* alerts -> cream cards with a colored rule */
[data-testid="stAlertContainer"] {{ background: var(--tc-cream) !important; color: var(--tc-ink) !important;
                                    border-left: 4px solid var(--tc-accent); border-radius: .45rem; }}
[data-testid="stAlertContentSuccess"], [data-testid="stAlertContentInfo"] {{ color: var(--tc-ink); }}
[data-testid="stExpander"] details {{ border-color: var(--tc-border); border-radius: .5rem; }}
[data-testid="stExpander"] summary p {{ font-weight: 600; color: var(--tc-ink); }}
.stTabs [data-baseweb="tab"] p {{ font-weight: 600; }}
/* sidebar */
[data-testid="stSidebar"] .tc-side-brand {{ font-family: Cambria, Caladea, Georgia, serif; font-size: 1.25rem;
                                            font-weight: 700; color: #fff; line-height: 1.2; }}
[data-testid="stSidebar"] .tc-side-sub {{ color: {GOLD}; font-size: .78rem; letter-spacing: .12em;
                                          text-transform: uppercase; margin-top: .25rem; }}
[data-testid="stSidebar"] .tc-side-key {{ font-size: .82rem; line-height: 1.4; color: #E6DFD8; margin: .45rem 0; }}
[data-testid="stSidebar"] .tc-side-key .tc-tag {{ margin-right: .4rem; }}
[data-testid="stSidebar"] .tc-side-meta {{ font-size: .74rem; color: {SLATE}; margin-top: .8rem; line-height: 1.45; }}
</style>
"""


def inject_css() -> None:
    md(CSS)


def guard_banner() -> None:
    """Shown on every page whenever the snapshot's engine check failed."""
    m = data.manifest() or {}
    if not m.get("guard", {}).get("passed", True):
        st.error("This snapshot was exported with **--allow-guard-failure**: the dashboard's Huff engine does not "
                 "reproduce the persisted Phase 4/6 values. Treat every Huff number here as unverified. "
                 "Details on the Methodology page.", icon=":material/warning:")


def sidebar_brand() -> None:
    with st.sidebar:
        md('<div class="tc-side-brand">Temple Coffee Roasters</div>'
           '<div class="tc-side-sub">Where should store ten go?</div>')


def sidebar_footer() -> None:
    m = data.manifest() or {}
    with st.sidebar:
        st.divider()
        md('<div class="tc-label" style="color:#D9A441;margin-top:0;">Every number carries a label</div>'
           + "".join(f'<div class="tc-side-key">{tag(k)}{KIND_SHORT[k]}</div>' for k in ("REAL", "PROXY", "MODELED")))
        if m:
            src = "" if m.get("source") == "supabase" else f" · source: <b>{_esc(m.get('source'))}</b>"
            md(f'<div class="tc-side-meta">Snapshot {_esc(str(m.get("exported_at", "?"))[:10])} · ranking run '
               f'{m.get("ranking_run_id")} · demand run {m.get("demand_run_id_scored")}{src}</div>')


# ----------------------------------------------------------------------------- map / chart color
# Map palette is the deck's: stores orange, candidates blue, filtered plum (validated
# all-pairs for color-vision deficiency), teal sequential ramp, orange drive-time tints.

def _rgb(h: str, a: int = 255) -> list[int]:
    h = h.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [a]


SEQ = ["#E3EFEA", "#C3DDD3", "#9CC7B8", "#72AD9B", "#4C917E", "#2F6B5E", "#1C4A40"]  # 7 classes, light -> dark
DIV_LOSS = ["#8A4318", "#D58E5C", "#F1D9C8"]  # strong -> weak
DIV_GAIN = ["#C3DDD3", "#72AD9B", "#2F6B5E"]  # weak -> strong
DIV_MID = "#E9E3DC"
NO_DATA = _rgb("#DDD8D2", 90)
ISO_LINE = "#8A4318"
ISO_FILL = {5: "#D58E5C", 10: "#E6B796", 15: "#F1D9C8"}

STORE = ACCENT          # Temple stores
CANDIDATE = "#2A78B5"   # passing candidates
FILTERED = PLUM         # filtered by the 5% rule (always with an X and a text label)
COMPETITOR = "#3F3A36"  # rival cafés
LANDUSE = GOLD          # OSM commercial / retail land
GRID = "#6E665F"        # screened grid cells


def quantile_classes(values: pd.Series, k: int = 7) -> tuple[np.ndarray, list[float]]:
    v = pd.to_numeric(values, errors="coerce")
    finite = v[np.isfinite(v)]
    if finite.empty:
        return np.full(len(v), -1), []
    edges = np.unique(np.quantile(finite, np.linspace(0, 1, k + 1)))
    if len(edges) < 2:
        edges = np.array([finite.min(), finite.max() + 1e-9])
    idx = np.clip(np.searchsorted(edges, v, side="right") - 1, 0, len(edges) - 2)
    idx = np.where(np.isfinite(v), idx, -1)
    return idx, edges.tolist()


def seq_fill(idx: np.ndarray, n_classes: int, alpha: int = 170) -> list[list[int]]:
    ramp = SEQ if n_classes >= len(SEQ) else [SEQ[round(i * (len(SEQ) - 1) / max(n_classes - 1, 1))]
                                                        for i in range(n_classes)]
    return [NO_DATA if i < 0 else _rgb(ramp[i], alpha) for i in idx]


def diverging_fill(values: pd.Series, limit: float, alpha: int = 180) -> tuple[list[list[int]], list[tuple[str, str]]]:
    """Symmetric 7-class diverging scale around 0. Returns fills and legend
    (color, label) pairs, strongest loss first."""
    lim = limit if limit and limit > 0 else 1.0
    cuts = [lim * f for f in (1 / 3, 2 / 3)]
    fills = []
    for v in pd.to_numeric(values, errors="coerce"):
        if not np.isfinite(v):
            fills.append(NO_DATA)
        elif abs(v) < 1e-12:
            fills.append(_rgb(DIV_MID, 60))
        elif v < 0:
            k = 0 if -v >= cuts[1] else (1 if -v >= cuts[0] else 2)
            fills.append(_rgb(DIV_LOSS[k], alpha))
        else:
            k = 2 if v >= cuts[1] else (1 if v >= cuts[0] else 0)
            fills.append(_rgb(DIV_GAIN[k], alpha))
    return fills, []


def legend_html(items: list[tuple[str, str, str]]) -> None:
    """items: (kind, hex color, label); kind in {'swatch','dot','ring','line'}."""
    parts = []
    for kind, color, label in items:
        if kind == "dot":
            mark = f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{color};"></span>'
        elif kind == "ring":
            mark = f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;border:2px solid {color};"></span>'
        elif kind == "line":
            mark = f'<span style="display:inline-block;width:14px;height:0;border-top:2px solid {color};"></span>'
        else:
            mark = f'<span style="display:inline-block;width:14px;height:10px;border-radius:2px;background:{color};"></span>'
        parts.append(f'<span style="display:inline-flex;align-items:center;gap:6px;margin-right:14px;'
                     f'white-space:nowrap;">{mark}<span>{label}</span></span>')
    st.markdown(f'<div style="font-size:0.84rem;line-height:1.9;color:{INK2};margin:-.2rem 0 .3rem;">'
                f'{"".join(parts)}</div>', unsafe_allow_html=True)


def class_legend(edges: list[float], fmt, n_classes: int | None = None) -> list[tuple[str, str, str]]:
    n = len(edges) - 1
    ramp = SEQ if n >= len(SEQ) else [SEQ[round(i * (len(SEQ) - 1) / max(n - 1, 1))] for i in range(n)]
    return [("swatch", ramp[i], f"{fmt(edges[i])}–{fmt(edges[i + 1])}") for i in range(n)]


# ----------------------------------------------------------------------------- pydeck

# Streamlit escapes HTML that comes from the data, so all formatting lives in this
# template and every layer supplies plain text in tip_title / tip_1..tip_3 (empty
# strings for unused lines; empty divs take no space).
TIP_COLS = ("tip_title", "tip_1", "tip_2", "tip_3")
TOOLTIP = {
    "html": ('<div style="font-family:Cambria,Caladea,Georgia,serif;font-weight:700;font-size:14px;color:#2B1D14;'
             'margin-bottom:3px;">{tip_title}</div>'
             '<div>{tip_1}</div><div>{tip_2}</div><div style="color:#8A8F98;">{tip_3}</div>'),
    "style": {"backgroundColor": "#FFFFFF", "color": "#5A4636", "fontSize": "13px", "lineHeight": "1.45",
              "padding": "9px 12px", "borderRadius": "8px", "maxWidth": "340px",
              "border": "1px solid #D9CFC6", "borderTop": "3px solid #C8692B",
              "boxShadow": "0 4px 14px rgba(43,29,20,0.16)", "fontFamily": "Calibri, Carlito, sans-serif"},
}


def set_tips(df: pd.DataFrame, title, line1=None, line2=None, line3=None) -> pd.DataFrame:
    """Writes the four plain-text tooltip columns (no HTML: it would be shown as text)."""
    n = len(df)
    for col, vals in zip(TIP_COLS, (title, line1, line2, line3)):
        df[col] = [""] * n if vals is None else ["" if v is None else str(v) for v in vals]
    return df


VIEW_ALL = pdk.ViewState(latitude=38.60, longitude=-121.43, zoom=9.2, pitch=0)


def view_for(lon: float, lat: float, zoom: float = 11.0) -> pdk.ViewState:
    return pdk.ViewState(latitude=float(lat), longitude=float(lon), zoom=zoom, pitch=0)


def deck(layers: list, view: pdk.ViewState | None = None) -> pdk.Deck:
    return pdk.Deck(
        layers=layers, initial_view_state=view or VIEW_ALL, map_provider="carto", map_style="light",
        tooltip=TOOLTIP,
    )


def store_layer(stores: pd.DataFrame, layer_id: str = "stores", removed: set[int] | None = None) -> pdk.Layer:
    s = stores.copy()
    removed = removed or set()
    rn = data.table("attractiveness_snapshot")
    rn = rn[rn["entity_type"] == "store"].set_index("entity_id")
    set_tips(
        s,
        [f"{n} · Temple store" for n in s["name"]],
        ["Closed in this scenario" if int(i) in removed else a for i, a in zip(s["store_id"], s["address"])],
        [f"Rating {rn['rating'].get(i, float('nan')):.1f} · {int(rn['review_count'].get(i, 0)):,} reviews"
         for i in s["store_id"]],
        ["Rating and reviews: PROXY snapshot"] * len(s),
    )
    s["fill"] = [_rgb("#FFFFFF") if int(i) in removed else _rgb(STORE) for i in s["store_id"]]
    s["line"] = [_rgb(STORE) if int(i) in removed else _rgb("#FFFFFF") for i in s["store_id"]]
    return pdk.Layer("ScatterplotLayer", s, id=layer_id, get_position=["lon", "lat"], get_fill_color="fill",
                     get_line_color="line", line_width_min_pixels=2, stroked=True,
                     get_radius=260, radius_min_pixels=6, radius_max_pixels=14, pickable=True)


def competitor_layer(comp: pd.DataFrame) -> pdk.Layer:
    c = comp.copy()
    set_tips(c, [n if isinstance(n, str) and n else "Unnamed cafe" for n in c["name"]],
             [f"Competitor · {b}" if isinstance(b, str) and b else "Competitor" for b in c["brand"]],
             None, ["Location: REAL (OpenStreetMap)"] * len(c))
    return pdk.Layer("ScatterplotLayer", c, id="competitors", get_position=["lon", "lat"],
                     get_fill_color=_rgb(COMPETITOR, 190), get_radius=90, radius_min_pixels=2.5,
                     radius_max_pixels=6, pickable=True)


def polygon_layer(features: list[dict], layer_id: str, filled: bool = True, line_hex: str = "#5A4636",
                  line_px: float = 0.5, pickable: bool = True, fill_alpha_default: int = 0) -> pdk.Layer:
    return pdk.Layer("GeoJsonLayer", features, id=layer_id, filled=filled, stroked=True,
                     get_fill_color="properties.fill" if filled else [0, 0, 0, fill_alpha_default],
                     get_line_color=_rgb(line_hex, 140), line_width_min_pixels=line_px, pickable=pickable)
