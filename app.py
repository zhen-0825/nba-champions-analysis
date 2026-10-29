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
# 其他 22 隊（每天慢慢載入球員逐場數據；載入後會出現在篩選列的球隊選項，預設不勾選）
OTHER_ZH = {"SAS": "馬刺", "DAL": "獨行俠", "MIA": "熱火", "CLE": "騎士", "ATL": "老鷹", "BKN": "籃網",
            "CHA": "黃蜂", "CHI": "公牛", "DET": "活塞", "HOU": "火箭", "IND": "溜馬", "LAC": "快艇",
            "MEM": "灰熊", "MIN": "灰狼", "NOP": "鵜鶘", "ORL": "魔術", "PHI": "七六人", "PHX": "太陽",
            "POR": "拓荒者", "SAC": "國王", "UTA": "爵士", "WAS": "巫師"}
ALL_ZH = {**TEAM_ZH, **OTHER_ZH}
# 每支球隊固定一個顏色，取自球衣主視覺色，並調亮到深色背景上看得清楚
TEAM_COLORS = {
    "GSW": "#1F5BCC",   # 勇士：皇家藍
    "DEN": "#B07D00",   # 金塊：金黃（白底上調深，才看得清楚）
    "BOS": "#00843D",   # 塞爾提克：塞爾提克綠
    "OKC": "#0A93C9",   # 雷霆：雷霆藍
    "NYK": "#E06A1B",   # 尼克：尼克橘
    "MIL": "#2F5D3A",   # 公鹿：深綠（奶油白在白底上看不見，改用公鹿的另一個主色）
    "LAL": "#6B3FB5",   # 湖人：湖人紫
    "TOR": "#C8102E",   # 暴龍：暴龍紅
}
DIM = "#d6d2df"          # 聚焦模式下，未選取球隊的淺灰色
# 球員比較用：依選取順序配色，最多 6 位
PLAYER_COLORS = ["#6250d6", "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]
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
INK = "#1a1426"           # 主要文字（近黑）
INK_2 = "#5f5873"         # 次要文字
MUTED = "#8f889f"         # 參考線
GRID = "rgba(76,42,150,0.08)"   # 很淡的紫灰格線
ACCENT = "#7c3aed"        # 主色：紫（白底上用深一點的紫）
SURFACE = "#ffffff"       # 圖表底色（點的外圈用它，讓重疊的點分得開）
FONT = "Noto Sans TC, Microsoft JhengHei, sans-serif"
# 熱力圖：同一個紫色由淺到深（越深數值越高）
PURPLE_RAMP = ["#f3effc", "#e1d6fa", "#c7b3f3", "#a98be8", "#8a63d9", "#6b42c2", "#4c2a96"]


# =====================================================================
# 網頁外觀
# =====================================================================
st.set_page_config(page_title="NBA 冠軍球隊數據分析", page_icon="docs/logo/zhen_logo.png" if os.path.exists("docs/logo/zhen_logo.png") else None, layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700;900&display=swap');

/* =========================================================
   配色：資料區用「白底＋深色字」最好讀；黑×紫用在品牌的地方
   （左側選單、首頁橫幅、目前所在位置、重點強調），不放在圖表後面
   ========================================================= */
:root {
  --bg: #f6f5fa;        /* 頁面底色：帶一點點紫的淺灰 */
  --surface: #ffffff;   /* 卡片、表格底色 */
  --ink: #1a1426;       /* 主要文字 */
  --ink-2: #5f5873;     /* 次要文字 */
  --muted: #8f889f;     /* 說明文字 */
  --line: #e7e3ef;      /* 分隔線 */
  --brand: #7c3aed;     /* 主色：紫 */
  --brand-soft: #f1ebfe;
  --night: #0d0a14;     /* 品牌黑 */
}
html, body, [class*="css"], .stMarkdown, .stText { font-family: 'Noto Sans TC', 'Microsoft JhengHei', sans-serif; }
.stApp { background: var(--bg); }
.block-container { padding-top: 1.6rem; padding-bottom: 4rem; max-width: 1360px; }

/* ===== 左側：品牌黑底選單（參考 YouTube 的左側導覽）===== */
section[data-testid="stSidebar"] { background: var(--night); border-right: 1px solid #241b38; }
section[data-testid="stSidebar"] * { color: #d9d3ea; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #8d86a3 !important; font-size: 0.78rem; }
section[data-testid="stSidebar"] hr { border-color: #241b38 !important; }
.logo { display: flex; align-items: center; gap: 12px; margin: 0 0 18px 4px; }
.logo img { width: 38px; height: 38px; }
.logo-name { font-size: 1.35rem; font-weight: 900; letter-spacing: 0.02em; line-height: 1.1; }
.logo-name .z { color: #a78bfa !important; } .logo-name .h { color: #f4f0ff !important; }
.logo-tag { font-size: 0.62rem; letter-spacing: 0.22em; color: #8d86a3 !important; margin-top: 2px; }
.nav-group { font-size: 0.72rem; letter-spacing: 0.16em; color: #8d86a3 !important; margin: 18px 0 4px 12px; }
section[data-testid="stSidebar"] .stButton > button {
  justify-content: flex-start; text-align: left; border-radius: 10px; padding: 0.5rem 0.9rem;
  border: 1px solid transparent; background: transparent; box-shadow: none; }
section[data-testid="stSidebar"] .stButton > button:hover { background: #1c1529; border-color: transparent; }
section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
  background: #2a1d4a !important; border-left: 3px solid #a78bfa !important; }
section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p { color: #ffffff !important; font-weight: 700; }
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: 0.2rem; }

/* ===== 首頁橫幅：唯一一塊大面積的黑×紫 ===== */
.hero { background: var(--night); border-radius: 16px; padding: 28px 32px 24px; margin-bottom: 18px;
        border-left: 4px solid var(--brand); }
.hero h1 { color: #ffffff; font-size: 2rem; font-weight: 900; margin: 0 0 6px 0; padding: 0; }
.hero-sub { color: #b9b1cf; font-size: 0.98rem; margin-bottom: 14px; }
.chip { display: inline-block; border: 1px solid #3a2d5c; color: #d9d0f5; background: #1a1328;
        border-radius: 999px; padding: 3px 12px; margin: 4px 6px 0 0; font-size: 0.8rem; }

/* ===== 各頁頁首：麵包屑＋標題＋這頁的問題 ===== */
.pagehead { padding: 0 0 12px 0; margin-bottom: 12px; border-bottom: 1px solid var(--line); }
.pagehead .crumb { font-size: 0.78rem; color: var(--muted); }
.pagehead h2 { font-weight: 900; color: var(--ink); font-size: 1.7rem; margin: 2px 0 2px 0; padding: 0; }
.pagehead .pq { color: var(--brand); font-size: 1rem; font-weight: 500; }

/* ===== 數字卡 ===== */
.kpi { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 14px 18px; height: 100%; }
.kpi-label { font-size: 0.8rem; color: var(--ink-2); font-weight: 500; }
.kpi-value { font-size: 1.7rem; font-weight: 900; color: var(--ink); line-height: 1.3; margin-top: 2px; font-variant-numeric: tabular-nums; }
.kpi-sub { font-size: 0.78rem; color: var(--muted); margin-top: 2px; }

/* ===== 區塊標題：左邊一條紫色短線，取代裝飾符號 ===== */
.section-title { font-size: 1.12rem; font-weight: 700; color: var(--ink); margin: 18px 0 2px 0;
                 padding-left: 10px; border-left: 3px solid var(--brand); line-height: 1.3; }
.section-sub { font-size: 0.85rem; color: var(--ink-2); margin: 2px 0 8px 13px; }

/* ===== 篩選列、圖表外框 ===== */
[data-testid="stVerticalBlockBorderWrapper"] { background: var(--surface); border-color: var(--line) !important; border-radius: 12px; }
[data-testid="stPlotlyChart"] { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 6px 4px; }
[data-testid="stExpander"] { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
[data-testid="stDataFrame"] { border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
hr { border-color: var(--line) !important; }

/* ===== 重點摘要框：淡紫底、深色字 ===== */
.insight { border: 1px solid #ddd0fb; background: var(--brand-soft); border-radius: 12px;
           padding: 12px 18px; margin: 6px 0 10px 0; color: #2d2245; font-size: 0.92rem; line-height: 1.8; }
.insight b { color: #4c1d95; }

/* ===== 按鈕、選項 ===== */
.stButton > button, .stDownloadButton > button { border-radius: 999px; padding: 0.5rem 1.2rem; font-weight: 500; }
[data-testid="stBaseButton-pills"], [data-testid="stBaseButton-pillsActive"],
[data-testid="stBaseButton-segmented_control"], [data-testid="stBaseButton-segmented_controlActive"] {
  min-height: 2.2rem; padding: 0.3rem 0.9rem; font-size: 0.9rem; }
[data-testid="stBaseButton-pillsActive"], [data-testid="stBaseButton-segmented_controlActive"] {
  background: var(--brand-soft) !important; border-color: var(--brand) !important; color: #4c1d95 !important; }

/* ===== 精簡表格：只有橫向細線、數字靠右對齊 ===== */
.ntable { width: 100%; border-collapse: collapse; font-size: 0.9rem; margin: 4px 0 8px 0; background: var(--surface);
          border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
.ntable th { text-align: left; font-weight: 500; font-size: 0.78rem; color: var(--ink-2);
             padding: 9px 12px; border-bottom: 1px solid #d9d3e6; background: #faf9fc; }
.ntable td { padding: 9px 12px; color: var(--ink); border-bottom: 1px solid #f0edf5; }
.ntable td.num, .ntable th.num { text-align: right; font-variant-numeric: tabular-nums; }
.ntable tr:hover td { background: #f7f3ff; }
.ntable .pos { color: #5b21b6; font-weight: 500; } .ntable .neg { color: var(--muted); }
.ntable .barcell { display: flex; align-items: center; justify-content: flex-end; gap: 10px; }
.ntable .bar { display: inline-block; height: 6px; flex: 0 0 auto; border-radius: 3px; background: #a78bfa; }
.dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 8px; position: relative; top: -1px; }

/* ===== 首頁卡片牆（參考 YouTube 影片卡）===== */
.home-group { font-size: 1.1rem; font-weight: 700; color: var(--ink); margin: 24px 0 10px 0; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; overflow: hidden;
        min-height: 176px; margin-bottom: 8px; transition: box-shadow 0.15s ease, border-color 0.15s ease; }
.card:hover { border-color: #c4b5fd; box-shadow: 0 6px 18px -10px rgba(76,29,149,0.35); }
.card-top { background: var(--night); padding: 12px 18px; display: flex; justify-content: space-between; align-items: center; }
.card-num { font-size: 0.8rem; color: #a78bfa; font-weight: 700; letter-spacing: 0.1em; }
.card-tag { font-size: 0.72rem; color: #b9b1cf; }
.card-body { padding: 12px 18px 16px 18px; }
.card-title { font-size: 1.2rem; font-weight: 900; color: var(--ink); }
.card-q { color: var(--brand); font-size: 0.93rem; margin-top: 2px; font-weight: 500; }
.card-desc { color: var(--ink-2); font-size: 0.84rem; line-height: 1.6; margin-top: 8px; }
.footnote { color: var(--muted); font-size: 0.78rem; text-align: center; margin-top: 36px; }
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
    # 圖的上緣如果有文字標註（例如「★ 奪冠」），上方多留空間，免得字被切掉
    try:
        top = 34 if any(a.yref == "paper" and (a.y or 0) >= 1 for a in fig.layout.annotations) else 8
    except Exception:
        top = 8
    fig.update_layout(
        height=height, margin=dict(l=8, r=24, t=top, b=8),
        font=dict(family=FONT, size=13, color=INK),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        hoverlabel=dict(font=dict(family=FONT, size=13, color=INK),
                        bgcolor="#ffffff", bordercolor="#c4b5fd"),
        legend=dict(orientation="h", y=-0.16, x=0, font=dict(color=INK_2)),
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, zeroline=False, showline=False,
                     tickfont=dict(color=INK_2), title_font=dict(color=INK_2))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, showline=False,
                     tickfont=dict(color=INK_2), title_font=dict(color=INK_2))
    return fig


def fmt(v, f):
    return "-" if pd.isna(v) else format(v, f)


def team_label(abbr):
    return f"{abbr} {ALL_ZH.get(abbr, '')}".strip()


def rounded(fig):
    try:
        fig.update_traces(marker_cornerradius=4)
    except ValueError:
        pass


def seg(label, options, key, default=None):
    """少量選項的單選：一排相連的按鈕（比下拉選單少點一次）"""
    default = default or options[0]
    try:
        v = st.segmented_control(label, options, default=default, key=key)
    except AttributeError:   # 舊版 Streamlit 沒有這個元件
        v = st.radio(label, options, horizontal=True, key=key)
    return v or default


def pills(label, options, key, default=None, multi=False, format_func=str, where=st):
    """膠囊按鈕：選項一眼看完，點一下就切換"""
    try:
        v = where.pills(label, options, selection_mode="multi" if multi else "single",
                        default=default, format_func=format_func, key=key)
    except AttributeError:
        v = (where.multiselect(label, options, default=default, format_func=format_func, key=key) if multi
             else where.selectbox(label, options, format_func=format_func, key=key))
    if multi:
        return list(v or [])
    return v or (default if default is not None else options[0])


def nice_table(df, num_cols=(), signed_cols=(), dot_col=None, colors=None, bars=None):
    """精簡的 HTML 表格：只有橫向細線，數字靠右；dot_col 欄位前面加上球隊顏色圓點
    bars={"顯示欄位": "_隱藏的數值欄位"}：在數字旁加一條細長條（數值 0～1 代表長條長度），不用讀數字也能比大小"""
    bars = bars or {}
    shown = [c for c in df.columns if not str(c).startswith("_")]   # 底線開頭的欄位不顯示
    head = "".join(f'<th class="{"num" if c in num_cols else ""}">{c}</th>' for c in shown)
    body = []
    for _, r in df.iterrows():
        cells = []
        for c in shown:
            v, cls = r[c], "num" if c in num_cols else ""
            if c in signed_cols and isinstance(v, str) and v[:1] in "+-":
                cls += " pos" if v.startswith("+") else " neg"
            if c == dot_col and colors:
                v = f'<span class="dot" style="background:{colors.get(r.get("_key"), MUTED)}"></span>{v}'
            if c in bars and pd.notna(r.get(bars[c])):
                w = max(0.0, min(1.0, float(r[bars[c]]))) * 70   # 最長 70 像素
                v = f'<div class="barcell"><span class="bar" style="width:{w:.0f}px"></span><span>{v}</span></div>'
            cells.append(f'<td class="{cls}">{v}</td>')
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(f'<table class="ntable"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>',
                unsafe_allow_html=True)


def champion_bands(fig, seasons, team):
    """在球員趨勢圖上，用淡紫色直條標出該隊奪冠的球季"""
    for i, s in enumerate(seasons):
        if (s, team) in CHAMP_SET:
            fig.add_vrect(x0=i - 0.5, x1=i + 0.5, fillcolor="rgba(167,139,250,0.10)",
                          line_width=0, layer="below")
            fig.add_annotation(x=s, y=1.0, yref="paper", yanchor="bottom", showarrow=False,
                               text="★ 奪冠", font=dict(size=11, color="#6d28d9"))


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


@st.cache_data(ttl=900, show_spinner="從資料庫讀取資料中…")   # 每 15 分鐘重新讀一次資料庫
def load_data():
    team = fetch_all("team_season_stats", ["team_id", "season", "season_type"])
    players = fetch_all("player_season_stats", ["team_id", "season", "season_type", "player_id"])
    champs = fetch_all("champions", ["season"])
    teams = fetch_all("teams", ["team_id"])
    champs = champs.merge(teams[["team_id", "abbreviation"]], on="team_id")
    try:
        league = fetch_all("league_team_seasons", ["season", "season_type", "team_id"])
        league = league.merge(teams[["team_id", "abbreviation"]], on="team_id", how="left")
    except Exception:
        league = pd.DataFrame()
    return team, players, champs, league


@st.cache_data(ttl=900, show_spinner="讀取逐場數據中…")
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


@st.cache_data(ttl=900)
def latest_game_date():
    """資料庫裡最新一場比賽的日期，用來顯示資料更新到哪一天"""
    try:
        rows = (get_client().table("games").select("game_date")
                .order("game_date", desc=True).limit(1).execute().data)
        return rows[0]["game_date"] if rows else None
    except Exception:
        return None


@st.cache_data(ttl=900)
def table_status(table):
    """進階資料表的狀態：'missing' 表不存在、'empty' 表是空的、'ok' 有資料"""
    try:
        rows = get_client().table(table).select("*").limit(1).execute().data
    except Exception:
        return "missing"
    return "ok" if rows else "empty"


@st.cache_data(ttl=3600, show_spinner="讀取投籃紀錄中…（一季約 7,000 次出手）")
def load_shots(team_id, season, season_type):
    """某隊某季的每一次出手。shots 表很大，所以一定先用 .eq() 篩選，再一頁一頁讀"""
    client = get_client()
    rows, start, page = [], 0, 1000
    try:
        while True:
            part = (client.table("shots")
                    .select("game_id,game_event_id,player_id,player_name,loc_x,loc_y,made,zone_basic,zone_area,shot_distance")
                    .eq("team_id", team_id).eq("season", season).eq("season_type", season_type)
                    .order("game_id").order("game_event_id")
                    .range(start, start + page - 1).execute().data)
            rows += part
            if len(part) < page:
                break
            start += page
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


@st.cache_data(ttl=3600)
def load_zone_league():
    """聯盟各區域的出手數與命中數（所有球季）"""
    try:
        return fetch_all("shot_zone_league", ["season", "season_type", "zone_basic", "zone_area", "zone_range"])
    except Exception:
        return pd.DataFrame()


VIEW_ERRORS = {}   # 檢視表讀取失敗時，把真正的錯誤訊息記下來顯示在畫面上


@st.cache_data(ttl=3600)
def _read_view(view, col, value):
    """讀檢視表（成功才會被快取；失敗會丟出錯誤，Streamlit 不會記住失敗的結果）"""
    rows, start, page = [], 0, 1000
    while True:   # Supabase 一次最多回 1000 筆，所以一樣一頁一頁讀
        part = (get_client().table(view).select("*").eq(col, value)
                .order("season").order("zone_basic").order("zone_area")
                .range(start, start + page - 1).execute().data)
        rows += part
        if len(part) < page:
            return pd.DataFrame(rows)
        start += page


def load_view(view, col, value):
    """回傳 DataFrame；讀不到就回傳 None，並把原因記在 VIEW_ERRORS"""
    try:
        return _read_view(view, col, int(value))
    except Exception as e:
        VIEW_ERRORS[view] = f"{type(e).__name__}: {e}"[:300]
        return None


def load_zone_team(team_id):
    """球隊每季各區域出手彙總（需要先建立 shot_zone_team 檢視表）"""
    return load_view("shot_zone_team", "team_id", team_id)


def load_zone_player(player_id):
    """球員每季各區域出手彙總（需要先建立 shot_zone_player 檢視表）"""
    return load_view("shot_zone_player", "player_id", player_id)


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


team_raw, player_raw, champs, league = load_data()
if team_raw.empty:
    st.error("資料庫裡還沒有資料，請先執行 load_to_supabase.py")
    st.stop()

ALL_TEAMS = [t for t in TEAM_ZH if t in set(team_raw["abbreviation"])]   # 八支冠軍隊（投籃、陣容等進階數據只有這八隊）
# 已經載入球員逐場數據的其他球隊（依英文縮寫排序）
EXTRA_TEAMS = sorted(t for t in set(team_raw["abbreviation"]) if t not in TEAM_ZH)
ALL_SEASONS = sorted(team_raw["season"].unique())
CHAMP_SET = set(zip(champs["season"], champs["abbreviation"]))   # {(球季, 球隊)}
P_COLS = ["gp", "min", "pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "reb", "ast", "stl", "blk", "tov"]


# =====================================================================
# 導覽：左側像 YouTube 一樣是「頁面選單」，篩選條件移到各頁上方
# =====================================================================
# ZheN 標誌：黑底圓角方塊裡一個紫色的 Z，下面那一橫做成上升的折線＋一個資料點（原始檔在 docs/logo/）
LOGO_B64 = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgdmlld0JveD0iMCAwIDQwIDQwIj4gPGRlZnM+IDxsaW5lYXJHcmFkaWVudCBpZD0iemciIHgxPSIwIiB5MT0iMCIgeDI9IjEiIHkyPSIxIj4gPHN0b3Agb2Zmc2V0PSIwIiBzdG9wLWNvbG9yPSIjYzRiNWZkIi8+IDxzdG9wIG9mZnNldD0iMSIgc3RvcC1jb2xvcj0iIzdjM2FlZCIvPiA8L2xpbmVhckdyYWRpZW50PiA8L2RlZnM+IDxyZWN0IHg9IjAuNSIgeT0iMC41IiB3aWR0aD0iMzkiIGhlaWdodD0iMzkiIHJ4PSIxMCIgZmlsbD0iIzBkMGExNCIgc3Ryb2tlPSIjN2MzYWVkIiBzdHJva2Utb3BhY2l0eT0iMC43Ii8+IDxwYXRoIGQ9Ik0xMSAxMS41IEgyOC41IEwxMS41IDI3LjUgTDE3IDI3LjUgTDIxLjUgMjMuNSBMMjUgMjYgTDI5LjUgMjEiIGZpbGw9Im5vbmUiIHN0cm9rZT0idXJsKCN6ZykiIHN0cm9rZS13aWR0aD0iMyIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+IDxjaXJjbGUgY3g9IjI5LjUiIGN5PSIyMSIgcj0iMi40IiBmaWxsPSIjZjRmMGZmIi8+IDwvc3ZnPg=="

# （群組, 頁面名稱, 這頁回答的問題, 卡片說明, 這頁要用到哪些篩選）
PAGES = [
    ("冠軍故事", "冠軍密碼", "奪冠最需要什麼？",
     "冠軍在攻守效率、三分、籃板等 10 項指標排聯盟第幾；三分時代與冠軍輪替。", {"season"}),
    ("冠軍故事", "投籃分布", "冠軍從哪裡出手？",
     "半場球場圖：奪冠那季的出手位置，和聯盟平均、和自己其他球季比較。", set()),
    ("冠軍故事", "戰術使用", "冠軍靠什麼戰術得分？",
     "戰術地圖、八位冠軍的共同點、全聯盟各隊比較與奪冠方程式。", set()),
    ("自由探索", "球季趨勢", "各隊一路怎麼變化？",
     "選一個指標，看各隊 20 季的折線；可聚焦幾支球隊，其他變灰。", {"team", "season", "type", "metric"}),
    ("自由探索", "球隊 × 球季", "哪隊在哪季特別突出？",
     "熱力圖一次看完所有球隊、所有球季，顏色越深越高，★ 是奪冠季。", {"team", "season", "type", "metric"}),
    ("自由探索", "冠軍球季比較", "奪冠那季比平常強多少？",
     "每支冠軍隊的奪冠球季，和它其他球季的平均差多少。", {"team", "season", "type", "metric"}),
    ("資料", "球員", "誰是冠軍的關鍵球員？",
     "球員在隊上的逐季變化、出手量 vs 效率、單季逐場數據。", {"team", "season", "type"}),
    ("資料", "數據表", "原始數字與下載",
     "球隊 × 球季的完整數字，可以排序、下載 Excel。", {"team", "season", "type"}),
]
PAGE_INFO = {p[1]: p for p in PAGES}
HOME = "首頁"


def goto(page):
    """切換頁面（按鈕的 on_click 會呼叫這裡）"""
    st.session_state["page"] = page
    try:
        st.query_params["page"] = page      # 網址也跟著變，可以直接分享某一頁
    except Exception:
        pass


if "page" not in st.session_state:          # 第一次打開：看網址有沒有指定頁面
    try:
        q = st.query_params.get("page")
    except Exception:
        q = None
    st.session_state["page"] = q if q in PAGE_INFO else HOME
if st.session_state["page"] not in PAGE_INFO:   # 舊網址或改過名字的頁面，一律回首頁
    st.session_state["page"] = HOME
PAGE = st.session_state["page"]

with st.sidebar:
    st.markdown(f'<div class="logo"><img src="data:image/svg+xml;base64,{LOGO_B64}" alt="ZheN">'
                '<div><div class="logo-name"><span class="z">Z</span><span class="h">he</span>'
                '<span class="z">N</span></div><div class="logo-tag">NBA 冠軍數據分析</div></div></div>',
                unsafe_allow_html=True)
    st.button("首頁", key="nav_home", width="stretch", on_click=goto, args=(HOME,),
              type="primary" if PAGE == HOME else "secondary")
    for grp in dict.fromkeys(p[0] for p in PAGES):     # 依序列出三個群組
        st.markdown(f'<div class="nav-group">{grp}</div>', unsafe_allow_html=True)
        for _, name, *_ in [p for p in PAGES if p[0] == grp]:
            st.button(name, key=f"nav_{name}", width="stretch", on_click=goto, args=(name,),
                      type="primary" if PAGE == name else "secondary")
    st.divider()
    if st.button("重新讀取最新資料", width="stretch",
                 help="網站每 15 分鐘會自動重讀資料庫；剛更新完資料想馬上看到，就按這裡"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"資料更新至：{latest_game_date() or '未知'}\n\n"
               "資料來源：NBA 官方數據（nba_api）→ Supabase 資料庫\n\n★ 代表該隊奪冠的球季")


# =====================================================================
# 頁首：首頁是大標題＋數字卡；其他頁是細長的「麵包屑＋標題＋這頁的問題」
# =====================================================================
if PAGE == HOME:
    st.markdown(f"""
<div class="hero">
  <h1>NBA 冠軍球隊數據分析</h1>
  <div class="hero-sub">2019–2026 八屆冠軍，近二十年的數據軌跡：冠軍的關鍵是什麼？</div>
  <span class="chip">{ALL_SEASONS[0]} – {ALL_SEASONS[-1]}</span>
  <span class="chip">資料更新至 {latest_game_date() or '未知'}</span>
  <span class="chip">資料庫已有 {len(ALL_TEAMS) + len(EXTRA_TEAMS)} / 30 隊</span>
</div>
""", unsafe_allow_html=True)
else:
    grp, name, question, *_ = PAGE_INFO[PAGE]
    st.markdown(f'<div class="pagehead"><div class="crumb">{grp}　／　{name}</div>'
                f'<h2>{name}</h2><div class="pq">{question}</div></div>', unsafe_allow_html=True)


# =====================================================================
# 篩選列：只在「需要」的頁面出現，而且只顯示這頁用得到的條件
# 換頁時條件會記住（存在 st.session_state 的 keep_ 開頭變數）
# =====================================================================
NEED = PAGE_INFO[PAGE][4] if PAGE in PAGE_INFO else set()
keep = st.session_state
teams_sel = keep.get("keep_teams", ALL_TEAMS)
s_from, s_to = keep.get("keep_range", (ALL_SEASONS[0], ALL_SEASONS[-1]))
types_sel = keep.get("keep_types", ["例行賽"])
metric_name = keep.get("keep_metric", list(METRICS)[0])
teams_sel = [a for a in teams_sel if a in ALL_TEAMS + EXTRA_TEAMS] or ALL_TEAMS
types_sel = [x for x in types_sel if x in TYPE_OPTIONS] or ["例行賽"]
metric_name = metric_name if metric_name in METRICS else list(METRICS)[0]
if s_from not in ALL_SEASONS or s_to not in ALL_SEASONS:
    s_from, s_to = ALL_SEASONS[0], ALL_SEASONS[-1]

if NEED:
    try:
        bar = st.container(border=True)
    except TypeError:
        bar = st.container()
    with bar:
        if "team" in NEED:
            teams_sel = pills("球隊", ALL_TEAMS + EXTRA_TEAMS, "w_teams", default=teams_sel, multi=True,
                              format_func=team_label)
            if EXTRA_TEAMS:
                st.caption(f"八支冠軍隊預設勾選；另外已載入 {len(EXTRA_TEAMS)} 隊，點一下就能加入比較"
                           f"（還有 {30 - len(ALL_TEAMS) - len(EXTRA_TEAMS)} 隊每天陸續載入中）。")
        f1, f2, f3 = st.columns([3, 2, 4])
        if "season" in NEED:
            with f1:
                s_from, s_to = st.select_slider("球季範圍", ALL_SEASONS, value=(s_from, s_to), key="w_range")
        if "type" in NEED:
            with f2:
                types_sel = pills("比賽類型", list(TYPE_OPTIONS), "w_types", default=types_sel, multi=True)
        if "metric" in NEED:
            with f3:
                metric_name = pills("比較指標", list(METRICS), "w_metric", default=metric_name)
        if "type" in NEED:
            st.caption("跨球季比較建議只看例行賽：每隊每季約 82 場，比較公平。")
    keep["keep_teams"], keep["keep_range"] = teams_sel, (s_from, s_to)
    keep["keep_types"], keep["keep_metric"] = types_sel, metric_name

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
# 首頁：像 YouTube 首頁一樣的卡片牆，一張卡＝一個研究問題
# =====================================================================
if PAGE == HOME:
    home = team_raw[team_raw["abbreviation"].isin(ALL_TEAMS) & (team_raw["season_type"] == "Regular Season")]
    n_titles = sum(1 for s_, a_ in CHAMP_SET if a_ in ALL_TEAMS and s_ in set(ALL_SEASONS))
    k1, k2, k3, k4 = st.columns(4)
    kpi(k1, "冠軍隊", f"{len(ALL_TEAMS)} 隊", f"另有 {len(EXTRA_TEAMS)} 隊可加入比較")
    kpi(k2, "球季", f"{len(ALL_SEASONS)} 季", f"{ALL_SEASONS[0]} ～ {ALL_SEASONS[-1]}")
    kpi(k3, "比賽場數", f"{int(pd.to_numeric(home['games'], errors='coerce').sum()):,}", "八支冠軍隊的例行賽合計")
    kpi(k4, "奪冠球季", f"{n_titles} 次", f"八隊在這 {len(ALL_SEASONS)} 季拿下的冠軍")
    for grp in dict.fromkeys(p[0] for p in PAGES):
        st.markdown(f'<div class="home-group">{grp}</div>', unsafe_allow_html=True)
        items = [p for p in PAGES if p[0] == grp]
        cols = st.columns(3, gap="medium")
        for i, (_, name, question, desc, _) in enumerate(items):
            n = PAGES.index(PAGE_INFO[name]) + 1
            with cols[i % 3]:
                st.markdown(f'<div class="card"><div class="card-top"><span class="card-num">{n:02d}</span>'
                            f'</div><div class="card-body">'
                            f'<div class="card-title">{name}</div><div class="card-q">{question}</div>'
                            f'<div class="card-desc">{desc}</div></div></div>', unsafe_allow_html=True)
                st.button(f"前往「{name}」", key=f"card_{name}", width="stretch", on_click=goto, args=(name,))
    st.markdown('<div class="footnote">DATA · NBA STATS API　｜　STORAGE · SUPABASE　｜　BUILT WITH STREAMLIT</div>',
                unsafe_allow_html=True)
    st.stop()


# ---------- 0. 冠軍密碼：三個問題 ----------
FACTORS = [  # （名稱, 欄位, 數值越高越好?, 顯示格式）
    ("淨效率", "net_rating", True, "signed"), ("進攻效率", "off_rating", True, "num1"),
    ("防守效率", "def_rating", False, "num1"), ("真實命中率", "ts_pct", True, "pct"),
    ("三分出手比例", "tpar", True, "pct"), ("三分命中率", "fg3_pct", True, "pct"),
    ("失誤率", "tm_tov_pct", False, "pct"), ("進攻籃板率", "oreb_pct", True, "pct"),
    ("防守籃板率", "dreb_pct", True, "pct"), ("助攻失誤比", "ast_to", True, "num2"),
]
STYLE = [("節奏", "pace", True), ("三分出手比例", "tpar", True), ("進攻效率", "off_rating", True),
         ("防守效率", "def_rating", False), ("進攻籃板率", "oreb_pct", True),
         ("助攻失誤比", "ast_to", True), ("失誤少", "tm_tov_pct", False)]
RECENT = "2018-19"   # 2019 年起連續 8 年不同冠軍


def show(v, kind):
    if pd.isna(v):
        return "-"
    if kind == "pct":
        return f"{(v if v > 1 else v * 100):.1f}%"
    return {"signed": f"{v:+.1f}", "num1": f"{v:.1f}", "num2": f"{v:.2f}"}[kind]


def insight(lines):
    st.markdown('<div class="insight">' + "<br>".join(lines) + "</div>", unsafe_allow_html=True)


if PAGE == "冠軍密碼":
    if league.empty:
        st.info("資料庫裡還沒有全聯盟數據，請先執行：python load_to_supabase.py --only league")
    else:
        champ_seasons = set(champs["season"])
        LG = league[(league["season_type"] == "Regular Season") & league["season"].isin(champ_seasons)
                    & (league["season"] >= s_from) & (league["season"] <= s_to)].copy()
        num = ["gp", "w", "fga", "fg3a", "fg3m", "net_rating", "off_rating", "def_rating", "pace",
               "ts_pct", "tm_tov_pct", "oreb_pct", "dreb_pct", "ast_to"]
        for c in num:
            LG[c] = pd.to_numeric(LG[c], errors="coerce")
        LG["tpar"] = LG["fg3a"] / LG["fga"]
        LG["fg3_pct"] = LG["fg3m"] / LG["fg3a"]
        LG["fg3a_pg"] = LG["fg3a"] / LG["gp"]
        LG["w_pct"] = LG["w"] / LG["gp"]
        LG["champion"] = [(s, t) in set(zip(champs["season"], champs["team_id"]))
                          for s, t in zip(LG["season"], LG["team_id"])]
        for _, col, hb, *_ in FACTORS + [(None, "pace", True)]:
            LG[f"rk_{col}"] = LG.groupby("season")[col].rank(ascending=not hb, method="min")
        CH = LG[LG["champion"]].sort_values("season")
        q_seasons = sorted(LG["season"].unique())

        if CH.empty:
            st.info("球季範圍內沒有已完成的冠軍球季，請把上方球季範圍拉大。")
        else:
            st.caption(f"以下三題都用全聯盟 30 隊的例行賽數據（{q_seasons[0]}～{q_seasons[-1]}，"
                       f"共 {len(CH)} 位冠軍）；這一頁只受上方「球季範圍」影響。")

            # ===== Q1 =====
            section("Q1　奪冠的最佳因素是什麼？",
                    "每個點是一位冠軍在該項指標的聯盟排名（1 = 最好）；◆ 是中位數；越集中在左邊，越是冠軍的共同點")
            summ = []
            for label, col, hb, kind in FACTORS:
                r = CH[f"rk_{col}"].dropna()
                summ.append({"label": label, "col": col, "kind": kind,
                             "median": r.median(), "top5": (r <= 5).mean(), "n": len(r)})
            summ = pd.DataFrame(summ).sort_values(["median", "top5"], ascending=[True, False]).reset_index(drop=True)
            n_f = len(summ)
            fig = go.Figure()
            fig.add_vrect(x0=0.5, x1=5.5, fillcolor="rgba(167,139,250,0.08)", line_width=0, layer="below")
            fig.add_annotation(x=3, y=n_f - 0.35, text="聯盟前 5", showarrow=False,
                               font=dict(size=11, color="#6d28d9"))
            for era, name, colr in [(False, f"{q_seasons[0][:4]}～2018 冠軍", "#b3adc2"),
                                    (True, "2019～2026 冠軍", ACCENT)]:
                xs, ys, hov = [], [], []
                for i, f in summ.iterrows():
                    y0 = n_f - 1 - i
                    for j, (_, r) in enumerate(CH.iterrows()):
                        if (r["season"] >= RECENT) != era or pd.isna(r[f"rk_{f['col']}"]):
                            continue
                        xs.append(r[f"rk_{f['col']}"])
                        ys.append(y0 + ((j % 5) - 2) * 0.09)
                        hov.append(f"<b>{r['season']} {team_label(r['abbreviation'])}</b><br>"
                                   f"{f['label']}：第 {int(r['rk_' + f['col']])} 名"
                                   f"（{show(r[f['col']], f['kind'])}）")
                fig.add_trace(go.Scatter(x=xs, y=ys, mode="markers", name=name, text=hov,
                                         hovertemplate="%{text}<extra></extra>",
                                         marker=dict(size=9, color=colr, opacity=0.85,
                                                     line=dict(width=1, color=SURFACE))))
            fig.add_trace(go.Scatter(
                x=summ["median"], y=[n_f - 1 - i for i in range(n_f)], mode="markers", name="中位數",
                marker=dict(symbol="diamond", size=14, color=SURFACE, line=dict(width=2, color="#7c3aed")),
                customdata=summ[["label", "top5"]].values,
                hovertemplate="<b>%{customdata[0]}</b><br>冠軍排名中位數：第 %{x:.0f} 名"
                              "<br>排聯盟前 5 的冠軍：%{customdata[1]:.0%}<extra></extra>"))
            for i, f in summ.iterrows():
                fig.add_annotation(x=31.2, y=n_f - 1 - i, xanchor="left", showarrow=False,
                                   text=f"前5 {f['top5']:.0%}", font=dict(size=11, color=INK_2))
            fig.update_xaxes(title="聯盟排名（1 = 最好，30 = 最差）", range=[0.3, 34.5],
                             tickvals=[1, 5, 10, 15, 20, 25, 30])
            fig.update_yaxes(tickvals=list(range(n_f)), ticktext=list(summ["label"][::-1]),
                             showgrid=False, range=[-0.6, n_f - 0.2])
            st.plotly_chart(style(fig, 90 + 46 * n_f), width="stretch")
            best, worst = summ.iloc[0], summ.iloc[-1]
            insight([
                f"<b>最一致的因素：{best['label']}</b>：{int(best['n'])} 位冠軍的排名中位數是第 {best['median']:.0f} 名，"
                f"{best['top5']:.0%} 排在聯盟前 5。",
                f"<b>第二、三名：</b>{summ.iloc[1]['label']}（中位數第 {summ.iloc[1]['median']:.0f} 名）、"
                f"{summ.iloc[2]['label']}（第 {summ.iloc[2]['median']:.0f} 名）。",
                f"<b>最不一致：{worst['label']}</b>：中位數第 {worst['median']:.0f} 名，代表冠軍在這項上沒有共同特徵。",
            ])
            st.divider()

            # ===== Q2 =====
            section("Q2　三分球時代是否造就了近年的冠軍？",
                    "灰線是聯盟平均，淡紫色帶是 30 隊的最低到最高，★ 是當季冠軍；要看的是冠軍「相對於同季聯盟」的位置")
            q2_opts = {"三分出手比例": ("tpar", "pct"), "三分命中率": ("fg3_pct", "pct"),
                       "場均三分出手": ("fg3a_pg", "num1")}
            q2_name = seg("指標", list(q2_opts), "q2")
            q2_col, q2_kind = q2_opts[q2_name]
            g = LG.groupby("season")
            avg = {"tpar": g["fg3a"].sum() / g["fga"].sum(), "fg3_pct": g["fg3m"].sum() / g["fg3a"].sum(),
                   "fg3a_pg": g["fg3a"].sum() / g["gp"].sum()}[q2_col]
            lo, hi = g[q2_col].min(), g[q2_col].max()
            ch2 = CH.set_index("season")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=hi.index, y=hi.values, mode="lines", line=dict(width=0),
                                     showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=lo.index, y=lo.values, mode="lines", line=dict(width=0),
                                     fill="tonexty", fillcolor="rgba(167,139,250,0.13)",
                                     name="30 隊範圍（最低～最高）", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=avg.index, y=avg.values, mode="lines+markers", name="聯盟平均",
                                     line=dict(color="#a39cb3", width=2), marker=dict(size=5, color="#a39cb3"),
                                     hovertemplate="聯盟平均 %{y:" + (".1%" if q2_kind == "pct" else ".1f") + "}<extra></extra>"))
            fig.add_trace(go.Scatter(
                x=ch2.index, y=ch2[q2_col], mode="markers+text", name="冠軍",
                text=ch2["abbreviation"], textposition="top center", textfont=dict(size=10, color=INK_2),
                marker=dict(symbol="star", size=16, color=ACCENT, line=dict(width=1.2, color=SURFACE)),
                hovertemplate="冠軍 %{text}　%{y:" + (".1%" if q2_kind == "pct" else ".1f") + "}<extra></extra>"))
            fig.update_xaxes(categoryorder="array", categoryarray=q_seasons, type="category")
            fig.update_yaxes(title=q2_name, tickformat=".0%" if q2_kind == "pct" else None)
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(style(fig, 420), width="stretch")

            diff = (ch2[q2_col] - avg.reindex(ch2.index))
            scale = 100 if q2_kind == "pct" else 1
            unit = "百分點" if q2_kind == "pct" else "次"
            fig = go.Figure(go.Bar(
                x=diff.index, y=diff.values * scale,
                marker=dict(color=[ACCENT if v >= 0 else MUTED for v in diff.values]),
                customdata=ch2[["abbreviation"]].values,
                hovertemplate="%{x} 冠軍 %{customdata[0]}<br>比聯盟平均 %{y:+.1f} " + unit + "<extra></extra>"))
            rounded(fig)
            fig.add_hline(y=0, line=dict(color=INK_2, width=1))
            fig.update_xaxes(categoryorder="array", categoryarray=q_seasons, type="category", showgrid=False)
            fig.update_yaxes(title=f"冠軍 − 聯盟平均（{unit}）")
            section(f"冠軍比聯盟平均多或少（{q2_name}）", "紫色＝高於聯盟平均，灰色＝低於聯盟平均")
            st.plotly_chart(style(fig, 260), width="stretch")
            above = int((diff > 0).sum())
            recent = diff[diff.index >= RECENT]
            insight([
                f"<b>聯盟趨勢：</b>{q2_name}從 {q_seasons[0]} 的 {show(avg.iloc[0], q2_kind)} "
                f"變成 {q_seasons[-1]} 的 {show(avg.iloc[-1], q2_kind)}。",
                f"<b>冠軍 vs 聯盟：</b>{len(diff)} 位冠軍中有 {above} 位高於當季聯盟平均"
                + (f"；2019 年後的 {len(recent)} 位中有 {int((recent > 0).sum())} 位。" if len(recent) else "。"),
            ])
            st.divider()

            # ===== Q3 =====
            section("Q3　為什麼這幾年冠軍球隊都不一樣？",
                    "假設一：球隊實力差距變小。用 30 隊的標準差衡量：數值越小，代表強弱越接近")
            q3_opts = {"淨效率": ("net_rating", ".1f"), "勝率": ("w_pct", ".1%")}
            q3_name = seg("用哪個指標衡量實力", list(q3_opts), "q3")
            q3_col, q3_fmt = q3_opts[q3_name]
            sd = LG.groupby("season")[q3_col].std()
            fig = go.Figure()
            for i, s in enumerate(q_seasons):
                if s >= RECENT:
                    fig.add_vrect(x0=i - 0.5, x1=i + 0.5, fillcolor="rgba(167,139,250,0.08)",
                                  line_width=0, layer="below")
            if any(s >= RECENT for s in q_seasons):
                fig.add_annotation(x=max(RECENT, q_seasons[0]), y=1.0, yref="paper", yanchor="bottom",
                                   xanchor="left", showarrow=False, text="2019～2026　連續 8 年不同冠軍",
                                   font=dict(size=11, color="#6d28d9"))
            fig.add_trace(go.Scatter(x=sd.index, y=sd.values, mode="lines+markers", name=f"{q3_name}標準差",
                                     line=dict(color=ACCENT, width=2.4),
                                     marker=dict(size=7, color=ACCENT, line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{x}　標準差 %{y:" + q3_fmt + "}<extra></extra>"))
            fig.update_xaxes(categoryorder="array", categoryarray=q_seasons, type="category")
            fig.update_yaxes(title=f"30 隊{q3_name}的標準差", tickformat=".0%" if "%" in q3_fmt else None)
            fig.update_layout(margin=dict(l=8, r=24, t=28, b=8), showlegend=False)
            st.plotly_chart(style(fig, 360), width="stretch")
            before, after = sd[sd.index < RECENT], sd[sd.index >= RECENT]
            ch_recent = CH[CH["season"] >= RECENT]
            lines = []
            if len(before) and len(after):
                change = after.mean() / before.mean() - 1
                lines.append(f"<b>差距變化：</b>2019 年後平均標準差 {format(after.mean(), q3_fmt)}，"
                             f"之前 {format(before.mean(), q3_fmt)}（{change:+.0%}）。"
                             + ("差距確實變小。" if change < 0 else "差距並沒有變小，這個假設要再想想。"))
            if len(ch_recent):
                k = int((ch_recent["rk_net_rating"] == 1).sum())
                lines.append(f"<b>最強的隊不一定奪冠：</b>2019 年後 {len(ch_recent)} 位冠軍中，"
                             f"只有 {k} 位是例行賽淨效率第 1 名。")
            insight(lines)

            section("假設二：每支冠軍的打法都不同",
                    "近年冠軍在各項打法的聯盟排名；顏色越深代表排名越前面。節奏第 1 = 最快，失誤少第 1 = 失誤最少")
            HS = CH[CH["season"] >= RECENT] if len(ch_recent) else CH.tail(8)
            labels = [f"{s} {team_label(a)}" for s, a in zip(HS["season"], HS["abbreviation"])]
            for _, col, hb in STYLE:   # 節奏、失誤少的排名
                if f"rk_{col}" not in LG:
                    LG[f"rk_{col}"] = LG.groupby("season")[col].rank(ascending=not hb, method="min")
            zr = [[LG.loc[idx, f"rk_{col}"] for _, col, _ in STYLE] for idx in HS.index]
            fig = go.Figure(go.Heatmap(
                z=zr, x=[s[0] for s in STYLE], y=labels, zmin=1, zmax=30,
                colorscale=[[i / (len(PURPLE_RAMP) - 1), c] for i, c in enumerate(PURPLE_RAMP[::-1])],
                xgap=3, ygap=3, showscale=False,
                hovertemplate="%{y}<br>%{x}：聯盟第 %{z:.0f} 名<extra></extra>"))
            for i, lab in enumerate(labels):
                for j, (name, _, _) in enumerate(STYLE):
                    v = zr[i][j]
                    if pd.isna(v):
                        continue
                    fig.add_annotation(x=name, y=lab, showarrow=False, text=f"第 {int(v)}",
                                       font=dict(size=11, color="#ffffff" if v <= 8 else INK))
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=False, side="top")
            st.plotly_chart(style(fig, 90 + 46 * len(labels)), width="stretch")
            st.caption("讀法：如果每一列亮的位置都不同，代表冠軍靠的是不同的打法，沒有單一的致勝公式。")


# ---------- 投籃分布：冠軍從哪裡出手？ ----------
# 區域中文名稱（資料裡的 zone_basic）
ZONE_ZH = {"Restricted Area": "禁區籃下", "In The Paint (Non-RA)": "油漆區", "Mid-Range": "中距離",
           "Left Corner 3": "左底角三分", "Right Corner 3": "右底角三分", "Above the Break 3": "弧頂三分"}
AREA_ZH = {"Left Side(L)": "左", "Left Side Center(LC)": "左翼", "Center(C)": "中",
           "Right Side Center(RC)": "右翼", "Right Side(R)": "右"}
# 五大區：把細分區域併成好比較的大類
ZONE_GROUP = {"Restricted Area": "禁區籃下", "In The Paint (Non-RA)": "油漆區", "Mid-Range": "中距離",
              "Left Corner 3": "底角三分", "Right Corner 3": "底角三分", "Above the Break 3": "弧頂三分"}
GROUP_ORDER = ["禁區籃下", "油漆區", "中距離", "底角三分", "弧頂三分"]
SHOT_START = "2016-17"   # 投籃紀錄從這季開始


def court_shapes():
    """用線條畫出半場：籃框在 (0,0)，單位 0.1 英尺（所以 237.5 = 23.75 英尺的三分線）"""
    import math

    def arc(cx, cy, r, a0, a1, n=48):   # 用很多短線段連成一段圓弧
        pts = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
                cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
        return "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    a = math.degrees(math.acos(220 / 237.5))         # 三分弧和底角直線的交點角度
    yc = 237.5 * math.sin(math.radians(a))
    ln = dict(color="rgba(60,40,100,0.30)", width=1.4)
    return [
        dict(type="rect", x0=-80, y0=-47.5, x1=80, y1=142.5, line=ln),        # 油漆區
        dict(type="line", x0=-30, y0=-7.5, x1=30, y1=-7.5, line=ln),          # 籃板
        dict(type="circle", x0=-7.5, y0=-7.5, x1=7.5, y1=7.5, line=ln),       # 籃框
        dict(type="path", path=arc(0, 142.5, 60, 0, 180), line=ln),           # 罰球圈
        dict(type="path", path=arc(0, 0, 40, 0, 180), line=ln),               # 禁區弧（合理衝撞區）
        dict(type="line", x0=-220, y0=-47.5, x1=-220, y1=yc, line=ln),        # 底角三分線
        dict(type="line", x0=220, y0=-47.5, x1=220, y1=yc, line=ln),
        dict(type="path", path=arc(0, 0, 237.5, a, 180 - a, 80), line=ln),    # 三分弧
        dict(type="line", x0=-250, y0=-47.5, x1=250, y1=-47.5, line=ln),      # 底線
    ]


def zone_table(df):
    """把出手資料整理成「每個細分區域一列」：出手、命中、命中率、佔比、位置"""
    d = df[df["zone_basic"].isin(ZONE_ZH)].copy()
    if d.empty:
        return d
    d["fga"] = pd.to_numeric(d["fga"], errors="coerce")
    d["fgm"] = pd.to_numeric(d["fgm"], errors="coerce")
    g = d.groupby(["zone_basic", "zone_area"], as_index=False)[["fga", "fgm"]].sum()
    if "x" in d.columns:
        pos = d.groupby(["zone_basic", "zone_area"], as_index=False)[["x", "y"]].mean()
        g = g.merge(pos, on=["zone_basic", "zone_area"])
    g["fg_pct"] = g["fgm"] / g["fga"].replace(0, pd.NA)
    g["share"] = g["fga"] / g["fga"].sum()
    g["value"] = g["zone_basic"].map(lambda z: 3 if "3" in z else 2)   # 三分區投進得 3 分
    g["pps"] = g["fg_pct"] * g["value"]                                  # 每次出手平均得分
    for c in ["fg_pct", "share", "pps"]:
        g[c] = pd.to_numeric(g[c], errors="coerce").astype(float)
    g["name"] = g["zone_basic"].map(ZONE_ZH) + g["zone_area"].map(lambda a: f"（{AREA_ZH.get(a, a)}）")
    g["group"] = g["zone_basic"].map(ZONE_GROUP)
    return g


def group_table(z):
    """細分區域 → 五大區"""
    g = z.groupby("group", as_index=False)[["fga", "fgm"]].sum()
    pts = (z["fgm"] * z["value"]).groupby(z["group"]).sum()
    g["share"] = g["fga"] / g["fga"].sum()
    g["fg_pct"] = g["fgm"] / g["fga"].replace(0, pd.NA)
    g["pps"] = g["group"].map(pts) / g["fga"].replace(0, pd.NA)
    for c in ["share", "fg_pct", "pps"]:
        g[c] = pd.to_numeric(g[c], errors="coerce").astype(float)
    return g.set_index("group").reindex(GROUP_ORDER)


def shots_to_zone_rows(s):
    """逐筆出手 → 每區的出手數、命中數與平均座標"""
    s = s.assign(fga=1, fgm=s["made"].astype(bool).astype(int),
                 x=pd.to_numeric(s["loc_x"], errors="coerce"), y=pd.to_numeric(s["loc_y"], errors="coerce"))
    return s[["zone_basic", "zone_area", "fga", "fgm", "x", "y"]]


if PAGE == "投籃分布":
    section("冠軍從哪裡出手？",
            "問題：奪冠那一季的出手位置，和聯盟平均、和自己其他球季有什麼不同？　"
            "假設：冠軍會把出手集中在「禁區籃下＋三分」這兩個每次出手得分最高的地方，少投中距離")
    status = table_status("shots")
    if status != "ok":
        st.info("尚未載入資料，請執行 python load_extra.py --only shots"
                + ("（資料表還不存在：請先到 Supabase SQL Editor 執行 schema_extra.sql）" if status == "missing" else ""))
    else:
        shot_seasons = [s for s in ALL_SEASONS if s >= SHOT_START][::-1]
        c1, c2, c3 = st.columns([3, 2, 2])
        with c1:
            sh_team = pills("球隊", ALL_TEAMS, "sh_team", default=ALL_TEAMS[0], format_func=team_label)
        sh_tid = int(team_raw[team_raw["abbreviation"] == sh_team]["team_id"].iloc[0])
        champ_s = [s for s in shot_seasons if (s, sh_team) in CHAMP_SET]
        with c2:
            sh_season = st.selectbox(
                "球季", shot_seasons, key=f"sh_season_{sh_team}",
                index=shot_seasons.index(champ_s[0]) if champ_s else 0,
                format_func=lambda s: s + ("　★ 奪冠" if (s, sh_team) in CHAMP_SET else ""))
        with c3:
            sh_type = TYPE_OPTIONS[seg("比賽類型", ["例行賽", "季後賽"], "sh_type")]
        c4, c5 = st.columns([3, 4])
        with c4:
            vs = seg("和誰比較", ["聯盟平均", "另一季"], "sh_vs")
        with c5:
            view = seg("球場圖顯示", ["分區命中率", "每一次出手"], "sh_view")

        shots_a = load_shots(sh_tid, sh_season, sh_type)
        # 球員篩選：全隊，或這季在隊上出手的某一位球員（依出手數排序）
        sh_pid, sh_pname = None, None
        if not shots_a.empty and "player_id" in shots_a.columns:
            cnt = (shots_a.groupby(["player_id", "player_name"]).size()
                   .sort_values(ascending=False).reset_index(name="n"))
            opts = [None] + cnt["player_id"].tolist()
            names = dict(zip(cnt["player_id"], cnt["player_name"]))
            nums = dict(zip(cnt["player_id"], cnt["n"]))
            sh_pid = st.selectbox(
                "球員（預設全隊；選一位球員就只看他的出手）", opts,
                key=f"sh_player_{sh_team}_{sh_season}_{sh_type}",
                format_func=lambda p: "全隊" if p is None else f"{names[p]}（{nums[p]:,} 次出手）")
            if sh_pid is not None:
                sh_pname = names[sh_pid]
                shots_a = shots_a[shots_a["player_id"] == sh_pid]
        who = sh_pname or TEAM_ZH.get(sh_team, sh_team)
        if shots_a.empty:
            st.info(f"{team_label(sh_team)} {sh_season} {'季後賽' if sh_type == 'Playoffs' else '例行賽'}"
                    "沒有投籃紀錄（可能那季沒打進季後賽，或這一季還沒載入）。")
        else:
            za = zone_table(shots_to_zone_rows(shots_a))
            # 比較對象 B
            if vs == "聯盟平均":
                zl = load_zone_league()
                zb_raw = (zl[(zl["season"] == sh_season) & (zl["season_type"] == sh_type)]
                          if not zl.empty else pd.DataFrame())
                b_label = f"{sh_season} 聯盟平均"
                zb = zone_table(zb_raw) if not zb_raw.empty else pd.DataFrame()
            else:
                prev = [s for s in shot_seasons if s < sh_season]
                others = [s for s in shot_seasons if s != sh_season]
                sh_season_b = st.selectbox(
                    "比較球季（預設是前一季，看看奪冠前後的改變；選了球員就比他自己的另一季）", others,
                    index=others.index(prev[0]) if prev else 0, key=f"sh_b_{sh_team}_{sh_season}",
                    format_func=lambda s: s + ("　★ 奪冠" if (s, sh_team) in CHAMP_SET else ""))
                shots_b = load_shots(sh_tid, sh_season_b, sh_type)
                if sh_pid is not None and not shots_b.empty:
                    shots_b = shots_b[shots_b["player_id"] == sh_pid]
                    if shots_b.empty:
                        st.caption(f"{sh_pname} 在 {sh_season_b} 沒有替{TEAM_ZH.get(sh_team, sh_team)}出手的紀錄，"
                                   "請換一季，或改成和聯盟平均比較。")
                b_label = f"{sh_season_b} {who}" + ("★" if (sh_season_b, sh_team) in CHAMP_SET else "")
                zb = zone_table(shots_to_zone_rows(shots_b)) if not shots_b.empty else pd.DataFrame()
            a_label = f"{sh_season} {who}" + ("★" if (sh_season, sh_team) in CHAMP_SET else "")
            color = TEAM_COLORS.get(sh_team, ACCENT)

            # ---- 球場圖 ----
            def court_axes(fig, height=500):
                """把圖變成半場球場：畫線、隱藏座標軸、長寬等比例"""
                fig.update_layout(shapes=court_shapes())
                fig.update_xaxes(range=[-255, 255], visible=False, fixedrange=True, constrain="domain")
                fig.update_yaxes(range=[-55, 330], visible=False, fixedrange=True, constrain="domain",
                                 scaleanchor="x", scaleratio=1)
                fig = style(fig, height)
                fig.update_layout(legend=dict(y=-0.02))
                return fig

            def points_fig(df):
                """每一次出手畫成一個點：投進＝球隊色圓點、沒進＝灰色 ×"""
                fig = go.Figure()
                made = df["made"].astype(bool)
                ms = 5 if sh_pid is None else 8   # 單一球員點比較少，畫大一點
                for ok, name, mk in [(False, "沒進", dict(symbol="x", size=ms, color="#9a93a9", opacity=0.6)),
                                     (True, "投進", dict(size=ms, color=color, opacity=0.75))]:
                    d = df[made == ok]
                    fig.add_trace(go.Scatter(
                        x=d["loc_x"], y=d["loc_y"], mode="markers", name=name, marker=mk,
                        customdata=d[["player_name", "shot_distance"]].values,
                        hovertemplate="%{customdata[0]}　%{customdata[1]} 英尺<extra>" + name + "</extra>"))
                return court_axes(fig)

            def shot_summary(df):
                """圖上方的一行摘要：出手數、命中率、三分出手比例"""
                n = len(df)
                fg = df["made"].astype(bool).mean() if n else float("nan")
                three = df["zone_basic"].isin(["Left Corner 3", "Right Corner 3", "Above the Break 3"]).mean()
                return f"出手 {n:,} 次｜命中率 {fg:.1%}｜三分出手佔 {three:.0%}"

            # 「另一季」＋「每一次出手」：兩季的球場圖左右並排，一眼比較
            two_up = view == "每一次出手" and vs == "另一季" and not zb.empty
            if two_up:
                ca, cb = st.columns(2, gap="large")
                for c_, df_, lab in [(ca, shots_a, a_label), (cb, shots_b, b_label)]:
                    with c_:
                        section(f"{lab} 出手位置", shot_summary(df_))
                        st.plotly_chart(points_fig(df_), width="stretch")
                st.caption("兩張圖用同一套顏色和比例：彩色＝投進、灰色 × ＝沒進。"
                           "比一比哪一區的點變多變少（出手選擇的改變）、哪一區彩色點變多（命中區的改變）。"
                           "想換比較的球季，改上方的「球季」和「比較球季」。")
                left, right = None, st.container()   # 下面的五大區對照改成整排寬
            else:
                left, right = st.columns([5, 4], gap="large")
            if not two_up:   # 一般情況：左邊一張球場圖
                with left:
                    fig = go.Figure()
                    if view == "每一次出手":
                        fig = points_fig(shots_a)
                        sub = f"每個點是一次出手：彩色＝投進、灰色 × ＝沒進。{shot_summary(shots_a)}"
                        if vs == "另一季":
                            sub += "（比較球季沒有資料，所以只顯示一張）"
                    else:
                        zm = za.copy()
                        if not zb.empty:
                            zm = zm.merge(zb[["zone_basic", "zone_area", "fg_pct", "share"]],
                                          on=["zone_basic", "zone_area"], how="left", suffixes=("", "_b"))
                        else:
                            zm["fg_pct_b"], zm["share_b"] = float("nan"), float("nan")
                        zm["diff"] = (pd.to_numeric(zm["fg_pct"] - zm["fg_pct_b"], errors="coerce") * 100)
                        size = 16 + 46 * (zm["share"] / zm["share"].max()) ** 0.5
                        fig.add_trace(go.Scatter(
                            x=zm["x"], y=zm["y"], mode="markers+text",
                            text=[f"{v:.0%}" for v in zm["fg_pct"]], textfont=dict(size=11, color=INK),
                            marker=dict(size=size, color=zm["diff"].fillna(0), cmin=-8, cmax=8,
                                        colorscale=[[0, "#3d74c9"], [0.5, "#ece9f2"], [1, "#7c3aed"]],
                                        line=dict(width=1, color="rgba(26,20,38,0.25)"),
                                        colorbar=dict(title=dict(text="命中率差<br>（百分點）", font=dict(size=11, color=INK_2)),
                                                      thickness=10, outlinewidth=0, len=0.6,
                                                      tickfont=dict(color=INK_2))),
                            customdata=zm[["name", "fga", "share", "fg_pct", "fg_pct_b", "diff", "pps"]].values,
                            hovertemplate="<b>%{customdata[0]}</b><br>出手 %{customdata[1]:,} 次（佔 %{customdata[2]:.1%}）"
                                          "<br>命中率 %{customdata[3]:.1%}｜" + b_label + " %{customdata[4]:.1%}"
                                          "<br>差距 %{customdata[5]:+.1f} 百分點｜每次出手 %{customdata[6]:.2f} 分"
                                          "<extra></extra>", showlegend=False))
                        sub = f"圈越大＝出手越多；圈內數字是命中率；紫色＝比「{b_label}」準、藍色＝比較不準"
                        fig = court_axes(fig)
                    section(f"{a_label} 出手位置", sub)
                    st.plotly_chart(fig, width="stretch")

            # ---- 五大區對照 ----
            with right:
                ga = group_table(za)
                gb = group_table(zb) if not zb.empty else None
                section("五大區出手佔比", f"每 100 次出手有幾次在這一區；彩色＝{a_label}（球隊色）、灰色＝{b_label}")
                fig = go.Figure()
                if gb is not None:
                    fig.add_trace(go.Bar(y=GROUP_ORDER, x=gb["share"], orientation="h", name=b_label,
                                         marker=dict(color="#c9c3d6"),
                                         hovertemplate="%{y}　%{x:.1%}<extra>" + b_label + "</extra>"))
                fig.add_trace(go.Bar(y=GROUP_ORDER, x=ga["share"], orientation="h", name=a_label,
                                     marker=dict(color=color), text=[fmt(v, ".0%") for v in ga["share"]],
                                     textposition="outside", cliponaxis=False, textfont=dict(color=INK),
                                     hovertemplate="%{y}　%{x:.1%}<extra>" + a_label + "</extra>"))
                rounded(fig)
                fig.update_yaxes(autorange="reversed", showgrid=False)
                fig.update_xaxes(showticklabels=False, showgrid=False)
                fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
                st.plotly_chart(style(fig, 330), width="stretch")
                rows = []
                for grp in GROUP_ORDER:
                    ra = ga.loc[grp]
                    rb = gb.loc[grp] if gb is not None else None
                    dif = (ra["share"] - rb["share"]) * 100 if rb is not None else float("nan")
                    rows.append({"區域": grp, "出手佔比": fmt(ra["share"], ".1%"),
                                 "對照": fmt(rb["share"], ".1%") if rb is not None else "-",
                                 "佔比差": "-" if pd.isna(dif) else f"{dif:+.1f}",
                                 "命中率": fmt(ra["fg_pct"], ".1%"),
                                 "每次出手得分": fmt(ra["pps"], ".2f")})
                nice_table(pd.DataFrame(rows), num_cols=("出手佔比", "對照", "佔比差", "命中率", "每次出手得分"),
                           signed_cols=("佔比差",))

            # ---- 自動讀法 ----
            lines = []
            if gb is not None:
                mid = (ga.loc["中距離", "share"] - gb.loc["中距離", "share"]) * 100
                three = ((ga.loc["底角三分", "share"] + ga.loc["弧頂三分", "share"])
                         - (gb.loc["底角三分", "share"] + gb.loc["弧頂三分", "share"])) * 100
                rim = (ga.loc["禁區籃下", "share"] - gb.loc["禁區籃下", "share"]) * 100
                lines.append(f"<b>出手選擇：</b>{who}和{b_label}相比，中距離 {mid:+.1f}、三分 {three:+.1f}、"
                             f"禁區籃下 {rim:+.1f} 個百分點。"
                             + ("中距離比較少、籃下或三分比較多，符合假設。" if mid < 0 and (three > 0 or rim > 0)
                                else "沒有明顯「少投中距離」，可能靠別的方式得分（例如中距離投得特別準）。"))
            if not zb.empty:
                zz = za.merge(zb[["zone_basic", "zone_area", "fg_pct"]], on=["zone_basic", "zone_area"],
                              suffixes=("", "_b"))
                zz = zz[zz["share"] >= 0.03]
                zz["d"] = zz["fg_pct"] - zz["fg_pct_b"]
                if not zz.empty:
                    best, worst = zz.loc[zz["d"].idxmax()], zz.loc[zz["d"].idxmin()]
                    lines.append(f"<b>最大優勢區：</b>{best['name']}，命中率 {best['fg_pct']:.1%}，"
                                 f"比對照高 {best['d'] * 100:+.1f} 個百分點；"
                                 f"<b>最弱區：</b>{worst['name']}（{worst['d'] * 100:+.1f}）。")
            lines.append(f"<b>為什麼看「每次出手得分」：</b>中距離就算投 45%，每次也只值 0.9 分；"
                         f"三分只要投 35% 就值 1.05 分。這就是球隊捨棄中距離的數學理由。")
            insight(lines)

            # ---- 逐季趨勢（需要 shot_zone_team 檢視表）----
            st.divider()
            section(f"{sh_pname or team_label(sh_team)} 每季出手選擇 vs 聯盟",
                    ("實線是球員（只含他在 8 支冠軍隊的球季）" if sh_pid is not None else "實線是球隊")
                    + "、灰線是聯盟平均，★ 是奪冠球季；看冠軍那一季是不是「特別偏離」聯盟或自己的習慣")
            trend_grp = seg("區域", ["中距離", "三分（底角＋弧頂）", "禁區籃下"], "sh_trend")
            zt = load_zone_team(sh_tid) if sh_pid is None else load_zone_player(sh_pid)
            zl = load_zone_league()
            view_file = "shot_zone_team" if sh_pid is None else "shot_zone_player"

            def share_by_season(df):
                d = df[(df["season_type"] == sh_type) & df["zone_basic"].isin(ZONE_ZH)].copy()
                if d.empty:
                    return pd.Series(dtype=float)
                d["fga"] = pd.to_numeric(d["fga"], errors="coerce")
                d["group"] = d["zone_basic"].map(ZONE_GROUP)
                tot = d.groupby("season")["fga"].sum()
                want = {"中距離": ["中距離"], "禁區籃下": ["禁區籃下"]}.get(trend_grp, ["底角三分", "弧頂三分"])
                return d[d["group"].isin(want)].groupby("season")["fga"].sum() / tot

            if zt is None:
                st.info("這張逐季趨勢圖需要一個彙總檢視表（一次讀 10 季的逐筆出手太慢）。"
                        f"請到 Supabase SQL Editor 執行 docs/sql/2026-10-28_{view_file}.sql，"
                        "執行後按左側「重新讀取最新資料」。")
                if view_file in VIEW_ERRORS:
                    st.caption(f"讀取 {view_file} 的錯誤訊息（截圖給助教看）：{VIEW_ERRORS[view_file]}")
            else:
                ts_team = share_by_season(zt) if not zt.empty else pd.Series(dtype=float)
                ts_lg = share_by_season(zl) if not zl.empty else pd.Series(dtype=float)
                fig = go.Figure()
                if not ts_lg.empty:
                    fig.add_trace(go.Scatter(x=ts_lg.index, y=ts_lg.values, mode="lines+markers", name="聯盟平均",
                                             line=dict(color="#8f889f", width=1.8, dash="dot"),
                                             marker=dict(size=5, color="#8f889f"),
                                             hovertemplate="聯盟 %{y:.1%}<extra></extra>"))
                if not ts_team.empty:
                    fig.add_trace(go.Scatter(x=ts_team.index, y=ts_team.values, mode="lines+markers",
                                             name=sh_pname or team_label(sh_team), line=dict(color=color, width=2.6),
                                             marker=dict(size=7, color=color, line=dict(width=1.5, color=SURFACE)),
                                             hovertemplate=who + " %{y:.1%}<extra></extra>"))
                    # 奪冠球季：球員可能換過隊，所以用「那一季他效力的球隊」判斷
                    abbr_of = dict(zip(team_raw["team_id"], team_raw["abbreviation"]))
                    team_by_season = (zt.groupby("season")["team_id"].first().map(abbr_of)
                                      if sh_pid is not None else pd.Series(dtype=object))
                    cs = [s for s in ts_team.index
                          if (s, team_by_season.get(s, sh_team) if sh_pid is not None else sh_team) in CHAMP_SET]
                    if cs:
                        fig.add_trace(go.Scatter(x=cs, y=ts_team.reindex(cs).values, mode="markers", showlegend=False,
                                                 hoverinfo="skip", marker=dict(symbol="star", size=20, color=color,
                                                                               line=dict(width=1.5, color=SURFACE))))
                    last = ts_team.index[-1]
                    fig.add_annotation(x=last, y=ts_team.iloc[-1], text=sh_pname or sh_team, showarrow=False, xanchor="left",
                                       xshift=10, font=dict(size=11, color=INK_2))
                if fig.data:
                    fig.update_xaxes(type="category", categoryorder="array",
                                     categoryarray=[s for s in ALL_SEASONS if s >= SHOT_START])
                    fig.update_yaxes(title=f"{trend_grp}出手佔比", tickformat=".0%")
                    fig.update_layout(hovermode="x unified")
                    st.plotly_chart(style(fig, 360), width="stretch")
                else:
                    st.info("檢視表已建立，但還沒有這個選擇的資料。")

            # ---- 多季對照：一眼看出出手選擇與命中區的變化 ----
            st.divider()
            section(f"{who} 多季對照：出手選擇與命中區有沒有改變？",
                    "問題：奪冠那幾季的出手位置和準度，跟其他球季比起來有沒有明顯轉變？　"
                    "讀法：橫著看一列（同一區）顏色有沒有變深變淺；★ 是奪冠球季")
            if zt is None or zt.empty:
                st.info(f"多季對照需要彙總檢視表：請到 Supabase SQL Editor 執行 docs/sql/2026-10-28_{view_file}.sql。")
                if view_file in VIEW_ERRORS:
                    st.caption(f"錯誤訊息：{VIEW_ERRORS[view_file]}")
            else:
                m1, m2 = st.columns([4, 3])
                with m1:
                    mv_metric = seg("顏色代表", ["出手佔比", "命中率", "命中率 vs 聯盟"], "mv_metric")
                with m2:
                    mv_level = seg("區域分法", ["五大區", "細分區域"], "mv_level")

                def per_season(df):
                    """每季 × 每區：出手、命中、佔比（該季出手中佔幾成）、命中率"""
                    d = df[(df["season_type"] == sh_type) & df["zone_basic"].isin(ZONE_ZH)].copy()
                    if d.empty:
                        return pd.DataFrame()
                    for c in ["fga", "fgm"]:
                        d[c] = pd.to_numeric(d[c], errors="coerce")
                    d["key"] = (d["zone_basic"].map(ZONE_GROUP) if mv_level == "五大區" else
                                d["zone_basic"].map(ZONE_ZH) + d["zone_area"].map(lambda a: f"（{AREA_ZH.get(a, a)}）"))
                    g = d.groupby(["season", "key"], as_index=False)[["fga", "fgm"]].sum()
                    g["share"] = g["fga"] / g.groupby("season")["fga"].transform("sum")
                    g["fg_pct"] = (g["fgm"] / g["fga"].where(g["fga"] > 0)).astype(float)
                    return g

                ms = per_season(zt)
                ml = per_season(zl) if not zl.empty else pd.DataFrame()
                if ms.empty:
                    st.info("這個選擇在這種比賽類型沒有多季資料。")
                else:
                    if not ml.empty:
                        ms = ms.merge(ml[["season", "key", "fg_pct"]].rename(columns={"fg_pct": "lg_pct"}),
                                      on=["season", "key"], how="left")
                    else:
                        ms["lg_pct"] = float("nan")
                    ms["vs_lg"] = (ms["fg_pct"] - ms["lg_pct"]) * 100
                    # 出手太少的格子命中率不可靠（例如 3 投 2 中 = 67%），命中率類指標就不上色
                    few = ms["fga"] < (10 if sh_pid is not None else 30)
                    col, ffmt = {"出手佔比": ("share", ".0%"), "命中率": ("fg_pct", ".0%"),
                                 "命中率 vs 聯盟": ("vs_lg", "+.1f")}[mv_metric]
                    if col != "share":
                        ms.loc[few, col] = float("nan")
                    seasons_mv = sorted(ms["season"].unique())
                    keys = [k for k in (GROUP_ORDER if mv_level == "五大區" else
                                        sorted(ms["key"].unique(), key=lambda k: (
                                            GROUP_ORDER.index(ZONE_GROUP[next(z for z, n in ZONE_ZH.items()
                                                                              if k.startswith(n))]), k)))
                            if k in set(ms["key"])]
                    pv = ms.pivot(index="key", columns="season", values=col).reindex(index=keys, columns=seasons_mv)
                    fga_pv = ms.pivot(index="key", columns="season", values="fga").reindex(index=keys, columns=seasons_mv)

                    # 每一季他效力的球隊（球員可能換隊），用來判斷是不是奪冠球季
                    abbr_of = dict(zip(team_raw["team_id"], team_raw["abbreviation"]))
                    tm = zt[zt["season_type"] == sh_type].groupby("season")["team_id"].first().map(abbr_of)
                    xlab = [s + (" ★" if (s, tm.get(s, sh_team)) in CHAMP_SET else "") for s in seasons_mv]

                    if col == "vs_lg":
                        scale, zmin, zmax = [[0, "#3d74c9"], [0.5, "#ece9f2"], [1, "#7c3aed"]], -8, 8
                    else:
                        scale = [[i / (len(PURPLE_RAMP) - 1), c] for i, c in enumerate(PURPLE_RAMP)]
                        zmin, zmax = None, None
                    z = pv.values.astype(float)
                    fig = go.Figure(go.Heatmap(
                        z=z, x=xlab, y=keys, colorscale=scale, zmin=zmin, zmax=zmax, xgap=3, ygap=3,
                        customdata=fga_pv.values,
                        colorbar=dict(thickness=10, outlinewidth=0, len=0.8, tickfont=dict(color=INK_2),
                                      tickformat=".0%" if col != "vs_lg" else None),
                        hovertemplate="%{y}　%{x}<br>" + mv_metric + "：%{z:" + ffmt + "}"
                                      + ("（百分點）" if col == "vs_lg" else "")
                                      + "<br>出手 %{customdata:,.0f} 次<extra></extra>"))
                    lo = pd.Series(z.ravel()).min()
                    hi = pd.Series(z.ravel()).max()
                    for i, k in enumerate(keys):
                        for j, s in enumerate(xlab):
                            v = z[i, j]
                            if pd.isna(v):
                                continue
                            bright = (abs(v) > 5) if col == "vs_lg" else ((v - lo) / ((hi - lo) or 1) > 0.6)
                            txt = f"{v:+.0f}" if col == "vs_lg" else f"{v:.0%}"
                            fig.add_annotation(x=s, y=k, text=txt, showarrow=False,
                                               font=dict(size=10.5, color="#ffffff" if bright else INK))
                    fig.update_yaxes(autorange="reversed", showgrid=False)
                    fig.update_xaxes(showgrid=False, side="top", type="category")
                    st.plotly_chart(style(fig, 90 + 40 * len(keys)), width="stretch")
                    st.caption("空白格＝那季沒有出手，或出手太少（命中率不可靠）所以不上色。"
                               "「命中率 vs 聯盟」的數字是百分點：+5 代表比同季聯盟平均準 5 個百分點。")

                    # 自動讀法：變化最大的區域
                    if len(seasons_mv) >= 2:
                        sh_pv = ms.pivot(index="key", columns="season", values="share").reindex(columns=seasons_mv)
                        pct_pv = ms.assign(fg=ms["fg_pct"].where(~few)).pivot(index="key", columns="season",
                                                                               values="fg").reindex(columns=seasons_mv)
                        rng = (sh_pv.max(axis=1) - sh_pv.min(axis=1)).dropna()
                        lines = []
                        if not rng.empty:
                            k = rng.idxmax()
                            lines.append(f"<b>出手選擇變化最大：</b>{k}，佔比在 {sh_pv.loc[k].idxmin()} 最低"
                                         f"（{sh_pv.loc[k].min():.0%}）、{sh_pv.loc[k].idxmax()} 最高"
                                         f"（{sh_pv.loc[k].max():.0%}）。")
                        prng = (pct_pv.max(axis=1) - pct_pv.min(axis=1)).dropna()
                        if not prng.empty:
                            k = prng.idxmax()
                            lines.append(f"<b>命中率起伏最大：</b>{k}，從 {pct_pv.loc[k].min():.0%}"
                                         f"（{pct_pv.loc[k].idxmin()}）到 {pct_pv.loc[k].max():.0%}"
                                         f"（{pct_pv.loc[k].idxmax()}）。")
                        lines.append("接著問「為什麼」：那一季換了教練、隊友，還是受傷？這就是從數據走到故事的一步。")
                        insight(lines)

                    # 小球場並排：選幾季放在一起看
                    champ_cols = [s for s, lab in zip(seasons_mv, xlab) if "★" in lab]
                    default_pick = (champ_cols + [s for s in seasons_mv if s not in champ_cols])[:3]
                    default_pick = sorted(default_pick)
                    pick = pills("並排比較的球季（最多 4 季）", seasons_mv, "mv_pick", default=default_pick,
                                 multi=True, format_func=lambda s: s + (" ★" if s in champ_cols else ""))
                    pick = sorted(pick)[:4]   # 不管點選順序，一律由舊到新排列
                    if pick:
                        # 各區在球場上的位置：用全隊檢視表的平均座標；沒有就用大概位置
                        pos_src = load_zone_team(sh_tid)
                        if pos_src is not None and not pos_src.empty and "avg_x" in pos_src.columns:
                            ps = pos_src.assign(w=pd.to_numeric(pos_src["fga"], errors="coerce"),
                                                ax=pd.to_numeric(pos_src["avg_x"], errors="coerce"),
                                                ay=pd.to_numeric(pos_src["avg_y"], errors="coerce"))
                            ps["wx"], ps["wy"] = ps["ax"] * ps["w"], ps["ay"] * ps["w"]
                            pg = ps.groupby(["zone_basic", "zone_area"])[["wx", "wy", "w"]].sum()
                            POS = {k: (r["wx"] / r["w"], r["wy"] / r["w"]) for k, r in pg.iterrows() if r["w"]}
                        else:
                            POS = {}
                        fine = zt[(zt["season_type"] == sh_type) & zt["zone_basic"].isin(ZONE_ZH)].copy()
                        for c in ["fga", "fgm"]:
                            fine[c] = pd.to_numeric(fine[c], errors="coerce")
                        cols = st.columns(len(pick))
                        for c_, s in zip(cols, pick):
                            f = (fine[fine["season"] == s].groupby(["zone_basic", "zone_area"], as_index=False)
                                 [["fga", "fgm"]].sum())
                            f = f[[(a, b) in POS for a, b in zip(f["zone_basic"], f["zone_area"])]]
                            if f.empty:
                                c_.caption(f"{s}：沒有資料")
                                continue
                            f["x"] = [POS[(a, b)][0] for a, b in zip(f["zone_basic"], f["zone_area"])]
                            f["y"] = [POS[(a, b)][1] for a, b in zip(f["zone_basic"], f["zone_area"])]
                            f["share"] = f["fga"] / f["fga"].sum()
                            f["fg"] = (f["fgm"] / f["fga"].where(f["fga"] > 0)).astype(float)
                            lgs = zl[(zl["season"] == s) & (zl["season_type"] == sh_type)] if not zl.empty else zl
                            if not lgs.empty:
                                lz = zone_table(lgs)[["zone_basic", "zone_area", "fg_pct"]]
                                f = f.merge(lz, on=["zone_basic", "zone_area"], how="left")
                            else:
                                f["fg_pct"] = float("nan")
                            f["d"] = ((f["fg"] - f["fg_pct"]) * 100).astype(float)
                            fig = go.Figure(go.Scatter(
                                x=f["x"], y=f["y"], mode="markers",
                                marker=dict(size=8 + 34 * (f["share"] / 0.35).clip(upper=1) ** 0.5,
                                            color=f["d"].fillna(0), cmin=-8, cmax=8,
                                            colorscale=[[0, "#3d74c9"], [0.5, "#ece9f2"], [1, "#7c3aed"]],
                                            line=dict(width=1, color="rgba(26,20,38,0.25)")),
                                customdata=f[["zone_basic", "fga", "share", "fg", "d"]].values,
                                hovertemplate="%{customdata[0]}<br>出手 %{customdata[1]:,.0f}（%{customdata[2]:.0%}）"
                                              "<br>命中率 %{customdata[3]:.1%}（vs 聯盟 %{customdata[4]:+.1f}）"
                                              "<extra></extra>", showlegend=False))
                            fig.update_layout(shapes=court_shapes())
                            fig.update_xaxes(range=[-255, 255], visible=False, fixedrange=True, constrain="domain")
                            fig.update_yaxes(range=[-55, 330], visible=False, fixedrange=True, constrain="domain",
                                             scaleanchor="x", scaleratio=1)   # 每張小球場比例、大小都一樣
                            star = " ★" if s in champ_cols else ""
                            c_.markdown(f'<div class="section-sub" style="margin-left:0;text-align:center">'
                                        f'<b style="color:#1a1426">{s}{star}</b>　出手 {int(f["fga"].sum()):,}</div>',
                                        unsafe_allow_html=True)
                            fig = style(fig, 280)
                            fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
                            c_.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                        st.caption("每個小球場同一套規則：圈越大＝那季在這區出手越多；紫色＝比同季聯盟準、藍色＝比較不準。"
                                   "並排看，圈「變大變小」就是出手選擇的改變，「變紫變藍」就是命中區的改變。")


# ---------- 戰術使用：冠軍靠什麼戰術得分？ ----------
PLAY_ZH = {"Isolation": "單打", "Transition": "快攻轉換", "PRBallHandler": "擋拆持球者",
           "PRRollman": "擋拆順下", "Postup": "低位背框", "Spotup": "定點投籃", "Handoff": "手遞手",
           "Cut": "空手切入", "OffScreen": "繞掩護", "OffRebound": "進攻籃板補進", "Misc": "其他"}
PLAY_ORDER = list(PLAY_ZH)


@st.cache_data(ttl=3600, show_spinner="讀取戰術數據中…")
def load_playtypes_team():
    """全聯盟 30 隊每季的 Synergy 戰術數據（約一萬多列，一頁一頁讀）"""
    try:
        return fetch_all("playtypes_team", ["season", "season_type", "team_id", "play_type", "type_grouping"])
    except Exception:
        return pd.DataFrame()


def prep_playtypes(pt):
    """整理數字欄位，並算出每支球隊在「同一季、同一戰術」的聯盟排名（1 = 最好）"""
    pt = pt.copy()
    for c in ["gp", "poss", "poss_pct", "ppp", "pts"]:
        pt[c] = pd.to_numeric(pt[c], errors="coerce")
    if pt["poss_pct"].max() > 1.5:          # 有些版本存成 0～100，統一成 0～1
        pt["poss_pct"] = pt["poss_pct"] / 100
    pt["side"] = pt["type_grouping"].str.lower()
    keys = ["season", "season_type", "side", "play_type"]
    off = pt["side"] == "offensive"
    pt["rk_ppp"] = float("nan")
    # 進攻：每回合得分越高越好；防守：讓對手每回合得分越低越好
    pt.loc[off, "rk_ppp"] = pt[off].groupby(keys)["ppp"].rank(ascending=False, method="min")
    pt.loc[~off, "rk_ppp"] = pt[~off].groupby(keys)["ppp"].rank(ascending=True, method="min")
    pt["rk_use"] = pt.groupby(keys)["poss_pct"].rank(ascending=False, method="min")   # 使用率排名
    pt["n_teams"] = pt.groupby(keys)["team_id"].transform("count")
    return pt


def playtype_league(pt):
    """聯盟平均：使用率取各隊平均；每回合得分＝全聯盟總得分 ÷ 總回合（回合多的隊佔比較重）"""
    g = (pt.groupby(["season", "season_type", "side", "play_type"])
         .agg(lg_share=("poss_pct", "mean"), lg_pts=("pts", "sum"), lg_poss=("poss", "sum"),
              lg_ppp_mean=("ppp", "mean"))
         .reset_index())
    g["lg_ppp"] = (g["lg_pts"] / g["lg_poss"].where(g["lg_poss"] > 0)).fillna(g["lg_ppp_mean"])
    return g.drop(columns=["lg_pts", "lg_poss", "lg_ppp_mean"])


if PAGE == "戰術使用":
    section("冠軍靠什麼戰術得分？",
            "問題：冠軍隊的進攻是「某種戰術用得特別多」，還是「同樣的戰術打得特別有效率」？　"
            "假設：冠軍的戰術比例和聯盟差不多，真正拉開差距的是每回合得分（效率）")
    pt_status = table_status("playtypes_team")
    pt_raw = load_playtypes_team() if pt_status == "ok" else pd.DataFrame()
    if pt_raw.empty:
        st.info("尚未載入資料，請執行 python load_extra.py --only playtypes"
                + ("（資料表還不存在：請先到 Supabase SQL Editor 執行 schema_extra.sql）"
                   if pt_status == "missing" else ""))
    else:
        PT = prep_playtypes(pt_raw)
        PT_LG = playtype_league(PT)
        # 球隊代號：冠軍隊用 team_raw，其他 22 隊用全聯盟資料表
        id2abbr = dict(zip(team_raw["team_id"], team_raw["abbreviation"]))
        if not league.empty:
            id2abbr.update(dict(zip(league["team_id"], league["abbreviation"])))

        # 球隊按鈕放在獨立一整排，8 隊才排得下（擠在窄欄裡會被切掉、只看得到幾隊）
        pl_team = pills("球隊", ALL_TEAMS, "pl_team", default=ALL_TEAMS[0], format_func=team_label)
        c2, c3, c4 = st.columns(3)
        pl_tid = int(team_raw[team_raw["abbreviation"] == pl_team]["team_id"].iloc[0])
        pl_seasons = sorted(PT[PT["team_id"] == pl_tid]["season"].unique())[::-1]
        if not pl_seasons:   # 這隊完全沒有戰術數據：仍列出所有球季，下面會顯示「沒有資料」
            pl_seasons = sorted(PT["season"].unique())[::-1]
        champ_pl = [s for s in pl_seasons if (s, pl_team) in CHAMP_SET]
        with c2:
            pl_season = st.selectbox(
                "球季", pl_seasons, key=f"pl_season_{pl_team}",
                index=pl_seasons.index(champ_pl[0]) if champ_pl else 0,
                format_func=lambda s: s + ("　★ 奪冠" if (s, pl_team) in CHAMP_SET else ""))
        with c3:
            pl_type = TYPE_OPTIONS[seg("比賽類型", ["例行賽", "季後賽"], "pl_type")]
        with c4:
            side_zh = seg("看哪一端", ["進攻", "防守"], "pl_side")
        side = "offensive" if side_zh == "進攻" else "defensive"
        is_off = side == "offensive"
        color = TEAM_COLORS.get(pl_team, ACCENT)

        cur = PT[(PT["team_id"] == pl_tid) & (PT["season"] == pl_season)
                 & (PT["season_type"] == pl_type) & (PT["side"] == side)]
        cur = cur.merge(PT_LG, on=["season", "season_type", "side", "play_type"], how="left")
        if cur.empty:
            st.info(f"{team_label(pl_team)} {pl_season} {'季後賽' if pl_type == 'Playoffs' else '例行賽'}"
                    "沒有戰術數據（可能那季沒打進季後賽，或還沒載入）。")
        else:
            cur["name"] = cur["play_type"].map(PLAY_ZH).fillna(cur["play_type"])
            cur["d_share"] = (cur["poss_pct"] - cur["lg_share"]) * 100          # 使用率差（百分點）
            # 效率差：統一成「正數＝比聯盟好」。防守端是對手得分，少才是好，所以反過來
            cur["d_ppp"] = (cur["ppp"] - cur["lg_ppp"]) * (1 if is_off else -1)
            cur = cur.sort_values("poss_pct", ascending=False)
            star = "★" if (pl_season, pl_team) in CHAMP_SET else ""
            who = f"{pl_season} {TEAM_ZH.get(pl_team, pl_team)}{star}"

            left, right = st.columns([5, 4], gap="large")
            with left:
                section(f"{who} 戰術地圖（{side_zh}）",
                        "橫軸：比聯盟多用還是少用；縱軸：比聯盟有效率還是沒效率；圈越大＝回合越多")
                plot = cur[cur["play_type"] != "Misc"]
                fig = go.Figure()
                fig.add_hline(y=0, line=dict(color=MUTED, width=1))
                fig.add_vline(x=0, line=dict(color=MUTED, width=1))
                xr = max(3.0, plot["d_share"].abs().max() * 1.25)
                yr = max(0.08, plot["d_ppp"].abs().max() * 1.25)
                good, bad = ("多用又有效", "常用但沒效率") if is_off else ("常被打但守得住", "常被打又守不住")
                for x, y, txt in [(xr, yr, good), (-xr, yr, "用得少但有效" if is_off else "少被打、守得住"),
                                  (xr, -yr, bad), (-xr, -yr, "用得少也沒效率" if is_off else "少被打但守不住")]:
                    fig.add_annotation(x=x, y=y, text=txt, showarrow=False, opacity=0.75,
                                       xanchor="right" if x > 0 else "left", yanchor="top" if y > 0 else "bottom",
                                       font=dict(size=11, color=INK_2))
                fig.add_trace(go.Scatter(
                    x=plot["d_share"], y=plot["d_ppp"], mode="markers+text", text=plot["name"],
                    textposition="top center", textfont=dict(size=12, color=INK),
                    marker=dict(size=10 + 30 * (plot["poss_pct"] / 0.3).clip(upper=1) ** 0.5,
                                color=color, opacity=0.8, line=dict(width=1, color="rgba(26,20,38,0.35)")),
                    customdata=plot[["name", "poss_pct", "lg_share", "ppp", "lg_ppp", "rk_ppp", "n_teams"]].values,
                    hovertemplate="<b>%{customdata[0]}</b><br>使用率 %{customdata[1]:.1%}（聯盟 %{customdata[2]:.1%}）"
                                  "<br>每回合" + ("得分" if is_off else "失分") +
                                  " %{customdata[3]:.2f}（聯盟 %{customdata[4]:.2f}）"
                                  "<br>效率排名 %{customdata[5]:.0f} / %{customdata[6]:.0f}<extra></extra>",
                    showlegend=False))
                fig = style(fig, 470)
                fig.update_xaxes(range=[-xr * 1.05, xr * 1.05], title="使用率 − 聯盟平均（百分點）",
                                 ticksuffix="", zeroline=False)
                fig.update_yaxes(range=[-yr * 1.05, yr * 1.05], tickformat="+.2f",
                                 title="每回合" + ("得分" if is_off else "少失") + "比聯盟多幾分")
                st.plotly_chart(fig, width="stretch")
            with right:
                section("每種戰術的使用率與效率",
                        "長條＝使用率；排名是每回合" + ("得分" if is_off else "失分") + "在全聯盟的名次（1 = 最好）")
                tb = pd.DataFrame({
                    "戰術": cur["name"],
                    "使用率": [fmt(v, ".1%") for v in cur["poss_pct"]],
                    "_bar": cur["poss_pct"] / max(cur["poss_pct"].max(), 0.01),
                    "聯盟使用率": [fmt(v, ".1%") for v in cur["lg_share"]],
                    "每回合" + ("得分" if is_off else "失分"): [fmt(v, ".2f") for v in cur["ppp"]],
                    "聯盟效率": [fmt(v, ".2f") for v in cur["lg_ppp"]],
                    "效率差": [fmt(v, "+.2f") for v in cur["d_ppp"]],
                    "排名": [f"{r:.0f}" if pd.notna(r) else "-" for r in cur["rk_ppp"]],
                })
                nice_table(tb, num_cols=list(tb.columns[1:]), signed_cols=["效率差"], bars={"使用率": "_bar"})
                st.caption("效率差：正數＝比聯盟好（防守端已經反過來算：對手每回合少得幾分）。")

            # 自動摘要：最常用、最有效、最弱
            main = cur[(cur["play_type"] != "Misc") & (cur["poss_pct"] >= 0.04)]   # 太少用的戰術樣本小，不列入
            if not main.empty:
                top3 = "、".join(main.head(3)["name"])
                best = main.sort_values("d_ppp", ascending=False).iloc[0]
                worst = main.sort_values("d_ppp").iloc[0]
                insight([
                    f"<b>{who}</b> {side_zh}端最常{'用' if is_off else '面對'}的三種戰術：{top3}。",
                    f"最大優勢：<b>{best['name']}</b>，每回合比聯盟{'多得' if is_off else '少失'} "
                    f"{best['d_ppp']:.2f} 分（聯盟第 {best['rk_ppp']:.0f} 名）。",
                    f"相對弱點：<b>{worst['name']}</b>，每回合比聯盟{'少得' if is_off else '多失'} "
                    f"{abs(worst['d_ppp']):.2f} 分（聯盟第 {worst['rk_ppp']:.0f} 名）。",
                    "讀法：如果圈大多落在「上方」而不是「右邊」，代表這支隊伍贏在效率，而不是打法特別不一樣。",
                ])

            # ===== 八位冠軍的共同點 =====
            st.write("")
            section(f"八位冠軍的共同點：每種戰術在聯盟排第幾？（{side_zh}）",
                    "每一欄是一位冠軍；格子裡的數字是聯盟排名（1 = 最好），顏色越深越前面；最右欄是八位冠軍的中位數")
            rank_kind = seg("排名依據", ["效率（每回合得分）", "使用率（用得多不多）"], "pl_rank_kind")
            rk_col = "rk_ppp" if rank_kind.startswith("效率") else "rk_use"
            ch = champs[champs["season"].isin(PT["season"].unique())].sort_values("season")
            cols, rows = [], {}
            for _, c in ch.iterrows():
                d = PT[(PT["team_id"] == c["team_id"]) & (PT["season"] == c["season"])
                       & (PT["season_type"] == pl_type) & (PT["side"] == side)]
                if d.empty:
                    continue
                lab = f"{c['season']}<br>{c['abbreviation']}"
                cols.append(lab)
                rows[lab] = dict(zip(d["play_type"], d[rk_col]))
            if not cols:
                st.caption("目前沒有冠軍球季的戰術數據。")
            else:
                hm = pd.DataFrame(rows).reindex([p for p in PLAY_ORDER if p != "Misc"])
                hm = hm.dropna(how="all")
                hm["中位數"] = hm[cols].median(axis=1)
                hm = hm.sort_values("中位數")
                z = hm.values.astype(float)
                ramp = PURPLE_RAMP[::-1]   # 排名數字越小（越好）顏色越深
                fig = go.Figure(go.Heatmap(
                    z=z, x=list(hm.columns), y=[PLAY_ZH.get(p, p) for p in hm.index],
                    zmin=1, zmax=30, xgap=2, ygap=2, showscale=False,
                    colorscale=[[i / (len(ramp) - 1), c] for i, c in enumerate(ramp)],
                    hovertemplate="%{y}　%{x}<br>聯盟第 %{z:.0f} 名<extra></extra>"))
                for i in range(z.shape[0]):
                    for j in range(z.shape[1]):
                        if pd.notna(z[i, j]):
                            fig.add_annotation(x=hm.columns[j], y=PLAY_ZH.get(hm.index[i], hm.index[i]),
                                               text=f"{z[i, j]:.0f}", showarrow=False,
                                               font=dict(size=11, color="#ffffff" if z[i, j] <= 8 else INK))
                fig.update_yaxes(autorange="reversed", showgrid=False)
                fig.update_xaxes(showgrid=False, side="top")
                st.plotly_chart(style(fig, 90 + 42 * len(hm)), width="stretch")
                strong = [PLAY_ZH.get(p, p) for p in hm.index[hm["中位數"] <= 10]]
                st.caption("讀法：橫著看一列，如果八位冠軍大多在前 10 名（深紫色），這個戰術就是「冠軍共同點」。"
                           + (f"目前中位數在前 10 名的：{'、'.join(strong)}。" if strong else
                              "目前沒有任何戰術的中位數在前 10 名：冠軍各有各的打法。")
                           + "改成「使用率」，就能檢查假設：如果使用率排名分散、效率排名集中在前面，代表冠軍贏在效率。")

            # ===== 奪冠前後：某一種戰術的逐季變化 =====
            st.write("")
            section(f"{TEAM_ZH.get(pl_team, pl_team)}的某一種戰術，逐季怎麼變？",
                    "紫色直條是奪冠球季；看看奪冠那季是突然變強，還是一路累積上來")
            opts = [p for p in PLAY_ORDER if p != "Misc" and p in set(PT["play_type"])]
            default_p = cur[cur["play_type"] != "Misc"]["play_type"].iloc[0] if (cur["play_type"] != "Misc").any() else opts[0]
            pl_play = pills("戰術", opts, "pl_play", default=default_p, format_func=lambda p: PLAY_ZH.get(p, p))
            tr = PT[(PT["team_id"] == pl_tid) & (PT["season_type"] == pl_type) & (PT["side"] == side)
                    & (PT["play_type"] == pl_play)].merge(
                PT_LG, on=["season", "season_type", "side", "play_type"], how="left").sort_values("season")
            if tr.empty:
                st.caption("這個戰術沒有資料。")
            else:
                tr_seasons = list(tr["season"])
                # 回合數很少的球季（例如剛開打的這一季）數字容易暴衝，畫成空心圈提醒「樣本少」
                poss = pd.to_numeric(tr["poss"], errors="coerce")
                few = list((poss < 0.3 * poss.median()).fillna(False))
                g1, g2 = st.columns(2, gap="large")
                for c_, val, lg, title, f_ in [
                        (g1, "poss_pct", "lg_share", "使用率", ".0%"),
                        (g2, "ppp", "lg_ppp", "每回合" + ("得分" if is_off else "失分"), ".2f")]:
                    with c_:
                        fig = go.Figure()
                        fig.add_trace(go.Scatter(x=tr_seasons, y=tr[lg], name="聯盟平均", mode="lines",
                                                 line=dict(color=MUTED, width=2, dash="dot")))
                        fig.add_trace(go.Scatter(x=tr_seasons, y=tr[val], name=TEAM_ZH.get(pl_team, pl_team),
                                                 mode="lines+markers", line=dict(color=color, width=3),
                                                 marker=dict(size=[11 if f else 7 for f in few],
                                                             symbol=["circle-open" if f else "circle" for f in few],
                                                             line=dict(width=2, color=color))))
                        champion_bands(fig, tr_seasons, pl_team)
                        fig = style(fig, 320)
                        fig.update_yaxes(tickformat=f_, title=title)
                        fig.update_xaxes(type="category", tickangle=-45)
                        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                few_s = [s_ for s_, f in zip(tr_seasons, few) if f]
                st.caption(("防守端的每回合失分：線越低越好。" if not is_off else "")
                           + "左圖看「用得多不多」，右圖看「打得好不好」。"
                           + (f"空心圈（{'、'.join(few_s)}）是回合數很少的球季，"
                              "例如剛開打的這一季，數字容易忽高忽低，先不要下結論。" if few_s else ""))

        # ===== 各隊戰術比較 =====
        st.write("")
        st.divider()
        win = pd.DataFrame()
        if not league.empty:   # 例行賽勝率：用來排序與找奪冠方程式
            win = league[league["season_type"] == "Regular Season"][["season", "team_id", "abbreviation", "w", "gp"]].copy()
            win["w"] = pd.to_numeric(win["w"], errors="coerce")
            win["gp"] = pd.to_numeric(win["gp"], errors="coerce")
            win["win_pct"] = win["w"] / win["gp"].where(win["gp"] > 0)
            win = win.drop_duplicates(["season", "team_id"])
        champ_ids = set(zip(champs["season"], champs["team_id"]))   # {(球季, team_id)}

        section(f"{pl_season} 各隊戰術比較（{side_zh}）",
                "每一列是一支球隊，依例行賽勝率由高到低排；框起來的那一列是當季冠軍；最下面是聯盟平均")
        k1, k2 = st.columns(2)
        with k1:
            cmp_metric = seg("比較什麼", ["使用率", "每回合" + ("得分" if is_off else "失分"), "效率排名"], "pl_cmp_metric")
        with k2:
            cmp_scope = seg("球隊範圍", ["全聯盟 30 隊", "八支冠軍隊"], "pl_cmp_scope")
        sea = PT[(PT["season"] == pl_season) & (PT["season_type"] == pl_type) & (PT["side"] == side)
                 & (PT["play_type"] != "Misc")]
        if cmp_scope == "八支冠軍隊":
            sea = sea[sea["team_id"].isin(set(team_raw["team_id"]))]
        if sea.empty:
            st.caption("這個條件沒有資料。")
        else:
            col_key = {"使用率": "poss_pct", "效率排名": "rk_ppp"}.get(cmp_metric, "ppp")
            hm = sea.pivot_table(index="team_id", columns="play_type", values=col_key, aggfunc="first")
            hm = hm[[p for p in PLAY_ORDER if p in hm.columns]]
            wp = win[win["season"] == pl_season].set_index("team_id")["win_pct"] if not win.empty else pd.Series(dtype=float)
            order = sorted(hm.index, key=lambda t: -(wp.get(t, float("nan")) if pd.notna(wp.get(t, float("nan"))) else -1))
            hm = hm.reindex(order)
            # 最下面加一列聯盟平均（全聯盟 30 隊，不受「球隊範圍」影響）
            lg = PT_LG[(PT_LG["season"] == pl_season) & (PT_LG["season_type"] == pl_type) & (PT_LG["side"] == side)]
            lg = lg.set_index("play_type")
            if col_key == "poss_pct":
                hm.loc["lg"] = lg["lg_share"].reindex(hm.columns).values
            elif col_key == "ppp":
                hm.loc["lg"] = lg["lg_ppp"].reindex(hm.columns).values
            else:
                hm.loc["lg"] = 15.5   # 排名的中間值
            labels = []
            for t in hm.index:
                if t == "lg":
                    labels.append("聯盟平均")
                    continue
                ab = id2abbr.get(t, str(t))
                w_ = wp.get(t, float("nan"))
                star = " ★" if (pl_season, t) in champ_ids else ""
                labels.append(f"{ab} {ALL_ZH.get(ab, '')}{star}　{'' if pd.isna(w_) else format(w_, '.0%')}".strip())
            z = hm.values.astype(float)
            # 顏色：越深越「好」或越「多」。效率排名、防守失分是數字越小越好，所以色階反過來
            reverse = col_key == "rk_ppp" or (col_key == "ppp" and not is_off)
            ramp = PURPLE_RAMP[::-1] if reverse else PURPLE_RAMP
            zz = z[:-1] if len(z) > 1 else z
            zmin, zmax = (1, 30) if col_key == "rk_ppp" else (pd.Series(zz.ravel()).min(), pd.Series(zz.ravel()).max())
            vfmt = {"poss_pct": ".0%", "ppp": ".2f", "rk_ppp": ".0f"}[col_key]
            xs = [PLAY_ZH.get(p, p) for p in hm.columns]
            fig = go.Figure(go.Heatmap(
                z=z, x=xs, y=labels, zmin=zmin, zmax=zmax, xgap=2, ygap=2, showscale=False,
                colorscale=[[i / (len(ramp) - 1), c] for i, c in enumerate(ramp)],
                hovertemplate="%{y}<br>%{x}：%{z:" + vfmt + "}<extra></extra>"))
            if len(hm) <= 12:   # 隊伍少才在格子裡寫數字，30 隊時太擠，改用滑鼠查看
                for i in range(z.shape[0]):
                    for j in range(z.shape[1]):
                        if pd.notna(z[i, j]) and not (col_key == "rk_ppp" and hm.index[i] == "lg"):
                            lvl = (z[i, j] - zmin) / ((zmax - zmin) or 1)
                            lvl = 1 - lvl if reverse else lvl
                            fig.add_annotation(x=xs[j], y=labels[i], text=format(z[i, j], vfmt), showarrow=False,
                                               font=dict(size=10.5, color="#ffffff" if lvl > 0.6 else INK))
            for i, t in enumerate(hm.index):   # 冠軍那一列框起來
                if (pl_season, t) in champ_ids:
                    fig.add_shape(type="rect", xref="x", yref="y", x0=-0.5, x1=len(xs) - 0.5, y0=i - 0.5, y1=i + 0.5,
                                  line=dict(color=ACCENT, width=2))
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=False, side="top")
            st.plotly_chart(style(fig, 90 + 30 * len(hm)), width="stretch")
            st.caption("讀法：上面幾列是勝率最高的球隊。直著看一欄，如果深色集中在上半部、淺色在下半部，"
                       "代表這個戰術「打得好的隊伍比較會贏」。30 隊時格子裡不寫數字，把滑鼠移到格子上就能看到。")

        # ===== 奪冠方程式 =====
        st.write("")
        st.divider()
        section("奪冠方程式：哪些戰術和贏球最有關？",
                "用全聯盟 30 隊、每一季的例行賽：每種戰術的「效率」和「使用率」，各自和球隊勝率的相關係數。"
                "長條越長（越往右），代表這件事做得好的隊伍越會贏")
        if win.empty:
            st.info("需要全聯盟數據才能計算，請先執行：python load_to_supabase.py --only league")
        else:
            M = PT[(PT["season_type"] == "Regular Season") & (PT["play_type"] != "Misc")].merge(
                win[["season", "team_id", "win_pct"]], on=["season", "team_id"], how="inner")
            # 效率統一成「數字越大越好」：防守端用負的失分
            M["eff"] = M["ppp"].where(M["side"] == "offensive", -M["ppp"])
            corr = []
            for (sd, p), g in M.groupby(["side", "play_type"]):
                if len(g) >= 20:
                    corr.append({"side": sd, "play_type": p, "n": len(g),
                                 "r_eff": g["eff"].corr(g["win_pct"]), "r_use": g["poss_pct"].corr(g["win_pct"])})
            corr = pd.DataFrame(corr)
            n_seasons = M["season"].nunique()
            if corr.empty:
                st.caption("資料太少，還算不出來。")
            else:
                cs = corr[corr["side"] == side].sort_values("r_eff")
                fig = go.Figure()
                fig.add_trace(go.Bar(y=[PLAY_ZH.get(p, p) for p in cs["play_type"]], x=cs["r_use"], orientation="h",
                                     name="使用率 和勝率的相關", marker_color="#c9c3d6",
                                     hovertemplate="%{y}：使用率相關 %{x:+.2f}<extra></extra>"))
                fig.add_trace(go.Bar(y=[PLAY_ZH.get(p, p) for p in cs["play_type"]], x=cs["r_eff"], orientation="h",
                                     name="效率 和勝率的相關", marker_color=ACCENT,
                                     hovertemplate="%{y}：效率相關 %{x:+.2f}<extra></extra>"))
                fig.add_vline(x=0, line=dict(color=MUTED, width=1))
                for x0, txt in [(0.1, "弱"), (0.3, "中"), (0.5, "強")]:
                    fig.add_vline(x=x0, line=dict(color=GRID, width=1, dash="dot"))
                    fig.add_annotation(x=x0, y=1.0, yref="paper", yanchor="bottom", text=txt, showarrow=False,
                                       font=dict(size=10, color=INK_2))
                fig = style(fig, 90 + 38 * len(cs))
                fig.update_layout(barmode="group", bargap=0.3)
                fig.update_xaxes(range=[min(-0.3, cs[["r_eff", "r_use"]].min().min() - 0.05),
                                        max(0.6, cs[["r_eff", "r_use"]].max().max() + 0.05)],
                                 tickformat="+.1f", title="相關係數（−1 ～ +1，0 代表沒關係）")
                fig.update_yaxes(showgrid=False)
                rounded(fig)
                st.plotly_chart(fig, width="stretch")
                top = cs.sort_values("r_eff", ascending=False).head(3)
                use_stronger = (cs["r_use"].abs() > cs["r_eff"]).sum()
                insight([
                    f"{side_zh}端和勝率最有關的三種戰術效率：<b>{'、'.join(PLAY_ZH.get(p, p) for p in top['play_type'])}</b>"
                    f"（相關係數 {'、'.join(format(v, '+.2f') for v in top['r_eff'])}）。",
                    f"{len(cs)} 種戰術中，有 {use_stronger} 種是「用得多」比「打得好」更和勝率有關。"
                    + ("這支持今天的假設：贏球靠的是效率，不是打法。" if use_stronger <= len(cs) / 3
                       else "這和今天的假設不太一樣：有不少戰術是「用多用少」本身就和勝率有關。"),
                    f"資料：{n_seasons} 季 × 30 隊的例行賽。相關不等於因果，例如好球隊快攻多，"
                    "也可能是因為防守好、搶到球就快攻。",
                ])

                # ---- 方程式分數：用上面的相關係數當權重，替每支球隊打分數，看冠軍會不會排在前面 ----
                section("檢驗方程式：用這個公式幫每隊打分數，冠軍會排第幾？",
                        "方程式分數＝把進攻、防守各戰術的效率換成「比同季聯盟好多少」（標準分數），"
                        "再用上圖的效率相關係數當權重加權平均；只用相關係數大於 0 的戰術")
                wts = corr.set_index(["side", "play_type"])["r_eff"].clip(lower=0)
                M["z"] = M.groupby(["season", "side", "play_type"])["eff"].transform(
                    lambda s: (s - s.mean()) / (s.std() or 1))
                M["w"] = [wts.get((sd, p), 0) for sd, p in zip(M["side"], M["play_type"])]
                M["wz"] = M["w"] * M["z"]
                sc = M.groupby(["season", "team_id"]).agg(wz=("wz", "sum"), w=("w", "sum"), win_pct=("win_pct", "first"))
                sc["score"] = sc["wz"] / sc["w"].where(sc["w"] > 0)
                sc = sc.reset_index()
                sc["rk_score"] = sc.groupby("season")["score"].rank(ascending=False, method="min")
                sc["rk_win"] = sc.groupby("season")["win_pct"].rank(ascending=False, method="min")
                chs = sc[[(s, t) in champ_ids for s, t in zip(sc["season"], sc["team_id"])]].sort_values("season")
                if chs.empty:
                    st.caption("範圍內沒有冠軍球季。")
                else:
                    rows = []
                    for _, r in chs.iterrows():
                        ab = id2abbr.get(r["team_id"], "")
                        rows.append({"球季": r["season"], "冠軍": f"{ab} {TEAM_ZH.get(ab, '')}", "_key": ab,
                                     "方程式排名": f"{r['rk_score']:.0f}", "勝率排名": f"{r['rk_win']:.0f}",
                                     "方程式分數": f"{r['score']:+.2f}", "勝率": f"{r['win_pct']:.1%}"})
                    nice_table(pd.DataFrame(rows), num_cols=["方程式排名", "勝率排名", "方程式分數", "勝率"],
                               signed_cols=["方程式分數"], dot_col="冠軍", colors=TEAM_COLORS)
                    top3 = int((chs["rk_score"] <= 3).sum())
                    top3_win = int((chs["rk_win"] <= 3).sum())
                    r_all = sc["score"].corr(sc["win_pct"])
                    insight([
                        f"{len(chs)} 位冠軍裡，有 <b>{top3}</b> 位的方程式分數在當季前 3 名"
                        f"（對照：例行賽勝率前 3 名的有 {top3_win} 位）。",
                        f"全部球隊的方程式分數和勝率相關 {r_all:+.2f}。",
                        "讀法：方程式排名越前面，代表「把最重要的戰術打好」這件事，冠軍做得比別人好。"
                        "如果某位冠軍方程式排名很後面，他就是靠別的東西奪冠（季後賽表現、健康、球星），值得單獨研究。",
                        "注意：權重和分數用的是同一批資料算出來的，所以這是「描述」不是「預測」；"
                        "要真正驗證，可以只用前幾季算權重，再看後幾季的冠軍排第幾。",
                    ])

                # ---- 單一戰術：效率 vs 勝率散點圖 ----
                section("單一戰術：效率越好，勝率越高嗎？",
                        "每個點是一支球隊的一個球季（例行賽）；灰色是其他球隊，彩色是冠軍")
                default_fp = cs.sort_values("r_eff", ascending=False)["play_type"].iloc[0]
                fp = pills("戰術", list(cs.sort_values("r_eff", ascending=False)["play_type"]), "pl_formula_play",
                           default=default_fp, format_func=lambda p: PLAY_ZH.get(p, p))
                d = M[(M["side"] == side) & (M["play_type"] == fp)].copy()
                d["champ"] = [(s, t) in champ_ids for s, t in zip(d["season"], d["team_id"])]
                d["abbr"] = d["team_id"].map(id2abbr)
                fig = go.Figure()
                o = d[~d["champ"]]
                fig.add_trace(go.Scatter(x=o["ppp"], y=o["win_pct"], mode="markers", name="其他球隊",
                                         marker=dict(size=7, color=DIM, opacity=0.7),
                                         customdata=o[["abbr", "season"]].values,
                                         hovertemplate="%{customdata[0]} %{customdata[1]}<br>每回合 %{x:.2f}｜勝率 %{y:.1%}<extra></extra>"))
                c = d[d["champ"]]
                fig.add_trace(go.Scatter(x=c["ppp"], y=c["win_pct"], mode="markers+text", name="冠軍",
                                         marker=dict(size=13, symbol="star",
                                                     color=[TEAM_COLORS.get(a, ACCENT) for a in c["abbr"]],
                                                     line=dict(width=1, color=SURFACE)),
                                         text=[f"{a} {s[2:]}" for a, s in zip(c["abbr"], c["season"])],
                                         textposition="top center", textfont=dict(size=11, color=INK),
                                         customdata=c[["abbr", "season"]].values,
                                         hovertemplate="★ %{customdata[0]} %{customdata[1]}<br>每回合 %{x:.2f}｜勝率 %{y:.1%}<extra></extra>"))
                fig = style(fig, 420)
                fig.update_xaxes(title="每回合" + ("得分（越右越好）" if is_off else "失分（越左越好）"), tickformat=".2f")
                fig.update_yaxes(title="例行賽勝率", tickformat=".0%")
                st.plotly_chart(fig, width="stretch")
                r_fp = corr[(corr["side"] == side) & (corr["play_type"] == fp)]["r_eff"]
                st.caption(f"{PLAY_ZH.get(fp, fp)}（{side_zh}）的效率和勝率相關 {r_fp.iloc[0]:+.2f}。"
                           + ("進攻端：點越往右上排，代表打得越好越會贏。" if is_off else
                              "防守端：失分越少越好，所以點應該往左上排。")
                           + "看看冠軍的星星，是不是都在右上角（防守是左上角）？")


# ---------- 1. 球季趨勢 ----------
if PAGE == "球季趨勢":
    section(f"{metric_name}：各隊逐季變化", "★ 是該隊奪冠的球季；選擇聚焦球隊，其他球隊會變成灰色背景，線條就不會互相干擾")
    focus = pills("聚焦球隊（可多選，不選＝全部上色）", teams_sel, "focus", default=[], multi=True,
                  format_func=team_label)
    fig = go.Figure()
    order = [a for a in teams_sel if a not in focus] + [a for a in teams_sel if a in focus]  # 聚焦的畫在最上層
    for abbr in order:
        d = team_season[team_season["abbreviation"] == abbr].sort_values("season")
        if d.empty:
            continue
        lit = not focus or abbr in focus
        color = TEAM_COLORS.get(abbr, MUTED) if lit else DIM
        fig.add_trace(go.Scatter(
            x=d["season"], y=d[metric], mode="lines+markers", name=team_label(abbr),
            line=dict(color=color, width=2.6 if (focus and lit) else (2 if lit else 1.2)),
            marker=dict(size=7 if lit else 4, color=color, line=dict(width=1.5, color=SURFACE)),
            opacity=1 if lit else 0.55, showlegend=lit,
            customdata=d[["games", "wins"]].values,
            hovertemplate=f"<b>{team_label(abbr)}</b>　%{{y:{mfmt}}}"
                          "（%{customdata[1]} 勝 / %{customdata[0]} 場）<extra></extra>",
        ))
        c = d[d["champion"]]
        if not c.empty:
            fig.add_trace(go.Scatter(
                x=c["season"], y=c[metric], mode="markers", showlegend=False, hoverinfo="skip",
                marker=dict(symbol="star", size=20 if lit else 11, color=color,
                            line=dict(width=1.5 if lit else 0, color=SURFACE)),
            ))
        if lit:   # 線尾直接標上隊名，不用一直對照圖例
            last = d.iloc[-1]
            fig.add_annotation(x=last["season"], y=last[metric], text=abbr, showarrow=False,
                               xanchor="left", xshift=10, font=dict(size=11, color=INK_2))
    fig.update_yaxes(title=metric_name, tickformat=".0%" if "%" in mfmt else None)
    fig.update_xaxes(title="球季", categoryorder="array", categoryarray=seasons, type="category")
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(style(fig, 480), width="stretch")


# ---------- 2. 球隊 × 球季 熱力圖 ----------
if PAGE == "球隊 × 球季":
    section(f"{metric_name}：球隊 × 球季交叉表", "顏色越深數值越高；★ 是奪冠球季；空白代表該季沒有這類比賽")
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
                               font=dict(size=10.5, color="#ffffff" if level > 0.6 else INK))
    fig.update_yaxes(autorange="reversed", showgrid=False)
    # 一定要指定 type="category"：不然 Plotly 會把「2006-07」這種球季當成「2006 年 7 月」的日期，
    # 2012-13 以後（13 月不存在）就對不上位置，數字全部擠到最左邊
    fig.update_xaxes(showgrid=False, side="top", type="category")
    st.plotly_chart(style(fig, 100 + 62 * len(pivot.index)), width="stretch")


# ---------- 3. 冠軍球季比較 ----------
if PAGE == "冠軍球季比較":
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
                rows.append({"_key": r["abbreviation"], "冠軍球季": r["label"], metric_name: fmt(r[metric], mfmt),
                             "其他球季平均": fmt(others, mfmt), "差距": diff_txt})
            nice_table(pd.DataFrame(rows), num_cols=(metric_name, "其他球季平均", "差距"), signed_cols=("差距",),
                       dot_col="冠軍球季", colors=TEAM_COLORS)


# ---------- 4. 球員 ----------
if PAGE == "球員":
    c1, c2 = st.columns([1, 2])
    p_team = c1.selectbox("球隊", teams_sel, format_func=team_label, key="p_team")
    with c2:
        mode = seg("檢視方式", ["跨球季：在該隊的所有球季", "單一球季"], "p_mode")
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

        c3, c4 = st.columns([1, 1], gap="large")
        names = career["player_name"].tolist()
        picked = c3.multiselect("選擇球員（最多 6 位）", names, default=names[:3], max_selections=6,
                                help="依在這隊的總得分排序；只列出在這隊出賽至少 20 場的球員")
        with c4:   # 改成膠囊按鈕：9 個指標一眼看完，點一下就切換
            p_metric_name = pills("球員指標", list(P_METRICS), "p_metric", default=list(P_METRICS)[0])
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
                    marker=dict(size=8, color=pc, line=dict(width=1.5, color=SURFACE)),
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
                                color=color, opacity=0.9, line=dict(width=1.5, color=SURFACE)),
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
                    marker=dict(size=8, color=color, opacity=0.4, line=dict(width=1, color=SURFACE)),
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
if PAGE == "數據表":
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
