"""
dashboard.py - Executive live dashboard (Plotly Dash) on MongoDB Atlas data.
Sections: Overview (with trend arrows), Momentum (revenue + cancellation trend with normal band),
Watchlist, Drivers, Gaps (map, rates, revenue lost by segment), Actions.
Filters: city, category. Colour coding vs targets. Refreshes every 20s.
"""

import os
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, dash_table, dcc, html
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(override=True)
orders = MongoClient(os.environ["MONGO_URI"])["ecommerce"]["orders"]

BG, CARD, BORDER = "#0b1120", "#131c31", "#22304d"
TEXT, MUTED = "#e5e9f2", "#8a97b1"
ACCENT, CYAN = "#6366f1", "#22d3ee"
GREEN, AMBER, RED = "#34d399", "#fbbf24", "#f87171"
TINT = {GREEN: "rgba(52,211,153,.14)", AMBER: "rgba(251,191,36,.14)",
        RED: "rgba(248,113,113,.14)", MUTED: "rgba(138,151,177,.14)"}
FONT = "Inter, Segoe UI, sans-serif"
TARGET, WARN, HIGH_VALUE = 15, 25, 8000
COLS = ["order_id", "ingested_at", "total_amount", "order_status", "product_name",
        "category", "payment_method", "city"]
CITIES = ["Delhi", "Mumbai", "Bangalore", "Chennai", "Hyderabad", "Pune", "Kolkata", "Jaipur"]
CATEGORIES = ["Beauty", "Electronics", "Fashion", "Grocery", "Home & Kitchen", "Sports"]
COORDS = {"Delhi": (28.61, 77.21), "Mumbai": (19.08, 72.88), "Bangalore": (12.97, 77.59),
          "Chennai": (13.08, 80.27), "Hyderabad": (17.39, 78.49), "Pune": (18.52, 73.86),
          "Kolkata": (22.57, 88.36), "Jaipur": (26.91, 75.79)}
# label side per city, chosen so neighbouring cities do not overlap
LABEL_POS = {"Delhi": "top center", "Jaipur": "bottom left", "Mumbai": "middle left",
             "Pune": "bottom left", "Hyderabad": "top right", "Bangalore": "bottom left",
             "Chennai": "middle right", "Kolkata": "top center"}
CARD_H = 300
STACK_H = CARD_H * 2 + 38 + 16   # map height = two stacked chart cards
ROLL = 5                          # rolling window (minutes) for the cancellation trend

