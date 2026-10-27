"""
NBA 冠軍球隊數據分析網頁（Streamlit）
資料來源：Supabase 資料庫（由 load_to_supabase.py 寫入）

執行方式（在 VS Code 終端機輸入）：
  streamlit run app.py

需要 .env 裡有 SUPABASE_URL 和 SUPABASE_PUBLISHABLE_KEY（只能讀、不能改的公開金鑰）
"""

import io
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# =====================================================================
# 設定區
# =====================================================================
TEAM_ZH = {"GSW": "勇士", "DEN": "金塊", "BOS": "塞爾提克", "OKC": "雷霆", "NYK": "尼克",
           "MIL": "公鹿", "LAL": "湖人", "TOR": "暴龍"}
# 每支球隊固定一個顏色（深色背景用的色盲友善配色），不管怎麼篩選都不會變
TEAM_COLORS = {"GSW": "#3987e5", "DEN": "#d95926", "BOS": "#199e70", "OKC": "#c98500",
               "NYK": "#d55181", "MIL": "#2f9e44", "LAL": "#9085e9", "TOR": "#e66767"}
# 球員比較用：依選取順序配色，最多 6 位
PLAYER_COLORS = ["#a78bfa", "#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"]
TYPE_OPTIONS = {"例行賽": "Regular Season", "附加賽": "PlayIn", "季後賽": "Playoffs"}

# 球隊指標：顯示名稱 →（欄位, 格式）
METRICS = {
    "真實命中率 TS%": ("ts", ".1%"),
    "三分出手比例": ("tpar", ".1%"),
    "三分命中率": ("fg3_pct", ".1%"),
    "場均三分出手": ("fg3a_pg", ".1f"),
    "場均得分": ("ppg", ".1f"),
    "場均助攻": ("apg", ".1f"),
    "助攻失誤比": ("ast_tov", ".2f"),
    "勝率": ("win_pct", ".1%"),
}
# 球員指標
P_METRICS = {
    "場均得分": ("ppg", ".1f"),
    "真實命中率 TS%": ("ts", ".1%"),
    "場均出手": ("fga_pg", ".1f"),
    "場均上場時間": ("mpg", ".1f"),
    "三分出手比例": ("tpar", ".1%"),
    "三分命中率": ("fg3_pct", ".1%"),
    "場均籃板": ("rpg", ".1f"),
    "場均助攻": ("apg", ".1f"),
    "出賽場數": ("gp", ".0f"),
}

# 配色：黑 × 紫
INK = "#ece8f5"           # 主要文字
INK_2 = "#a59fb8"         # 次要文字
MUTED = "#6f6883"         # 參考線
GRID = "rgba(167,139,250,0.10)"
ACCENT = "#a78bfa"        # 主色：薰衣草紫
FONT = "Noto Sans TC, Microsoft JhengHei, sans-serif"
# 熱力圖：同一個紫色由暗到亮（越亮數值越高）
PURPLE_RAMP = ["#1d1630", "#2c1f52", "#41307a", "#5b41a6", "#7a57cf", "#9d80e8", "#c8b6f8"]