CSS = """
body{margin:0;background:#0b1120;font-family:Inter,'Segoe UI',sans-serif;color:#e5e9f2}
.wrap{max-width:1400px;margin:0 auto;padding:28px 32px 56px}
.card{background:#131c31;border:1px solid #22304d;border-radius:16px;padding:18px 20px}
.grid{display:grid;gap:16px}
.g5{grid-template-columns:repeat(5,1fr)}
.g21{grid-template-columns:2fr 1fr}
.g2{grid-template-columns:1fr 1fr}
.g3{grid-template-columns:repeat(3,1fr)}
.sec{margin:38px 0 2px;font-size:12px;letter-spacing:.16em;text-transform:uppercase;color:#818cf8;font-weight:600}
.sech{margin:0 0 14px;font-size:21px;font-weight:600}
.lbl{font-size:12px;color:#8a97b1;text-transform:uppercase;letter-spacing:.07em;font-weight:500}
.val{font-size:32px;font-weight:700;margin:8px 0 10px}
.chip{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;padding:3px 10px;border-radius:999px;margin:0 6px 6px 0}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.live{display:flex;align-items:center;gap:9px;font-size:13px;color:#8a97b1;margin-top:6px}
.live i{width:9px;height:9px;border-radius:50%;background:#34d399;animation:pulse 2s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.55)}70%{box-shadow:0 0 0 9px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
@media(max-width:1000px){.g5,.g21,.g2,.g3{grid-template-columns:1fr}}
"""
INDEX = """<!DOCTYPE html>
<html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}<style>__CSS__</style></head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

app = Dash(__name__, external_stylesheets=[
    "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"])
app.title = "Business Pulse"
app.index_string = INDEX.replace("__CSS__", CSS)


def rag(rate):
    return GREEN if rate <= TARGET else AMBER if rate <= WARN else RED


def chip(text, color=MUTED):
    return html.Span([html.Span(className="dot", style={"background": color}), text],
                     className="chip", style={"background": TINT[color], "color": color})


def delta_chip(cur, prev, good_up=True):
    """Trend chip: % change of cur vs prev (last 10 min vs the 10 min before)."""
    if prev is None or prev <= 0:
        return chip("no prior 10 min")
    pct = (cur - prev) / prev * 100
    if abs(pct) < 0.5:
        return chip("▬ flat vs prev 10 min")
    color = GREEN if (pct > 0) == good_up else RED
    return chip(f"{'▲' if pct > 0 else '▼'} {abs(pct):.0f}% vs prev 10 min", color)


def delta_pts_chip(cur, prev):
    """Trend chip for cancellation rate: change in percentage points (lower is better)."""
    if cur is None or prev is None:
        return chip("no prior 10 min")
    d = cur - prev
    if abs(d) < 0.1:
        return chip("▬ flat vs prev 10 min")
    return chip(f"{'▲' if d > 0 else '▼'} {abs(d):.1f} pts vs prev 10 min",
                RED if d > 0 else GREEN)


def kpi(title, cid):
    return html.Div([html.Div(title, className="lbl"), html.Div(id=cid, className="val"),
                     html.Div(id=f"{cid}s")], className="card")


def section(tag, title):
    return html.Div([html.Div(tag, className="sec"), html.H2(title, className="sech")])


def gcard(gid, h=CARD_H):
    return html.Div(dcc.Graph(id=gid, config={"displayModeBar": False},
                              style={"height": f"{h}px"}), className="card")


def table(tid, columns, conditions):
    return dash_table.DataTable(
        id=tid, columns=columns, page_size=8, sort_action="native", style_as_list_view=True,
        style_table={"overflowX": "auto"},
        style_header={"backgroundColor": "transparent", "color": MUTED, "fontWeight": "600",
                      "fontSize": "11px", "textTransform": "uppercase", "letterSpacing": ".08em",
                      "border": "none", "borderBottom": f"1px solid {BORDER}"},
        style_cell={"backgroundColor": "transparent", "color": TEXT, "border": "none",
                    "borderBottom": f"1px solid {BORDER}", "padding": "11px 8px",
                    "textAlign": "left", "fontFamily": FONT, "fontSize": "14px"},
        style_data_conditional=conditions)


watch_cols = [{"name": "Time (IST)", "id": "time"}, {"name": "Order", "id": "order_id"},
              {"name": "City", "id": "city"}, {"name": "Product", "id": "product_name"},
              {"name": "Amount (₹)", "id": "total_amount", "type": "numeric",
               "format": {"specifier": ",.0f"}},
              {"name": "Status", "id": "order_status"}, {"name": "Flag", "id": "flag"}]
watch_cond = [
    {"if": {"filter_query": '{flag} contains "CANCELLED"', "column_id": ["order_status", "flag"]},
     "backgroundColor": "rgba(248,113,113,.16)", "color": RED, "fontWeight": "600"},
    {"if": {"filter_query": '{flag} = "HIGH VALUE"', "column_id": "flag"},
     "backgroundColor": "rgba(251,191,36,.16)", "color": AMBER, "fontWeight": "600"}]

dd = {"width": "190px", "color": "#111827"}
app.layout = html.Div(className="wrap", children=[
    html.Div(style={"display": "flex", "justifyContent": "space-between",
                    "alignItems": "flex-end", "flexWrap": "wrap", "gap": "16px"}, children=[
        html.Div([html.H1("Business Pulse", style={"margin": 0, "fontSize": "32px",
                                                   "fontWeight": 700}),
                  html.Div(id="stamp", className="live")]),
        html.Div(style={"display": "flex", "gap": "12px"}, children=[
            dcc.Dropdown(CITIES, id="f-city", placeholder="All cities", style=dd),
            dcc.Dropdown(CATEGORIES, id="f-cat", placeholder="All categories", style=dd)])]),

    section("Overview", "How are we doing today?"),
    html.Div(className="grid g5", children=[
        kpi("Net revenue", "k1"), kpi("Orders", "k2"), kpi("Avg order value", "k3"),
        kpi("Cancellation rate", "k4"), kpi("Revenue lost", "k5")]),

    section("Momentum", "Is it healthy right now?"),
    html.Div([gcard("line"), gcard("gauge")], className="grid g21"),
    html.Div(style={"marginTop": "16px"}, children=[gcard("ctrend")]),

    section("Watchlist", "Which orders need attention right now?"),
    html.Div(className="card", children=[
        html.Div(f"Latest cancelled orders and orders above ₹{HIGH_VALUE:,}",
                 style={"color": MUTED, "fontSize": "13px", "marginBottom": "8px"}),
        table("tbl-watch", watch_cols, watch_cond)]),

    section("Drivers", "What is making the money?"),
    html.Div([gcard("cat"), gcard("prod")], className="grid g2"),

    section("Gaps", "Where are we losing orders and money?"),
    html.Div(className="grid g2", children=[
        gcard("city", STACK_H),
        html.Div(className="grid", children=[gcard("pay"), gcard("prodc")])]),
    html.Div(style={"marginTop": "16px"}, className="grid g3",
             children=[gcard("lpay"), gcard("lcity"), gcard("lprod")]),

    section("Actions", "What should leadership do?"),
    html.Div(id="actions", className="grid g2"),
    dcc.Interval(id="tick", interval=20000),
])


def style(fig, title, h=CARD_H):
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15, color=TEXT)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, color=MUTED, size=12), margin=dict(l=8, r=8, t=48, b=8),
        height=h, showlegend=False,
        hoverlabel=dict(bgcolor=CARD, font_color=TEXT, bordercolor=BORDER))
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=BORDER, ticks="", automargin=True)
    fig.update_yaxes(gridcolor=BORDER, zeroline=False, showline=False, ticks="", automargin=True)
    return fig


def blank(title, msg, h=CARD_H):
    fig = go.Figure()
    fig.add_annotation(text=msg, showarrow=False, font=dict(size=14, color=MUTED))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style(fig, title, h)


def cancel_rate(df, col, min_n=10):
    g = df.groupby(col).agg(n=("order_status", "size"),
                            c=("order_status", lambda s: (s == "Cancelled").sum()))
    g = g[g.n >= min_n]
    g["rate"] = g.c / g.n * 100
    return g.sort_values("rate", ascending=False)


def rate_bar(g, title):
    colors = [RED if r > WARN else AMBER if r > TARGET else GREEN for r in g.rate]
    fig = go.Figure(go.Bar(x=g.index, y=g.rate.round(1), marker_color=colors,
                           text=g.rate.round(1), texttemplate="%{text}%",
                           textposition="outside", cliponaxis=False,
                           customdata=g.n, hovertemplate="%{x}: %{y}% of %{customdata} orders"
                                                         "<extra></extra>"))
    fig.add_hline(y=TARGET, line_dash="dot", line_color=AMBER, annotation_text=f"target {TARGET}%",
                  annotation_position="top left", annotation_font_color=AMBER)
    style(fig, title)
    fig.update_yaxes(range=[0, max(30, (g.rate.max() if len(g) else 0) * 1.25)])
    return fig


def lost_bar(lost_df, col, title, top=6):
    """Revenue lost (Rs of cancelled orders) by segment: shows where the money is."""
    g = lost_df.groupby(col).total_amount.sum().sort_values(ascending=False).head(top)
    if g.empty:
        return blank(title, "No cancellations yet")
    fig = go.Figure(go.Bar(
        x=g.values, y=g.index, orientation="h", marker_color=RED, text=g.values,
        texttemplate="₹%{x:.3s}", textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
    style(fig, title)
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, showticklabels=False, range=[0, g.max() * 1.35])
    return fig


def city_map(g, selected):
    """Bubble map of India: size = orders, colour = cancellation rate vs targets."""
    g = g[g.index.isin(COORDS)]
    if g.empty:
        return blank("Orders and cancellations by city", "Collecting data...", STACK_H)
    sizes = 10 + 26 * (g.n / g.n.max()) ** 0.5
    fig = go.Figure(go.Scattergeo(
        lat=[COORDS[c][0] for c in g.index], lon=[COORDS[c][1] for c in g.index],
        mode="markers+text", text=[f"{c} {r:.0f}%" for c, r in zip(g.index, g.rate)],
        textposition=[LABEL_POS[c] for c in g.index],
        textfont=dict(color=TEXT, size=12, family=FONT),
        marker=dict(size=sizes, color=[rag(r) for r in g.rate], opacity=0.85,
                    line=dict(width=[3 if c == selected else 1 for c in g.index],
                              color=["#ffffff" if c == selected else BORDER for c in g.index])),
        customdata=list(zip(g.index, g.n, g.rate.round(1))),
        hovertemplate="%{customdata[0]}<br>%{customdata[1]} orders<br>"
                      "%{customdata[2]}% cancelled<extra></extra>"))
    style(fig, "Orders (bubble size) and cancellation rate (colour) by city", STACK_H)
    fig.update_geos(
        projection_type="mercator", lonaxis_range=[67, 99], lataxis_range=[6, 37],
        showland=True, landcolor="#1a2540", showcountries=True, countrycolor="#3a4a6d",
        showcoastlines=True, coastlinecolor="#3a4a6d", showocean=False, showlakes=False,
        showframe=False, bgcolor="rgba(0,0,0,0)", resolution=50)
    return fig


def flag(x):
    c, h = x.order_status == "Cancelled", x.total_amount > HIGH_VALUE
    return "CANCELLED + HIGH VALUE" if c and h else "CANCELLED" if c else "HIGH VALUE"


OUTS = ([Output(i, "children") for i in
         ["k1", "k2", "k3", "k4", "k5", "k1s", "k2s", "k3s", "k4s", "k5s", "stamp", "actions"]] +
        [Output(i, "figure") for i in ["line", "gauge", "cat", "prod", "pay", "city", "prodc",
                                       "ctrend", "lpay", "lcity", "lprod"]] +
        [Output("tbl-watch", "data")])


@app.callback(OUTS, Input("tick", "n_intervals"), Input("f-city", "value"),
              Input("f-cat", "value"))
def refresh(_, f_city, f_cat):
    now = pd.Timestamp.now(tz="UTC")
    day_start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    df = pd.DataFrame(list(orders.find({"ingested_at": {"$gte": day_start}},
                                       {c: 1 for c in COLS} | {"_id": 0})), columns=COLS)
    if f_cat:
        df = df[df.category == f_cat]
    df_map = df                      # map keeps all cities and highlights the selected one
    if f_city:
        df = df[df.city == f_city]
    scope = " · ".join([f_city or "All cities", f_cat or "All categories"])
    stamp = [html.I(), f"Live · Kafka → MongoDB Atlas · {scope} · updated {datetime.now():%H:%M:%S}"]

    if df.empty:
        e = blank("No data", "No orders for this selection yet")
        return (("-",) * 5 + ("",) * 5 + (stamp, "Start producer_live.py and consumer.py, "
                                                 "or clear the filters.") + (e,) * 11 + ([],))

    df = df.assign(t=pd.to_datetime(df.ingested_at).dt.tz_localize("UTC"))
    ok = df[df.order_status != "Cancelled"]
    lost_df = df[df.order_status == "Cancelled"]
    revenue, lost = ok.total_amount.sum(), lost_df.total_amount.sum()
    rate = len(lost_df) / len(df) * 100
    aov = ok.total_amount.mean() if len(ok) else 0
    color = rag(rate)
    status = "On target" if rate <= TARGET else "Above target" if rate <= WARN else "Critical"

    # Trend arrows: last 10 min vs the 10 min before
    w10, w20 = now - pd.Timedelta(minutes=10), now - pd.Timedelta(minutes=20)
    cur = df[df.t >= w10]
    prev = df[(df.t >= w20) & (df.t < w10)]
    rev_cur = cur[cur.order_status != "Cancelled"].total_amount.sum()
    rev_prev = prev[prev.order_status != "Cancelled"].total_amount.sum()
    cr_cur = (cur.order_status == "Cancelled").mean() * 100 if len(cur) else None
    cr_prev = (prev.order_status == "Cancelled").mean() * 100 if len(prev) else None

    # Momentum: revenue per minute (full minutes only, so no misleading partial-minute dip)
    line = go.Figure()
    has_line = False
    end = now.floor("min")
    start = max(end - pd.Timedelta(minutes=10), df.t.min().ceil("min"))
    if len(ok) and start < end:
        idx = pd.date_range(start, end - pd.Timedelta(minutes=1), freq="1min")
        pm = ok.set_index("t").total_amount.resample("1min").sum().reindex(idx, fill_value=0)
        line.add_trace(go.Scatter(
            x=pm.index.tz_convert("Asia/Kolkata"), y=pm.values, mode="lines",
            line=dict(color=ACCENT, width=3, shape="spline"), fill="tozeroy",
            fillcolor="rgba(99,102,241,.15)",
            hovertemplate="%{x|%H:%M}<br>₹%{y:,.0f}<extra></extra>"))
        has_line = True
    style(line, "Revenue per minute · last 10 full minutes")
    line.update_yaxes(tickformat="~s")
    if not has_line:
        line = blank("Revenue per minute · last 10 full minutes", "Collecting data...")

    # Momentum: 5-minute rolling cancellation rate with a normal-range band.
    # Band = 95% statistical range around the day average for that window's sample size.
    # A point above the band is a real spike, not random noise.
    ttl = f"Cancellation rate · {ROLL}-min rolling vs normal range"
    trend = blank(ttl, "Collecting data...")
    if start < end:
        idx = pd.date_range(start, end - pd.Timedelta(minutes=1), freq="1min")
        idx_full = pd.date_range(start - pd.Timedelta(minutes=ROLL - 1),
                                 end - pd.Timedelta(minutes=1), freq="1min")
        d = df.assign(m=df.t.dt.floor("min"), c=(df.order_status == "Cancelled"))
        g = d.groupby("m").agg(n=("c", "size"), c=("c", "sum")).reindex(idx_full, fill_value=0)
        rn = g.n.rolling(ROLL, min_periods=1).sum().loc[idx]
        rc = g.c.rolling(ROLL, min_periods=1).sum().loc[idx]
        rn = rn.where(rn > 0)
        rr = rc / rn * 100
        p = rate / 100
        half = 1.96 * ((p * (1 - p)) / rn) ** 0.5 * 100
        upper = (rate + half).clip(upper=100)
        lower = (rate - half).clip(lower=0)
        x = idx.tz_convert("Asia/Kolkata")
        spike = rr > upper
        trend = go.Figure()
        trend.add_trace(go.Scatter(x=x, y=upper.values, mode="lines", line=dict(width=0),
                                   hoverinfo="skip"))
        trend.add_trace(go.Scatter(x=x, y=lower.values, mode="lines", line=dict(width=0),
                                   fill="tonexty", fillcolor="rgba(138,151,177,.18)",
                                   hoverinfo="skip"))
        trend.add_trace(go.Scatter(
            x=x, y=rr.values, mode="lines+markers", connectgaps=True,
            line=dict(color=CYAN, width=3),
            marker=dict(size=8, color=[RED if s else CYAN for s in spike]),
            customdata=list(zip(rn.fillna(0).astype(int), lower.round(1), upper.round(1))),
            hovertemplate="%{x|%H:%M}<br>%{y:.1f}% cancelled (last " + str(ROLL) +
                          " min, %{customdata[0]} orders)<br>normal range "
                          "%{customdata[1]}% to %{customdata[2]}%<extra></extra>"))
        style(trend, ttl)
        trend.add_hline(y=TARGET, line_dash="dot", line_color=AMBER,
                        annotation_text=f"target {TARGET}%", annotation_position="top left",
                        annotation_font_color=AMBER)
        trend.add_annotation(xref="paper", yref="paper", x=1, y=1.14, showarrow=False,
                             xanchor="right", font=dict(size=12, color=MUTED),
                             text=f"shaded = normal range around day average ({rate:.1f}%) · "
                                  "red dot = above normal")
        top = max(30, (upper.max() if upper.notna().any() else 0) * 1.1,
                  (rr.max() if rr.notna().any() else 0) * 1.1)
        trend.update_yaxes(range=[0, top], ticksuffix="%")

    gauge = go.Figure(go.Indicator(
        mode="gauge+number", value=round(rate, 1),
        number={"suffix": "%", "font": {"size": 44, "color": TEXT}},
        gauge={"axis": {"range": [0, 40], "tickcolor": BORDER, "tickfont": {"color": MUTED}},
               "bar": {"color": color, "thickness": 0.28}, "bgcolor": "rgba(0,0,0,0)",
               "borderwidth": 0,
               "steps": [{"range": [0, TARGET], "color": "rgba(52,211,153,.18)"},
                         {"range": [TARGET, WARN], "color": "rgba(251,191,36,.18)"},
                         {"range": [WARN, 40], "color": "rgba(248,113,113,.18)"}]}))
    style(gauge, f"Cancellation rate · target under {TARGET}%")

    # Drivers
    cat = ok.groupby("category").total_amount.sum().sort_values(ascending=False)
    cat_fig = go.Figure(go.Bar(
        x=cat.index, y=cat.values, hovertemplate="%{x}: ₹%{y:,.0f}<extra></extra>",
        marker_color=[ACCENT] + ["rgba(99,102,241,.45)"] * max(len(cat) - 1, 0)))
    style(cat_fig, "Revenue by category")
    cat_fig.update_yaxes(tickformat="~s")
    prod = ok.groupby("product_name").total_amount.sum().sort_values(ascending=False).head(5)
    prod_fig = go.Figure(go.Bar(
        x=prod.values, y=prod.index, orientation="h", marker_color=CYAN,
        hovertemplate="%{y}: ₹%{x:,.0f}<extra></extra>"))
    style(prod_fig, "Top 5 products by revenue")
    prod_fig.update_yaxes(autorange="reversed", showgrid=False)
    prod_fig.update_xaxes(showgrid=True, gridcolor=BORDER, tickformat="~s")

    # Gaps: rates, map, and revenue lost by segment
    pay = cancel_rate(df, "payment_method")
    city = cancel_rate(df, "city")
    prc = cancel_rate(df, "product_name")
    pay_fig = rate_bar(pay, "Cancellation rate by payment method")
    prc_fig = rate_bar(prc, "Cancellation rate by product")
    map_fig = city_map(cancel_rate(df_map, "city", min_n=1), f_city)
    lost_map = df_map[df_map.order_status == "Cancelled"]
    lpay_fig = lost_bar(lost_df, "payment_method", "Revenue lost by payment method (₹)")
    lcity_fig = lost_bar(lost_map, "city", "Revenue lost by city (₹)")
    lprod_fig = lost_bar(lost_df, "product_name", "Revenue lost by product (₹)")

    # Watchlist
    wl = df[(df.order_status == "Cancelled") | (df.total_amount > HIGH_VALUE)]
    wl = wl.sort_values("ingested_at", ascending=False).head(10).copy()
    watch_rows = []
    if len(wl):
        wl["time"] = wl.t.dt.tz_convert("Asia/Kolkata").dt.strftime("%H:%M:%S")
        wl["flag"] = wl.apply(flag, axis=1)
        watch_rows = wl[["time", "order_id", "city", "product_name", "total_amount",
                         "order_status", "flag"]].to_dict("records")

    # Actions
    acts = []
    if len(pay):
        acts.append(("Payment gap", f"{pay.index[0]} has the highest cancellation rate "
                     f"({pay.rate.iloc[0]:.0f}%). Review checkout and fraud rules for this method.",
                     rag(pay.rate.iloc[0])))
    if len(city):
        acts.append(("Regional gap", f"{city.index[0]} cancels {city.rate.iloc[0]:.0f}% of orders. "
                     "Check delivery promises and stock there.", rag(city.rate.iloc[0])))
    if len(prc):
        acts.append(("Product gap", f"{prc.index[0]} has the highest cancellation rate "
                     f"({prc.rate.iloc[0]:.0f}%). Check stock, listing quality and delivery "
                     "for this product.", rag(prc.rate.iloc[0])))
    lp = lost_df.groupby("payment_method").total_amount.sum().sort_values(ascending=False)
    if len(lp):
        acts.append(("Biggest revenue leak", f"{lp.index[0]} orders lost ₹{lp.iloc[0]:,.0f}, "
                     f"{lp.iloc[0] / max(lost, 1) * 100:.0f}% of all cancelled value. "
                     "Fixing it recovers the most money.", RED))
    if len(cat):
        acts.append(("Growth", f"{cat.index[0]} brings {cat.iloc[0] / max(revenue, 1) * 100:.0f}% "
                     "of revenue. Protect its stock and consider a targeted promotion.", GREEN))
    acts.append(("Money at risk", f"₹{lost:,.0f} of orders were cancelled ({rate:.0f}% vs "
                 f"{TARGET}% target). " + ("Above target: escalate to operations."
                                           if rate > TARGET else "Within target."), color))
    actions = [html.Div([html.Div(t, className="lbl", style={"color": c}),
                         html.Div(x, style={"marginTop": "6px", "lineHeight": "1.5"})],
                        className="card") for t, x, c in acts]

    subs = ([chip(f"{len(ok):,} completed"), delta_chip(rev_cur, rev_prev)],
            [chip(f"{len(lost_df):,} cancelled"), delta_chip(len(cur), len(prev))],
            [chip("per completed order")],
            [chip(status, color), delta_pts_chip(cr_cur, cr_prev)],
            [chip(f"{lost / max(revenue + lost, 1) * 100:.0f}% of gross", color)])
    figs = (line, gauge, cat_fig, prod_fig, pay_fig, map_fig, prc_fig, trend,
            lpay_fig, lcity_fig, lprod_fig)
    return ((f"₹{revenue:,.0f}", f"{len(df):,}", f"₹{aov:,.0f}", f"{rate:.1f}%", f"₹{lost:,.0f}") +
            subs + (stamp, actions) + figs + (watch_rows,))


if __name__ == "__main__":
    app.run(debug=False)