# =====================================================================
# 網頁外觀
# =====================================================================
st.set_page_config(page_title="NBA 冠軍球隊數據分析", page_icon="🏆", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@300;400;500;700&family=Noto+Serif+TC:wght@500;700;900&display=swap');

html, body, [class*="css"], .stMarkdown, .stText { font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif; }
.stApp {
  background:
    radial-gradient(900px 480px at 85% -8%, rgba(124, 58, 237, 0.16), transparent 60%),
    radial-gradient(700px 420px at -5% 30%, rgba(88, 28, 135, 0.12), transparent 60%),
    #0b0910;
}
.block-container { padding-top: 2.2rem; padding-bottom: 4rem; max-width: 1400px; }

/* 側欄 */
section[data-testid="stSidebar"] { background: #0e0b15; border-right: 1px solid rgba(167,139,250,0.14); }
section[data-testid="stSidebar"] h3 { font-family: 'Noto Serif TC', serif; letter-spacing: 0.06em; color: #d8ccff; }

/* 頁首 */
.hero { position: relative; overflow: hidden;
        background: linear-gradient(135deg, #1a1030 0%, #120c1f 55%, #0d0a15 100%);
        border: 1px solid rgba(167,139,250,0.22); border-radius: 18px;
        padding: 30px 36px 26px; margin-bottom: 22px;
        box-shadow: 0 0 0 1px rgba(0,0,0,0.4), 0 24px 60px -30px rgba(124,58,237,0.45); }
.hero::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 2px;
        background: linear-gradient(90deg, transparent, #a78bfa 30%, #7c3aed 70%, transparent); }
.hero::after { content: ""; position: absolute; right: -80px; top: -120px; width: 320px; height: 320px;
        border-radius: 50%; border: 1px solid rgba(167,139,250,0.12);
        box-shadow: 0 0 0 40px rgba(167,139,250,0.03), 0 0 0 90px rgba(167,139,250,0.02); }
.hero-kicker { font-size: 0.74rem; letter-spacing: 0.32em; color: #b7a4f5; font-weight: 500; }
.hero h1 { font-family: 'Noto Serif TC', serif; color: #f4f0ff; font-size: 2.3rem; font-weight: 900;
           letter-spacing: 0.04em; margin: 8px 0 6px 0; padding: 0; }
.hero-sub { color: #a59fb8; font-size: 0.95rem; margin-bottom: 14px; font-weight: 300; }
.chip { display: inline-block; border: 1px solid rgba(167,139,250,0.32); color: #d8ccff;
        background: rgba(124,58,237,0.10); border-radius: 999px;
        padding: 3px 13px; margin: 4px 6px 0 0; font-size: 0.82rem; }

/* 重點數字卡片 */
.kpi { position: relative; border: 1px solid rgba(167,139,250,0.16); border-radius: 14px;
       padding: 16px 20px 15px 22px; height: 100%;
       background: linear-gradient(180deg, rgba(30,22,48,0.75), rgba(17,13,26,0.75)); }
.kpi::before { content: ""; position: absolute; left: 0; top: 16px; bottom: 16px; width: 2px;
       border-radius: 2px; background: linear-gradient(180deg, #a78bfa, #6d28d9); }
.kpi-label { font-size: 0.76rem; letter-spacing: 0.12em; color: #a59fb8; font-weight: 500; }
.kpi-value { font-family: 'Noto Serif TC', serif; font-size: 1.85rem; font-weight: 700;
             color: #f4f0ff; line-height: 1.3; margin-top: 4px; }
.kpi-sub { font-size: 0.78rem; color: #7f7894; margin-top: 2px; }

/* 區塊標題 */
.section-title { font-family: 'Noto Serif TC', serif; font-size: 1.2rem; font-weight: 700;
                 color: #efeaff; margin: 10px 0 2px 0; letter-spacing: 0.03em; }
.section-title::before { content: "◆"; color: #a78bfa; font-size: 0.7rem; margin-right: 10px;
                         position: relative; top: -2px; }
.section-sub { font-size: 0.84rem; color: #8d86a3; margin: 0 0 8px 20px; }

/* 分頁 */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid rgba(167,139,250,0.14); }
.stTabs [data-baseweb="tab"] { font-size: 0.98rem; font-weight: 500; padding: 10px 18px; color: #a59fb8;
                               letter-spacing: 0.05em; }
.stTabs [aria-selected="true"] { color: #e4dbff; }
.stTabs [data-baseweb="tab-highlight"] { background: linear-gradient(90deg, #a78bfa, #7c3aed); height: 2px; }

/* 細節 */
hr { border-color: rgba(167,139,250,0.14) !important; }
[data-testid="stExpander"] { border: 1px solid rgba(167,139,250,0.16); border-radius: 12px; }
.footnote { color: #6f6883; font-size: 0.78rem; text-align: center; margin-top: 36px; letter-spacing: 0.08em; }
</style>
""", unsafe_allow_html=True)


def kpi(col, label, value, sub=""):
    col.markdown(f'<div class="kpi"><div class="kpi-label">{label}</div>'
                 f'<div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>',
                 unsafe_allow_html=True)


def section(title, sub=""):
    st.markdown(f'<div class="section-title">{title}</div>'
                f'<div class="section-sub">{sub}</div>', unsafe_allow_html=True)


def style(fig, height):
    """統一圖表外觀：透明背景、淡紫格線、深色提示框"""
    fig.update_layout(
        height=height, margin=dict(l=8, r=24, t=8, b=8),
        font=dict(family=FONT, size=13, color=INK),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(font=dict(family=FONT, size=13, color=INK),
                        bgcolor="#1b1528", bordercolor="#6d4fc2"),
        legend=dict(orientation="h", y=-0.16, x=0, font=dict(color=INK_2)),
        bargap=0.35,
    )
    fig.update_xaxes(gridcolor=GRID, zeroline=False, showline=False,
                     tickfont=dict(color=INK_2), title_font=dict(color=INK_2))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False,
                     tickfont=dict(color=INK_2), title_font=dict(color=INK_2))
    return fig


def fmt(v, f):
    return "-" if pd.isna(v) else format(v, f)


def team_label(abbr):
    return f"{abbr} {TEAM_ZH.get(abbr, '')}".strip()


def rounded(fig):
    try:
        fig.update_traces(marker_cornerradius=4)
    except ValueError:
        pass


def champion_bands(fig, seasons, team):
    """在球員趨勢圖上，用淡紫色直條標出該隊奪冠的球季"""
    for i, s in enumerate(seasons):
        if (s, team) in CHAMP_SET:
            fig.add_vrect(x0=i - 0.5, x1=i + 0.5, fillcolor="rgba(167,139,250,0.10)",
                          line_width=0, layer="below")
            fig.add_annotation(x=s, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                               text="★ 奪冠", font=dict(size=11, color="#cbb8ff"))


# =====================================================================
# 從 Supabase 讀資料
# =====================================================================
@st.cache_resource
def get_client():
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        st.error("找不到 SUPABASE_URL 或 SUPABASE_PUBLISHABLE_KEY，請檢查 .env 檔")
        st.stop()
    return create_client(url, key)


def fetch_all(table, order_cols, page=1000):
    """資料庫一次最多回傳 1000 筆，所以一頁一頁讀到完"""
    client = get_client()
    rows, start = [], 0
    while True:
        q = client.table(table).select("*")
        for c in order_cols:
            q = q.order(c)
        part = q.range(start, start + page - 1).execute().data
        rows += part
        if len(part) < page:
            break
        start += page
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600, show_spinner="從資料庫讀取資料中…")
def load_data():
    team = fetch_all("team_season_stats", ["team_id", "season", "season_type"])
    players = fetch_all("player_season_stats", ["team_id", "season", "season_type", "player_id"])
    champs = fetch_all("champions", ["season"])
    teams = fetch_all("teams", ["team_id"])
    champs = champs.merge(teams[["team_id", "abbreviation"]], on="team_id")
    return team, players, champs


@st.cache_data(ttl=3600, show_spinner="讀取逐場數據中…")
def load_player_games(player_id, team_id, season):
    """讀取某位球員在某隊、某球季的逐場數據"""
    client = get_client()
    stats = (client.table("player_game_stats")
             .select("game_id,min,pts,fgm,fga,fg3m,fg3a,ftm,fta,reb,ast,"
                     "games!inner(game_date,season,season_type)")
             .eq("player_id", player_id).eq("team_id", team_id)
             .eq("games.season", season).execute().data)
    if not stats:
        return pd.DataFrame()
    df = pd.json_normalize(stats).rename(columns=lambda c: c.replace("games.", ""))
    tg = (client.table("team_games").select("game_id,matchup,wl")
          .eq("team_id", team_id).in_("game_id", df["game_id"].tolist()).execute().data)
    df = df.merge(pd.DataFrame(tg), on="game_id", how="left")
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df.sort_values("game_date")


def add_metrics(d, games_col="games"):
    """由加總數字算出各項指標"""
    d = d.copy()
    n = d[games_col].replace(0, pd.NA)
    d["ts"] = d["pts"] / (2 * (d["fga"] + 0.44 * d["fta"]))
    d["fg_pct"] = d["fgm"] / d["fga"]
    d["tpar"] = d["fg3a"] / d["fga"]
    d["fg3_pct"] = d["fg3m"] / d["fg3a"].replace(0, pd.NA)
    d["ppg"] = d["pts"] / n
    d["fga_pg"] = d["fga"] / n
    d["fg3a_pg"] = d["fg3a"] / n
    d["apg"] = d["ast"] / n
    d["rpg"] = d["reb"] / n
    d["ast_tov"] = d["ast"] / d["tov"].replace(0, pd.NA)
    if "min" in d.columns:
        d["mpg"] = d["min"] / n
    if "wins" in d.columns:
        d["win_pct"] = d["wins"] / n
    num = ["ts", "fg_pct", "tpar", "fg3_pct", "ppg", "fga_pg", "fg3a_pg", "apg", "rpg",
           "ast_tov", "mpg", "win_pct", games_col]
    for c in [c for c in num if c in d.columns]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


team_raw, player_raw, champs = load_data()
if team_raw.empty:
    st.error("資料庫裡還沒有資料，請先執行 load_to_supabase.py")
    st.stop()

ALL_TEAMS = [t for t in TEAM_ZH if t in set(team_raw["abbreviation"])]
ALL_SEASONS = sorted(team_raw["season"].unique())
CHAMP_SET = set(zip(champs["season"], champs["abbreviation"]))   # {(球季, 球隊)}
P_COLS = ["gp", "min", "pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "ast", "stl", "blk", "tov"]


# =====================================================================
# 左側：查詢條件
# =====================================================================
with st.sidebar:
    st.markdown("### 查詢條件")
    teams_sel = st.multiselect("球隊", ALL_TEAMS, default=ALL_TEAMS, format_func=team_label)
    s_from, s_to = st.select_slider("球季範圍", ALL_SEASONS,
                                    value=(ALL_SEASONS[0], ALL_SEASONS[-1]))
    types_sel = st.multiselect("比賽類型", list(TYPE_OPTIONS), default=["例行賽"],
                               help="跨球季比較建議只看例行賽：每隊每季都是 82 場左右，比較公平。"
                                    "季後賽場數差很多，數字容易被少數比賽影響。")
    metric_name = st.selectbox("球隊比較指標", list(METRICS))
    st.divider()
    st.caption("資料來源：NBA 官方數據（nba_api）→ Supabase 資料庫\n\n★ 代表該隊奪冠的球季")

if not teams_sel or not types_sel:
    st.warning("請至少選擇一支球隊和一種比賽類型")
    st.stop()

metric, mfmt = METRICS[metric_name]
seasons = [s for s in ALL_SEASONS if s_from <= s <= s_to]
types = [TYPE_OPTIONS[t] for t in types_sel]

# 依條件篩選，再把不同比賽類型加總成「球隊 × 球季」
t = team_raw[team_raw["abbreviation"].isin(teams_sel) & team_raw["season"].isin(seasons)
             & team_raw["season_type"].isin(types)]
num_cols = ["games", "wins", "pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta",
            "oreb", "dreb", "reb", "ast", "stl", "blk", "tov"]
team_season = add_metrics(t.groupby(["abbreviation", "season"], as_index=False)[num_cols].sum())
team_season["champion"] = [(s, a) in CHAMP_SET for s, a in
                           zip(team_season["season"], team_season["abbreviation"])]

if team_season.empty:
    st.warning("這個條件沒有資料，請換一個條件。")
    st.stop()


# =====================================================================
# 頁首
# =====================================================================
chips = "".join(f'<span class="chip">{team_label(a)}</span>' for a in teams_sel)
st.markdown(f"""
<div class="hero">
  <div class="hero-kicker">NBA CHAMPIONSHIP ANALYTICS</div>
  <h1>NBA 冠軍球隊數據分析</h1>
  <div class="hero-sub">2019–2026 八屆冠軍，近二十年的數據軌跡</div>
  <span class="chip">{s_from} – {s_to}</span>
  <span class="chip">{'・'.join(types_sel)}</span>{chips}
</div>
""", unsafe_allow_html=True)

k1, k2, k3, k4 = st.columns(4)
kpi(k1, "球隊", f"{len(teams_sel)} 隊", "2019～2026 八屆冠軍")
kpi(k2, "球季", f"{len(seasons)} 季", f"{s_from} ～ {s_to}")
kpi(k3, "比賽場數", f"{int(team_season['games'].sum()):,}", "所選球隊、球季、比賽類型合計")
kpi(k4, "範圍內奪冠球季", f"{int(team_season['champion'].sum())} 次", "圖上以 ★ 標示")
st.write("")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["球季趨勢", "球隊 × 球季", "冠軍球季比較", "球員", "數據表"])


# ---------- 1. 球季趨勢 ----------
with tab1:
    section(f"{metric_name}：各隊逐季變化", "每條線一支球隊；★ 是該隊奪冠的球季")
    fig = go.Figure()
    for abbr in teams_sel:
        d = team_season[team_season["abbreviation"] == abbr].sort_values("season")
        if d.empty:
            continue
        color = TEAM_COLORS.get(abbr, MUTED)
        fig.add_trace(go.Scatter(
            x=d["season"], y=d[metric], mode="lines+markers", name=team_label(abbr),
            line=dict(color=color, width=2),
            marker=dict(size=7, color=color, line=dict(width=1.5, color="#0b0910")),
            customdata=d[["games", "wins"]].values,
            hovertemplate=f"<b>{team_label(abbr)}</b>　%{{y:{mfmt}}}"
                          "（%{customdata[1]} 勝 / %{customdata[0]} 場）<extra></extra>",
        ))
        c = d[d["champion"]]
        if not c.empty:
            fig.add_trace(go.Scatter(
                x=c["season"], y=c[metric], mode="markers", showlegend=False, hoverinfo="skip",
                marker=dict(symbol="star", size=20, color=color, line=dict(width=1.5, color="#f4f0ff")),
            ))
    fig.update_yaxes(title=metric_name, tickformat=".0%" if "%" in mfmt else None)
    fig.update_xaxes(title="球季", categoryorder="array", categoryarray=seasons)
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style(fig, 480), width="stretch")


# ---------- 2. 球隊 × 球季 熱力圖 ----------
with tab2:
    section(f"{metric_name}：球隊 × 球季交叉表", "顏色越亮數值越高；★ 是奪冠球季；空白代表該季沒有這類比賽")
    pivot = team_season.pivot(index="abbreviation", columns="season", values=metric)
    pivot = pivot.reindex(index=[a for a in teams_sel if a in pivot.index], columns=seasons)
    z = pivot.values.astype(float)
    fig = go.Figure(go.Heatmap(
        z=z, x=pivot.columns, y=[team_label(a) for a in pivot.index],
        colorscale=[[i / (len(PURPLE_RAMP) - 1), c] for i, c in enumerate(PURPLE_RAMP)],
        xgap=2, ygap=2,
        colorbar=dict(title="", thickness=10, outlinewidth=0, tickfont=dict(color=INK_2),
                      tickformat=".0%" if "%" in mfmt else None),
        hovertemplate=f"%{{y}}　%{{x}}<br>{metric_name}：%{{z:{mfmt}}}<extra></extra>",
    ))
    zmin, zmax = pd.Series(z.ravel()).min(), pd.Series(z.ravel()).max()
    for i, abbr in enumerate(pivot.index):
        for j, season in enumerate(pivot.columns):
            v = z[i, j]
            if pd.isna(v):
                continue
            level = (v - zmin) / ((zmax - zmin) or 1)
            star = "★<br>" if (season, abbr) in CHAMP_SET else ""
            fig.add_annotation(x=season, y=team_label(abbr), showarrow=False,
                               text=star + fmt(v, mfmt),
                               font=dict(size=10.5, color="#140e20" if level > 0.6 else "#efeaf8"))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    fig.update_xaxes(showgrid=False, side="top")
    st.plotly_chart(style(fig, 100 + 62 * len(pivot.index)), width="stretch")


# ---------- 3. 冠軍球季比較 ----------
with tab3:
    champ_rows = team_season[team_season["champion"]].copy()
    if champ_rows.empty:
        st.info("目前的球隊與球季範圍內沒有奪冠球季。")
    else:
        champ_rows["label"] = champ_rows["season"] + " " + champ_rows["abbreviation"].map(team_label)
        champ_rows = champ_rows.sort_values("season")
        left, right = st.columns([3, 2], gap="large")
        with left:
            section(f"奪冠那一季的{metric_name}", "比較每支冠軍隊在奪冠球季的表現")
            d = champ_rows.sort_values(metric)
            fig = go.Figure(go.Bar(
                x=d[metric], y=d["label"], orientation="h",
                marker=dict(color=[TEAM_COLORS.get(a, MUTED) for a in d["abbreviation"]]),
                text=[fmt(v, mfmt) for v in d[metric]], textposition="outside", cliponaxis=False,
                textfont=dict(color=INK),
                hovertemplate=f"<b>%{{y}}</b><br>{metric_name}：%{{x:{mfmt}}}<extra></extra>",
            ))
            rounded(fig)
            fig.update_xaxes(showticklabels=False, showgrid=False)
            fig.update_yaxes(showgrid=False)
            st.plotly_chart(style(fig, max(320, 46 * len(d) + 60)), width="stretch")
        with right:
            section("奪冠球季 vs 該隊其他球季", "奪冠那季比該隊範圍內其他球季平均高（＋）或低（－）多少")
            rows = []
            for _, r in champ_rows.iterrows():
                others = team_season[(team_season["abbreviation"] == r["abbreviation"])
                                     & (~team_season["champion"])][metric].mean()
                diff = r[metric] - others
                diff_txt = "-" if pd.isna(diff) else (
                    f"{diff * 100:+.1f} 百分點" if "%" in mfmt else f"{diff:+.2f}")
                rows.append({"冠軍球季": r["label"], metric_name: fmt(r[metric], mfmt),
                             "其他球季平均": fmt(others, mfmt), "差距": diff_txt})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


# ---------- 4. 球員 ----------
with tab4:
    c1, c2 = st.columns([1, 2])
    p_team = c1.selectbox("球隊", teams_sel, format_func=team_label, key="p_team")
    mode = c2.radio("檢視方式", ["跨球季：在該隊的所有球季", "單一球季"], horizontal=True)
    color = TEAM_COLORS.get(p_team, ACCENT)
    team_id = int(team_raw[team_raw["abbreviation"] == p_team]["team_id"].iloc[0])

    # 這支球隊、所選球季範圍與比賽類型的球員數據
    pt = player_raw[(player_raw["abbreviation"] == p_team) & (player_raw["season"].isin(seasons))
                    & (player_raw["season_type"].isin(types))]

    if pt.empty:
        st.info("這個條件沒有球員資料。")

    elif mode.startswith("跨球季"):
        # 每位球員在這隊的生涯加總
        career = add_metrics(pt.groupby(["player_id", "player_name"], as_index=False)[P_COLS].sum(), "gp")
        career["seasons_n"] = pt.groupby("player_id")["season"].nunique().reindex(career["player_id"]).values
        career = career[career["gp"] >= 20].sort_values("pts", ascending=False)
        # 每位球員每一季
        per_season = add_metrics(
            pt.groupby(["player_id", "player_name", "season"], as_index=False)[P_COLS].sum(), "gp")

        c3, c4 = st.columns([2, 1])
        names = career["player_name"].tolist()
        picked = c3.multiselect("選擇球員（最多 6 位）", names, default=names[:3], max_selections=6,
                                help="依在這隊的總得分排序；只列出在這隊出賽至少 20 場的球員")
        p_metric_name = c4.selectbox("球員指標", list(P_METRICS))
        p_metric, p_fmt = P_METRICS[p_metric_name]

        section(f"{p_metric_name}：球員在{team_label(p_team)}的逐季變化",
                "X 軸球季、一條線一位球員；淡紫直條是這隊奪冠的球季；線條中斷代表那季不在隊上")
        if picked:
            fig = go.Figure()
            for i, name in enumerate(picked):
                d = (per_season[per_season["player_name"] == name]
                     .set_index("season").reindex(seasons).reset_index())
                pc = PLAYER_COLORS[i % len(PLAYER_COLORS)]
                fig.add_trace(go.Scatter(
                    x=d["season"], y=d[p_metric], mode="lines+markers", name=name, connectgaps=False,
                    line=dict(color=pc, width=2.2),
                    marker=dict(size=8, color=pc, line=dict(width=1.5, color="#0b0910")),
                    customdata=d[["gp"]].values,
                    hovertemplate=f"<b>{name}</b>　%{{y:{p_fmt}}}（出賽 %{{customdata[0]}} 場）<extra></extra>",
                ))
            champion_bands(fig, seasons, p_team)
            fig.update_xaxes(title="球季", categoryorder="array", categoryarray=seasons, type="category")
            fig.update_yaxes(title=p_metric_name, tickformat=".0%" if "%" in p_fmt else None)
            fig.update_layout(hovermode="x unified", margin=dict(l=8, r=24, t=28, b=8))
            st.plotly_chart(style(fig, 460), width="stretch")
        else:
            st.info("請至少選擇一位球員。")

        section(f"{team_label(p_team)} 球員在隊生涯總覽",
                f"{s_from}～{s_to}・{'・'.join(types_sel)}；出賽至少 20 場；可點欄位名稱排序")
        table = career.copy()
        for c in ["ts", "fg_pct", "fg3_pct", "tpar"]:
            table[c] = table[c] * 100
        st.dataframe(
            table[["player_name", "seasons_n", "gp", "ppg", "mpg", "fga_pg", "ts", "fg_pct",
                   "fg3_pct", "rpg", "apg", "pts"]],
            hide_index=True, width="stretch", height=420,
            column_config={
                "player_name": st.column_config.TextColumn("球員", width="medium"),
                "seasons_n": st.column_config.NumberColumn("球季數"),
                "gp": st.column_config.NumberColumn("出賽"),
                "ppg": st.column_config.NumberColumn("場均得分", format="%.1f"),
                "mpg": st.column_config.NumberColumn("場均時間", format="%.1f"),
                "fga_pg": st.column_config.NumberColumn("場均出手", format="%.1f"),
                "ts": st.column_config.ProgressColumn("真實命中率", format="%.1f%%", min_value=40, max_value=70),
                "fg_pct": st.column_config.NumberColumn("投籃命中率", format="%.1f%%"),
                "fg3_pct": st.column_config.NumberColumn("三分命中率", format="%.1f%%"),
                "rpg": st.column_config.NumberColumn("場均籃板", format="%.1f"),
                "apg": st.column_config.NumberColumn("場均助攻", format="%.1f"),
                "pts": st.column_config.NumberColumn("總得分", format="%d"),
            },
        )
        if picked:
            with st.expander("查看所選球員的逐季數據"):
                d = per_season[per_season["player_name"].isin(picked)].copy()
                d["champ"] = d["season"].map(lambda s: "★" if (s, p_team) in CHAMP_SET else "")
                for c in ["ts", "fg3_pct"]:
                    d[c] = d[c] * 100
                st.dataframe(
                    d.sort_values(["player_name", "season"])[
                        ["player_name", "season", "champ", "gp", "ppg", "mpg", "fga_pg", "ts", "fg3_pct", "rpg", "apg"]],
                    hide_index=True, width="stretch",
                    column_config={
                        "player_name": "球員", "season": "球季", "champ": "奪冠", "gp": "出賽",
                        "ppg": st.column_config.NumberColumn("場均得分", format="%.1f"),
                        "mpg": st.column_config.NumberColumn("場均時間", format="%.1f"),
                        "fga_pg": st.column_config.NumberColumn("場均出手", format="%.1f"),
                        "ts": st.column_config.NumberColumn("真實命中率", format="%.1f%%"),
                        "fg3_pct": st.column_config.NumberColumn("三分命中率", format="%.1f%%"),
                        "rpg": st.column_config.NumberColumn("場均籃板", format="%.1f"),
                        "apg": st.column_config.NumberColumn("場均助攻", format="%.1f"),
                    },
                )

    else:
        # ---- 單一球季 ----
        p_seasons = sorted(pt["season"].unique(), reverse=True)
        p_season = st.selectbox("球季", p_seasons,
                                format_func=lambda s: s + ("　★ 奪冠" if (s, p_team) in CHAMP_SET else ""))
        p = pt[pt["season"] == p_season]
        players = add_metrics(p.groupby(["player_id", "player_name"], as_index=False)[P_COLS].sum(), "gp")
        team_games_n = int(team_season[(team_season["abbreviation"] == p_team)
                                       & (team_season["season"] == p_season)]["games"].sum())
        min_gp = max(1, round(team_games_n * 0.1))
        players = players[(players["gp"] >= min_gp) & (players["fga"] > 0)].sort_values("pts", ascending=False)

        if players.empty:
            st.info("這個條件沒有球員資料。")
        else:
            left, right = st.columns([3, 2], gap="large")
            with left:
                section("出手量 vs 投籃效率", f"出賽至少 {min_gp} 場的球員；點越大總得分越多；虛線為中位數")
                top = set(players.head(8)["player_name"])
                fig = go.Figure(go.Scatter(
                    x=players["fga_pg"], y=players["ts"], mode="markers+text",
                    text=[n if n in top else "" for n in players["player_name"]],
                    textposition="top center", textfont=dict(size=12, color=INK),
                    marker=dict(size=12 + 26 * (players["pts"] / players["pts"].max()) ** 0.5,
                                color=color, opacity=0.9, line=dict(width=1.5, color="#0b0910")),
                    customdata=players[["player_name", "gp", "ppg"]].values,
                    hovertemplate="<b>%{customdata[0]}</b><br>出賽 %{customdata[1]} 場｜場均 %{customdata[2]:.1f} 分"
                                  "<br>場均出手 %{x:.1f}｜TS% %{y:.1%}<extra></extra>",
                ))
                fig.add_vline(x=players["fga_pg"].median(), line=dict(color=MUTED, width=1, dash="dot"))
                fig.add_hline(y=players["ts"].median(), line=dict(color=MUTED, width=1, dash="dot"))
                fig.update_xaxes(title="場均投籃出手")
                fig.update_yaxes(title="真實命中率 TS%", tickformat=".0%")
                st.plotly_chart(style(fig, 440), width="stretch")
            with right:
                section("場均得分", f"{team_label(p_team)} {p_season}")
                d = players.head(12).sort_values("ppg")
                fig = go.Figure(go.Bar(
                    x=d["ppg"], y=d["player_name"], orientation="h", marker=dict(color=color),
                    text=[f"{v:.1f}" for v in d["ppg"]], textposition="outside", cliponaxis=False,
                    textfont=dict(color=INK),
                    hovertemplate="<b>%{y}</b><br>場均 %{x:.1f} 分<extra></extra>",
                ))
                rounded(fig)
                fig.update_xaxes(showticklabels=False, showgrid=False)
                fig.update_yaxes(showgrid=False)
                st.plotly_chart(style(fig, 440), width="stretch")

            st.divider()
            name = st.selectbox("查看球員逐場得分", players["player_name"])
            pid = int(players[players["player_name"] == name]["player_id"].iloc[0])
            g = load_player_games(pid, team_id, p_season)
            g = g[g["season_type"].isin(types)] if not g.empty else g
            if g.empty:
                st.info("沒有逐場數據。")
            else:
                g["avg5"] = g["pts"].rolling(5, min_periods=1).mean()
                section(f"{name} 逐場得分", "淺色點是單場得分，亮線是近 5 場平均")
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=g["game_date"], y=g["pts"], mode="markers", name="單場得分",
                    marker=dict(size=8, color=color, opacity=0.4, line=dict(width=1, color="#0b0910")),
                    customdata=g[["matchup", "wl", "fgm", "fga", "fg3m", "fg3a"]].values,
                    hovertemplate="<b>%{x|%Y-%m-%d}</b>　%{customdata[0]}（%{customdata[1]}）<br>"
                                  "得分 %{y}｜投籃 %{customdata[2]}-%{customdata[3]}｜"
                                  "三分 %{customdata[4]}-%{customdata[5]}<extra></extra>",
                ))
                fig.add_trace(go.Scatter(
                    x=g["game_date"], y=g["avg5"], mode="lines", name="近 5 場平均",
                    line=dict(color=color, width=2.5, shape="spline", smoothing=0.6),
                    hovertemplate="近 5 場平均 %{y:.1f} 分<extra></extra>",
                ))
                fig.update_yaxes(title="得分", rangemode="tozero")
                fig.update_layout(hovermode="x unified")
                st.plotly_chart(style(fig, 380), width="stretch")


# ---------- 5. 數據表 ----------
with tab5:
    section("球隊 × 球季 數據表", "可點欄位名稱排序；★ 為奪冠球季")
    table = team_season.copy()
    table["球隊"] = table["abbreviation"].map(team_label)
    table["奪冠"] = table["champion"].map({True: "★", False: ""})
    for c in ["win_pct", "ts", "fg_pct", "tpar", "fg3_pct"]:
        table[c] = table[c] * 100
    table = table[["球隊", "season", "奪冠", "games", "wins", "win_pct", "ppg", "ts", "fg_pct",
                   "tpar", "fg3_pct", "fg3a_pg", "apg", "ast_tov"]]
    st.dataframe(
        table, hide_index=True, width="stretch", height=520,
        column_config={
            "season": "球季", "games": "場數", "wins": "勝場",
            "win_pct": st.column_config.NumberColumn("勝率", format="%.1f%%"),
            "ppg": st.column_config.NumberColumn("場均得分", format="%.1f"),
            "ts": st.column_config.ProgressColumn("真實命中率", format="%.1f%%", min_value=48, max_value=62),
            "fg_pct": st.column_config.NumberColumn("投籃命中率", format="%.1f%%"),
            "tpar": st.column_config.NumberColumn("三分出手比例", format="%.1f%%"),
            "fg3_pct": st.column_config.NumberColumn("三分命中率", format="%.1f%%"),
            "fg3a_pg": st.column_config.NumberColumn("場均三分出手", format="%.1f"),
            "apg": st.column_config.NumberColumn("場均助攻", format="%.1f"),
            "ast_tov": st.column_config.NumberColumn("助攻失誤比", format="%.2f"),
        },
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        table.to_excel(writer, sheet_name="球隊球季", index=False)
    st.download_button("下載 Excel", data=buffer.getvalue(), type="primary",
                       file_name=f"champions_{s_from}_{s_to}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    with st.expander("指標說明"):
        st.markdown("""
| 指標 | 意思 | 算法 |
|---|---|---|
| 真實命中率 TS% | 把二分、三分、罰球都算進去，每次出手換到多少分 | 得分 ÷ [2 ×（出手 + 0.44 × 罰球出手）] |
| 三分出手比例 | 全部出手中三分球佔幾成 | 三分出手 ÷ 全部出手 |
| 三分命中率 | 三分球投進的比例 | 三分命中 ÷ 三分出手 |
| 助攻失誤比 | 每一次失誤對應幾次助攻，越高代表傳球越穩 | 助攻 ÷ 失誤 |
| 勝率 | 贏球場數比例 | 勝場 ÷ 場數 |
""")

st.markdown('<div class="footnote">DATA · NBA STATS API　｜　STORAGE · SUPABASE　｜　BUILT WITH STREAMLIT</div>',
            unsafe_allow_html=True)
