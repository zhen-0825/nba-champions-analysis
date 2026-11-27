"""
NBA 冠軍球隊數據分析網頁（Streamlit）
資料來源：Supabase 資料庫（由 load_to_supabase.py 寫入）

執行方式（在 VS Code 終端機輸入）：
  streamlit run app.py

需要 .env 裡有 SUPABASE_URL 和 SUPABASE_PUBLISHABLE_KEY（只能讀、不能改的公開金鑰）
"""

import io
import os
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import season_stats as ss   # 本季數據的計算（奪冠列車、焦點人物、首頁本季故事）

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
# 其他 22 隊（每天陸續載入）也給一個球衣代表色，否則加入比較時全部是同一種灰色、分不出誰是誰
# 30 隊一定會有顏色相近的（例如紅色系），所以折線尾端仍然直接標隊名，不只靠顏色分辨
TEAM_COLORS.update({
    "SAS": "#5b6670", "DAL": "#0053BC", "MIA": "#98002E", "CLE": "#860038", "ATL": "#E03A3E",
    "BKN": "#2b2b2b", "CHA": "#00788C", "CHI": "#CE1141", "DET": "#1D428A", "HOU": "#BA0C2F",
    "IND": "#B58500", "LAC": "#1D428A", "MEM": "#5D76A9", "MIN": "#236192", "NOP": "#85714D",
    "ORL": "#0077C0", "PHI": "#006BB6", "PHX": "#E56020", "POR": "#B8202E", "SAC": "#5A2D81",
    "UTA": "#3E2680", "WAS": "#002B5C",
})
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
    "投籃命中率": ("fg_pct", ".1%"),
    "場均籃板": ("rpg", ".1f"),
    "場均抄截": ("spg", ".1f"),
    "場均阻攻": ("bpg", ".1f"),
    "場均失誤（越少越好）": ("topg", ".1f"),
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
.block-container { padding-top: 3.2rem; padding-bottom: 4rem; max-width: 1360px; }   /* 上方留空間，麵包屑才不會被頂端工具列蓋住 */

/* ===== 左側：品牌黑底選單（參考 YouTube 的左側導覽）===== */
section[data-testid="stSidebar"] { background: var(--night); border-right: 1px solid #241b38; }
section[data-testid="stSidebar"] * { color: #d9d3ea; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p { color: #8d86a3 !important; font-size: 0.78rem; }
section[data-testid="stSidebar"] hr { border-color: #241b38 !important; }
.logo { display: flex; align-items: center; gap: 12px; margin: 0 0 18px 4px; }
.logo img { width: 42px; height: 42px; }
.logo-name { font-size: 1.5rem; font-weight: 900; letter-spacing: 0.01em; line-height: 1.05; }
.logo-name .z { color: #8b5cf6 !important; } .logo-name .h { color: #ffffff !important; }
.logo-tag { font-size: 0.62rem; letter-spacing: 0.22em; color: #8d86a3 !important; margin-top: 2px; }
/* 標誌就是「回首頁」按鈕：一顆看不見的按鈕疊在標誌上面（按鈕本身不能放圖片），按標誌就回首頁 */
.logo { padding: 6px 8px; margin: 0 0 12px 0; border-radius: 12px; transition: background 0.15s ease; }
.st-key-nav_home { margin-top: -66px; height: 62px; position: relative; z-index: 2; }
.st-key-nav_home button, .st-key-nav_home button:hover, .st-key-nav_home button:active {
  height: 62px; background: transparent !important; border: none !important; box-shadow: none !important; cursor: pointer; }
.st-key-nav_home button p { color: transparent !important; }          /* 按鈕文字隱藏，只看得到標誌 */
.st-key-nav_home button:focus-visible { outline: 2px solid #a78bfa; }  /* 用鍵盤切換時仍看得到框線 */
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"]:has(.st-key-nav_home button:hover) .logo { background: #1c1529; }
.nav-group { font-size: 0.72rem; letter-spacing: 0.16em; color: #8d86a3 !important; margin: 18px 0 4px 12px; }
section[data-testid="stSidebar"] .stButton > button {
  justify-content: flex-start; text-align: left; border-radius: 10px; padding: 0.5rem 0.9rem;
  border: 1px solid transparent; background: transparent; box-shadow: none; }
section[data-testid="stSidebar"] .stButton > button > div,
section[data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"] {
  justify-content: flex-start !important; text-align: left !important; width: 100%; }
section[data-testid="stSidebar"] .stButton > button p { text-align: left !important; font-size: 0.95rem; }
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

/* ===== 問題／假設小卡 ===== */
.hypo { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 10px 16px;
        margin: 4px 0 14px 0; font-size: 0.9rem; color: var(--ink); line-height: 1.9; }
.hypo-k { display: inline-block; font-size: 0.74rem; font-weight: 700; color: #ffffff; background: var(--night);
          border-radius: 4px; padding: 0 7px; margin-right: 10px; line-height: 1.7; }
.hypo div:nth-child(2) .hypo-k { background: var(--brand); }

/* ===== 圖例列（多張圖共用一個圖例）===== */
.legend-row { font-size: 0.85rem; color: var(--ink-2); margin: -4px 0 12px 0; display: flex; align-items: center;
              flex-wrap: wrap; gap: 6px 14px; }
.legend-row .sw { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }
.legend-row .lg-note { color: var(--muted); }

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
.insight-k { display: inline-block; font-size: 0.74rem; font-weight: 700; color: #ffffff; background: var(--brand);
             border-radius: 4px; padding: 0 7px; margin-right: 10px; line-height: 1.7; }

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
.ntable th, .ntable td { white-space: nowrap; }
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
/* ===== 維基式版面（1030-1～4、1030-7、1030-11）===== */
.summary { background: var(--brand-soft); border: 1px solid #ddd0fb; border-radius: 12px; padding: 12px 18px;
           margin: 0 0 14px 0; color: #2d2245; font-size: 0.93rem; line-height: 1.85; }
.summary-k { font-size: 0.74rem; font-weight: 700; color: #4c1d95; letter-spacing: 0.08em; margin-bottom: 2px; }
.summary ol { margin: 0; padding-left: 1.3rem; }
.chart-headline { font-size: 1.02rem; font-weight: 700; color: var(--ink); margin: 6px 0 4px 0; line-height: 1.5; }
.howread { font-size: 0.86rem; color: var(--ink-2); line-height: 1.8; }
.check-k { display: inline-block; font-size: 0.74rem; font-weight: 700; color: #4c1d95; background: #ffffff;
           border: 1px solid #c4b5fd; border-radius: 4px; padding: 0 7px; margin-right: 10px; line-height: 1.7; }
.section-title.sub2 { font-size: 1rem; border-left-width: 2px; margin-left: 14px; }
.section-title.sub2 + .section-sub { margin-left: 27px; }
.toc { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 10px 18px;
       margin: 0 0 14px 0; font-size: 0.9rem; line-height: 1.9; }
.toc-k { font-size: 0.74rem; font-weight: 700; color: var(--ink-2); letter-spacing: 0.08em; }
.toc a { color: var(--ink); text-decoration: none; } .toc a:hover { color: var(--brand); text-decoration: underline; }
.toc .t2 { padding-left: 1.4rem; color: var(--ink-2); }
.foot-k { font-size: 0.95rem; font-weight: 700; color: var(--ink); margin: 26px 0 6px 0; padding-left: 10px;
          border-left: 3px solid var(--brand); }
.foot-why { font-size: 0.8rem; color: var(--ink-2); margin: -2px 0 10px 4px; line-height: 1.5; }
.feature { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; overflow: hidden; height: 100%; }
.feature-top { background: var(--night); padding: 10px 18px; font-size: 0.78rem; color: #a78bfa; font-weight: 700;
               letter-spacing: 0.1em; }
.feature-body { padding: 16px 20px 18px 20px; }
.feature-title { font-size: 1.45rem; font-weight: 900; color: var(--ink); line-height: 1.4; }
.feature-text { font-size: 0.92rem; color: var(--ink-2); line-height: 1.8; margin-top: 8px; }
.feature-page { font-size: 0.8rem; color: var(--brand); margin-top: 10px; font-weight: 500; }
.headline-item { border-bottom: 1px solid var(--line); padding: 8px 2px 4px 2px; }
.headline-item .hp { font-size: 0.74rem; color: var(--brand); font-weight: 700; }
.headline-item .ht { font-size: 0.92rem; color: var(--ink); line-height: 1.55; }

/* ===== 簡單的立體感（使用者 2026-11-02 要求）=====
   做法：只用「底下一條實心陰影＋很淡的投影」，像實體按鍵；不用漸層、不發光。
   按鈕：平常浮起 3px，滑鼠移上去再浮 1px，按下去整顆往下壓、陰影消失，點了有沒有反應一眼就知道。
   卡片、圖表外框、表格：只加一層很淡的投影，和底色分開，不搶資料的目光。 */
:root { --key-edge: #d4cde3; --key-edge-brand: #4c1d95; --lift: 0 6px 14px -10px rgba(40,24,80,0.45); }
[data-testid="stMain"] .stButton > button,
[data-testid="stMain"] .stDownloadButton > button {
  background: #ffffff; border: 1px solid var(--key-edge) !important; color: var(--ink);
  box-shadow: 0 3px 0 var(--key-edge), var(--lift); transform: translateY(0);
  transition: transform 0.08s ease, box-shadow 0.08s ease, border-color 0.15s ease; }
[data-testid="stMain"] .stButton > button:hover,
[data-testid="stMain"] .stDownloadButton > button:hover {
  border-color: #b9a6ee !important; transform: translateY(-1px);
  box-shadow: 0 4px 0 #b9a6ee, 0 8px 16px -10px rgba(40,24,80,0.5); }
[data-testid="stMain"] .stButton > button:active,
[data-testid="stMain"] .stDownloadButton > button:active {
  transform: translateY(3px); box-shadow: 0 0 0 var(--key-edge); }
/* 主要按鈕（紫底白字）：底下一條深紫，像按鍵的側面 */
[data-testid="stMain"] [data-testid="stBaseButton-primary"] {
  background: var(--brand) !important; color: #ffffff !important; border-color: var(--brand) !important;
  box-shadow: 0 2px 0 rgba(76,29,149,0.45), 0 4px 10px -8px rgba(40,24,80,0.4) !important; }
[data-testid="stMain"] [data-testid="stBaseButton-primary"] p { color: #ffffff !important; }
[data-testid="stMain"] [data-testid="stBaseButton-primary"]:hover { background: #6d28d9 !important;
  box-shadow: 0 2px 0 rgba(76,29,149,0.5), 0 6px 12px -8px rgba(40,24,80,0.45) !important; }
[data-testid="stMain"] [data-testid="stBaseButton-primary"]:active { transform: translateY(2px);
  box-shadow: 0 0 0 rgba(76,29,149,0) !important; }
/* 首頁「本週發現」下面的按鈕：和卡片拉開一點距離 */
.st-key-feat_go { margin-top: 14px; }
/* 文字型按鈕（首頁重點發現的「前往 →」）維持平的，像連結 */
[data-testid="stMain"] [data-testid="stBaseButton-tertiary"] {
  background: transparent !important; border: none !important; box-shadow: none !important; color: var(--brand) !important; }
/* 膠囊、分段選擇：小一號的按鍵；選到的那顆「按下去」（陰影變內凹），一眼看出選了哪個 */
[data-testid="stBaseButton-pills"], [data-testid="stBaseButton-segmented_control"] {
  background: #ffffff; box-shadow: 0 2px 0 var(--key-edge); transition: transform 0.08s ease, box-shadow 0.08s ease; }
[data-testid="stBaseButton-pills"]:hover, [data-testid="stBaseButton-segmented_control"]:hover { transform: translateY(-1px); }
[data-testid="stBaseButton-pillsActive"], [data-testid="stBaseButton-segmented_controlActive"] {
  transform: translateY(2px); box-shadow: inset 0 2px 3px rgba(76,29,149,0.18) !important; font-weight: 700; }
/* 卡片、數字卡、圖表、表格、可點開區塊：一層很淡的投影，浮在底色上 */
.card, .kpi, .feature, .hypo, .toc, .ntable,
[data-testid="stPlotlyChart"], [data-testid="stExpander"], [data-testid="stVerticalBlockBorderWrapper"] {
  box-shadow: 0 1px 0 rgba(40,24,80,0.04), var(--lift); }
.card:hover { transform: translateY(-2px); box-shadow: 0 2px 0 rgba(40,24,80,0.04), 0 12px 22px -12px rgba(76,29,149,0.45); }
.card { transition: transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease; }
/* 左側黑色選單：目前所在頁面像「被按下去」的按鍵 */
section[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] { box-shadow: inset 0 2px 4px rgba(0,0,0,0.45) !important; }
section[data-testid="stSidebar"] .stButton > button:active { transform: translateY(1px); }
</style>
""", unsafe_allow_html=True)


def kpi(col, label, value, sub=""):
    col.markdown(f'<div class="kpi"><div class="kpi-label">{label}</div>'
                 f'<div class="kpi-value">{value}</div><div class="kpi-sub">{sub}</div></div>',
                 unsafe_allow_html=True)


def hypothesis(question, guess):
    """每頁開頭的小卡：這頁要驗證的問題與假設（老師要的「先提出假設」）"""
    st.markdown(f'<div class="hypo"><div><span class="hypo-k">問題</span>{question}</div>'
                f'<div><span class="hypo-k">假設</span>{guess}</div></div>', unsafe_allow_html=True)


def hypo_only(guess):
    """題目下方的「假設」小卡（冠軍密碼每一題用；1030-12）"""
    st.markdown(f'<div class="hypo"><div><span class="hypo-k" style="background:var(--brand)">假設</span>{guess}</div></div>',
                unsafe_allow_html=True)


def section(title, sub="", anchor=None, level=1):
    """區塊標題＋一行說明；回傳一個緊接在標題下方的空位，之後可以把「發現／結論」放進去（先讀結論再看圖）
    說明超過 40 字時，只留第一句當副標，完整說明收進可點開的「怎麼讀這張圖」（1030-3）
    anchor：給本頁目錄跳轉用的錨點；level=2 是小一級的標題（例如 3-1、3-2）"""
    short, full = sub, ""
    if len(_plain(sub)) > 40:
        parts = re.split(r"(?<=[。；])|　", sub, maxsplit=1)
        short, full = parts[0].strip().rstrip("；。"), sub
    aid = f' id="{anchor}"' if anchor else ""
    cls = "section-title" + (" sub2" if level == 2 else "")
    st.markdown(f'<div class="{cls}"{aid}>{title}</div>'
                f'<div class="section-sub">{short}</div>', unsafe_allow_html=True)
    if full:
        how_read(full)
    return st.container()


def _plain(s):
    """拿掉 <b> 這類 HTML 標籤，只留文字"""
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def how_read(text, where=None):
    """長的讀法收進可點開的說明（1030-3），畫面不會被一大段字塞滿"""
    with (where or st).expander("怎麼讀這張圖"):
        st.markdown(f'<div class="howread">{text}</div>', unsafe_allow_html=True)


# ---------- 「發現／結論」框＋頁首摘要（1030-1、1030-3、1030-12）----------
PAGE_FINDINGS = []      # 這一頁所有「發現」的第一句，整頁畫完後放進頁首的摘要
NOTE_WORDS = ("尚未", "還沒", "沒有資料", "請先", "請把", "資料不足", "無法計算", "算不出來")


def insight(lines=None, where=None, label="發現", to_summary=True, headline=True, check=None):
    """「發現／結論」框。
    - 第一句自動放大成圖上方的標題（圖的標題直接寫發現）；其餘句子留在框裡
    - 「讀法：…」開頭的句子收進可點開的「怎麼讀這張圖」
    - check：對照假設，說明假設成立與否（冠軍密碼等頁使用）
    - 第一句同時收進頁首「摘要」；「資料還沒載入」這類提示不會被當成標題或摘要"""
    lines = [x for x in (lines or []) if x]
    if not lines and not check:
        return
    host = where or st
    reads = [x for x in lines if _plain(x).startswith("讀法：")]
    lines = [x for x in lines if x not in reads]
    first = _plain(re.sub(r"</b>：", "</b>，", lines[0])) if lines else ""
    is_note = (not first) or any(w in first[:16] for w in NOTE_WORDS)
    body = lines
    if headline and not is_note:
        host.markdown(f'<div class="chart-headline">{first}</div>', unsafe_allow_html=True)
        body = lines[1:]
    if check:
        body = body + [f'<span class="check-k">對照假設</span>{check}']
    if body:
        host.markdown(f'<div class="insight"><span class="insight-k">{label}</span>'
                      + "<br>".join(body) + "</div>", unsafe_allow_html=True)
    if reads:
        how_read("<br>".join(_plain(x)[3:] for x in reads), where=host)
    if to_summary and not is_note:
        PAGE_FINDINGS.append(first)


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
    st.markdown(f'<div style="overflow-x:auto"><table class="ntable"><thead><tr>{head}</tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table></div>', unsafe_allow_html=True)


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
def read_stats(name, order_cols):
    """先讀「預先算好的彙總表」（_mv，很快）；還沒建立的話，退回原本的檢視表（比較慢）"""
    try:
        df = fetch_all(f"{name}_mv", order_cols)
        if not df.empty:
            return df
    except Exception:
        pass
    return fetch_all(name, order_cols)


def load_data():
    team = read_stats("team_season_stats", ["team_id", "season", "season_type"])
    players = read_stats("player_season_stats", ["team_id", "season", "season_type", "player_id"])
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
    for c_, src in [("spg", "stl"), ("bpg", "blk"), ("topg", "tov")]:
        if src in d.columns:
            d[c_] = d[src] / n
    if "min" in d.columns:
        d["mpg"] = d["min"] / n
    if "wins" in d.columns:
        d["win_pct"] = d["wins"] / n
    num = ["ts", "fg_pct", "tpar", "fg3_pct", "ppg", "fga_pg", "fg3a_pg", "apg", "rpg",
           "ast_tov", "mpg", "win_pct", "spg", "bpg", "topg", games_col]
    for c in [c for c in num if c in d.columns]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


# ---------- 跑動距離、全部球隊逐場輸贏（跑動距離、賽程與休息、主場與客場、首頁共用）----------
KM = 1.609   # 1 英里 = 1.609 公里


@st.cache_data(ttl=3600, show_spinner="讀取跑動數據中…")
def load_tracking(entity):
    """tracking_speed：entity = 'team'（30 隊）或 'player'（所有球員），每場平均跑動距離與速度"""
    try:
        return fetch_all_filtered("tracking_speed", [("eq", "entity", entity)], ["season", "season_type", "id"])
    except Exception:
        return pd.DataFrame()


def fetch_all_filtered(table, filters, order_cols, page=1000):
    """和 fetch_all 一樣一頁一頁讀，但先在資料庫篩選（例如只要球隊、不要球員）"""
    rows, start = [], 0
    while True:
        q = get_client().table(table).select("*")
        for op, col, val in filters:
            q = getattr(q, op)(col, val)
        for c in order_cols:
            q = q.order(c)
        part = q.range(start, start + page - 1).execute().data
        rows += part
        if len(part) < page:
            break
        start += page
    return pd.DataFrame(rows)


def prep_tracking(tr, league_tbl):
    """整理跑動數據：英里換公里、配上勝率、同季排名與「比同季聯盟多多少」"""
    if tr.empty:
        return tr
    d = tr.copy()
    for c in ["gp", "min", "dist_miles", "dist_miles_off", "dist_miles_def", "avg_speed", "avg_speed_off", "avg_speed_def"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["id"] = pd.to_numeric(d["id"], errors="coerce")
    d["dist_km"] = d["dist_miles"] * KM
    for c in ["avg_speed", "avg_speed_off", "avg_speed_def"]:
        d[c.replace("avg_speed", "spd")] = d[c] * KM
    if not league_tbl.empty:
        lg = league_tbl[["season", "season_type", "team_id", "gp", "w", "abbreviation"]].copy()
        lg["team_id"] = pd.to_numeric(lg["team_id"], errors="coerce")
        lg["win_pct"] = pd.to_numeric(lg["w"], errors="coerce") / pd.to_numeric(lg["gp"], errors="coerce").replace(0, pd.NA)
        d = d.merge(lg[["season", "season_type", "team_id", "win_pct", "abbreviation"]].rename(columns={"team_id": "id"}),
                    on=["season", "season_type", "id"], how="left")
    else:
        d["win_pct"], d["abbreviation"] = float("nan"), None
    d["win_pct"] = pd.to_numeric(d["win_pct"], errors="coerce")
    keys = ["season", "season_type"]
    for col, _ in TRACK_OPTS.values():
        d[f"rk_{col}"] = d.groupby(keys)[col].rank(ascending=False, method="min")
        d[f"d_{col}"] = d[col] - d.groupby(keys)[col].transform("mean")
    d["rk_win"] = d.groupby(keys)["win_pct"].rank(ascending=False, method="min")
    d["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(d["season"], d["abbreviation"])]
    return d


RECENT = "2018-19"   # 2019 年起連續 8 年不同冠軍（首頁與冠軍密碼共用）

# 跑動指標：顯示名稱 →（欄位, 單位）
TRACK_OPTS = {"每場跑動距離": ("dist_km", "公里"), "平均速度": ("spd", "公里／小時"),
              "進攻時速度": ("spd_off", "公里／小時"), "防守時速度": ("spd_def", "公里／小時")}


@st.cache_data(ttl=3600, show_spinner="讀取各隊逐場輸贏中…（球隊越多越久，約 10～30 秒）")
def load_team_games_all(team_ids):
    """已載入球隊的每一場比賽：日期、球季、比賽類型、主客場、輸贏。一隊一隊讀，每隊約 2,000 場"""
    out = []
    for tid in team_ids:
        start, page = 0, 1000
        try:
            while True:
                part = (get_client().table("team_games")
                        .select("game_id,team_id,is_home,wl,matchup,games!inner(game_date,season,season_type)")
                        .eq("team_id", int(tid)).order("game_id")
                        .range(start, start + page - 1).execute().data)
                out += part
                if len(part) < page:
                    break
                start += page
        except Exception:
            continue
    if not out:
        return pd.DataFrame()
    df = pd.json_normalize(out).rename(columns=lambda c: c.replace("games.", ""))
    df["game_date"] = pd.to_datetime(df["game_date"], errors="coerce")
    df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce")
    return df


def team_games_with_abbr():
    """load_team_games_all 加上球隊代號、是否奪冠球季、輸贏 1/0"""
    ids = team_raw[["team_id", "abbreviation"]].drop_duplicates()
    ids["team_id"] = pd.to_numeric(ids["team_id"], errors="coerce")
    d = load_team_games_all(tuple(sorted(ids["team_id"].dropna().astype(int))))
    if d.empty:
        return d
    d = d.merge(ids, on="team_id", how="left")
    d["win"] = (d["wl"] == "W").astype(int)
    d["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(d["season"], d["abbreviation"])]
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
# ZheN 標誌：黑底方塊裡一個粗體白色 Z，Z 的底邊接著兩根往上長的紫色長條（數據成長），原始檔在 docs/logo/
LOGO_B64 = "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCIgdmlld0JveD0iMCAwIDQwIDQwIj4gPHJlY3QgeD0iMC43NSIgeT0iMC43NSIgd2lkdGg9IjM4LjUiIGhlaWdodD0iMzguNSIgcng9IjciIGZpbGw9IiMwZDBhMTQiIHN0cm9rZT0iIzdjM2FlZCIgc3Ryb2tlLXdpZHRoPSIxLjUiLz4gPHBvbHlnb24gcG9pbnRzPSI4LDggMzIsOCAzMiwxMy41IDgsMTMuNSIgZmlsbD0iI2ZmZmZmZiIvPiA8cG9seWdvbiBwb2ludHM9IjI1LjUsMTMuNSAzMiwxMy41IDE0LjUsMjcuNSA4LDI3LjUiIGZpbGw9IiNmZmZmZmYiLz4gPHJlY3QgeD0iOCIgeT0iMjcuNSIgd2lkdGg9IjYuNSIgaGVpZ2h0PSI0LjUiIGZpbGw9IiNmZmZmZmYiLz4gPHJlY3QgeD0iMTYuNzUiIHk9IjIyLjUiIHdpZHRoPSI2LjUiIGhlaWdodD0iOS41IiBmaWxsPSIjOGI1Y2Y2Ii8+IDxyZWN0IHg9IjI1LjUiIHk9IjE3IiB3aWR0aD0iNi41IiBoZWlnaHQ9IjE1IiBmaWxsPSIjOGI1Y2Y2Ii8+IDwvc3ZnPg=="

# （群組, 頁面名稱, 這頁回答的問題, 卡片說明, 這頁要用到哪些篩選）
PAGES = [
    ("每日戰報", "每日戰報", "昨晚發生什麼事？",
     "下一場勝率與球員預估、全聯盟比分卡、值得關注的球員、球隊隱憂與東西區戰績榜，每天自動更新。", set()),
    ("奪冠列車", "奪冠列車", "今年誰最像冠軍？",
     "用歷屆冠軍的六項標準（進攻、防守、三分、籃板、助攻、失誤）衡量本季 30 隊：冠軍指數、雷達圖、最像哪一位冠軍。", set()),
    ("焦點人物", "焦點人物", "本季誰最值得看？",
     "爆發中、不可或缺、關鍵先生：用數據挑出本季的人物；每位球員有雷達圖，點開看完整的傳統與進階數據。", set()),
    ("冠軍故事", "冠軍密碼", "奪冠最需要什麼？",
     "冠軍在攻守效率、三分、籃板等 10 項指標排聯盟第幾；三分時代與冠軍輪替。", {"season"}),
    ("冠軍故事", "投籃分布", "冠軍從哪裡出手？",
     "每一位冠軍 vs 同季聯盟的出手選擇；單一球隊的半場球場圖；跨球季的變化。", set()),
    ("冠軍故事", "戰術使用", "冠軍靠什麼戰術得分？",
     "戰術地圖、八位冠軍的共同點、全聯盟各隊比較與奪冠方程式。", set()),
    ("冠軍故事", "上場陣容", "冠軍的核心五人是誰？",
     "哪一組 5 人同時在場最久、淨效率多高；每位冠軍都靠一組固定核心嗎？", set()),
    ("冠軍故事", "跑動距離", "冠軍跑得比較多嗎？",
     "各隊每場跑幾公里、跑多快；冠軍在聯盟排第幾，跑得多和贏球有沒有關係，隊上誰跑最多。", set()),
    ("冠軍故事", "籤運與傷兵", "冠軍是不是靠運氣？",
     "冠軍的季後賽對手比一般季後賽球隊弱嗎？遇到的是不是剛好都打得贏？對手主力缺陣有沒有特別多？", set()),
    ("冠軍故事", "賽程與休息", "背靠背會不會輸比較多？",
     "休息 0、1、2、3 天以上的勝率；每位冠軍背靠背 vs 有休息；聯盟背靠背是不是越來越少。", set()),
    ("冠軍故事", "主場與客場", "冠軍的主場優勢比較大嗎？",
     "主場勝率 − 客場勝率：冠軍 vs 其他球隊、主場優勢是不是一年比一年小、冠軍在季後賽客場的戰績。", set()),
    ("冠軍故事", "例行賽與季後賽", "球星進季後賽會更強嗎？",
     "冠軍的頭號球星進季後賽後，得分、上場時間、真實命中率怎麼變；和其他季後賽球隊的球星比較。", set()),
    ("冠軍故事", "得分穩定度", "冠軍球星比較不會爆冷嗎？",
     "每場得分的起伏：冠軍頭號球星和同得分水準的球員比，是不是比較穩定、低迷場比較少。", set()),
    ("冠軍故事", "月份趨勢", "冠軍是不是越打越好？",
     "每個月的勝率、前半季 vs 後半季：冠軍和同樣強的其他球隊，誰在季末比較強。", set()),
    ("冠軍故事", "贏球與輸球", "冠軍輸球時哪裡掉最多？",
     "贏球場 vs 輸球場：命中率、失誤、籃板…哪一項差最多；每一位冠軍都是投不進就輸嗎？", set()),
    ("冠軍故事", "防守端", "冠軍的防守強在哪裡？",
     "讓對手投不準、逼失誤、還是搶籃板？冠軍在每一項防守排聯盟第幾，哪一項最影響防守好壞。", set()),
    ("冠軍故事", "奪冠隔年", "冠軍隔年還強嗎？",
     "冠軍拿到冠軍的隔年，淨效率掉多少；和同樣強的其他球隊比，冠軍是不是特別掉；誰衛冕成功。", set()),
    ("冠軍故事", "輸球之後", "冠軍輸球後會馬上反彈嗎？",
     "輸球後下一場的勝率、整季最長連敗：冠軍和其他強隊比；扣掉下一場的對手強弱與主客場再比一次。", set()),
    ("冠軍故事", "節奏與勝率", "打得快的隊比較會贏嗎？",
     "冠軍的節奏排聯盟第幾、全聯盟節奏和勝率有沒有關係、進了季後賽會不會變慢。", set()),
    ("冠軍故事", "奪冠前一季", "冠軍是突然變強的嗎？",
     "奪冠那一季比前一季進步在哪裡：前一季就是強隊嗎？進步來自進攻還是防守？哪一項排名進步最多？", set()),
    ("冠軍故事", "陣容深度", "冠軍的得分靠幾個人？",
     "頭號、第 2、第 3 得分手各佔全隊得分幾成；冠軍 vs 其他強隊、得分分散和勝率、進了季後賽是不是更依賴球星。", set()),
    ("冠軍故事", "季後賽輪次", "冠軍哪一輪打得最辛苦？",
     "首輪、次輪、分區決賽、總冠軍賽：冠軍每一輪打幾場、有沒有被逼到第 7 戰，和同一輪的其他晉級球隊比。", set()),
    ("冠軍故事", "頭號得分手缺陣", "少了頭號得分手還贏得了嗎？",
     "頭號得分手沒上場的比賽，冠軍、其他強隊、其他球隊的勝率各掉多少；每一位冠軍有他 vs 缺陣。", set()),
    ("冠軍故事", "輸球時的球星", "冠軍輸球，是球星失常嗎？",
     "冠軍輸球的那幾場，頭號得分手和其他隊友各少得幾分；和其他強隊比，冠軍的球星是不是比較不會一起倒。", set()),
    ("冠軍故事", "缺陣場的對手", "少了球星時，對手比較弱嗎？",
     "頭號得分手缺陣的那幾場，遇到的對手是不是比較弱；扣掉對手強弱後，少了他勝率掉多少。", set()),
    ("冠軍故事", "誰補上得分", "少了頭號得分手，誰補上得分？",
     "頭號得分手缺陣時，第 2 號、第 3 號得分手和其他隊友每場多得幾分、補回幾成；冠軍和其他強隊比。", set()),
    ("冠軍故事", "每一輪的球星", "球星越到後面越強嗎？",
     "冠軍的頭號得分手在首輪、次輪、分區決賽、總冠軍賽，得分、命中率、上場時間怎麼變；和同一輪的其他晉級球隊比較。", set()),
    ("冠軍故事", "對手防守與球星", "遇到防守強的對手，球星掉比較多嗎？",
     "每一輪季後賽對手的例行賽防守排名，和頭號得分手這一輪的命中率掉多少；冠軍 vs 其他晉級球隊；越後面越難投是不是因為對手越會守。", set()),
    ("冠軍故事", "二號與三號得分手", "越往後，誰站出來？",
     "季後賽每一輪，頭號、第 2、第 3 號得分手比自己例行賽變多少；頭號被守住時，配角有沒有補上。", set()),
    ("冠軍故事", "系列賽主場優勢", "有主場優勢的一方比較常晉級嗎？",
     "季後賽各輪有主場優勢一方的晉級比例、搶七；每位冠軍哪幾輪有主場優勢；同樣兩隊在主場和客場的單場勝率差。", set()),
    ("冠軍故事", "季末輪休", "季末最後 10 場，主力真的在休息嗎？",
     "最後 10 場的前 3 號主力缺陣比例、上場分鐘、上場人數、勝率；冠軍和其他強隊比；只看主力全員上場時，季末下滑還在嗎。", set()),
    ("資料與探索", "球季趨勢", "各隊一路怎麼變化？",
     "選一個指標，看各隊 20 季的折線；可聚焦幾支球隊，其他變灰。", {"team", "season", "type", "metric"}),
    ("資料與探索", "球隊 × 球季", "哪隊在哪季特別突出？",
     "熱力圖一次看完所有球隊、所有球季，顏色越深越高，★ 是奪冠季。", {"team", "season", "type", "metric"}),
    ("資料與探索", "冠軍球季比較", "奪冠那季比平常強多少？",
     "每支冠軍隊的奪冠球季，和它其他球季的平均差多少。", {"team", "season", "type", "metric"}),
    ("資料與探索", "球員", "誰是冠軍的關鍵球員？",
     "球員在隊上的逐季變化、出手量 vs 效率、單季逐場數據。", {"team", "season", "type"}),
    ("資料與探索", "數據表", "原始數字與下載",
     "球隊 × 球季的完整數字，可以排序、下載 Excel。", {"team", "season", "type"}),
]
# 冠軍故事的 28 頁分成 5 章（2026-11-23 改版：左側 35 個按鈕合併成 6 個入口）
CHAPTERS = {
    "奪冠關鍵": ["冠軍密碼", "防守端", "贏球與輸球"],
    "進攻與投籃": ["投籃分布", "戰術使用", "節奏與勝率"],
    "球星與陣容": ["上場陣容", "陣容深度", "頭號得分手缺陣", "缺陣場的對手", "誰補上得分", "輸球時的球星",
               "二號與三號得分手", "得分穩定度", "例行賽與季後賽", "每一輪的球星", "對手防守與球星"],
    "賽程與狀態": ["賽程與休息", "主場與客場", "月份趨勢", "輸球之後", "季末輪休", "跑動距離"],
    "季後賽之路": ["季後賽輪次", "系列賽主場優勢", "籤運與傷兵", "奪冠前一季", "奪冠隔年"],
}
CHAPTER_OF = {pg: ch for ch, pgs in CHAPTERS.items() for pg in pgs}
# 依章節重新排序（上一頁／下一頁也照這個順序走）；章節裡沒列到的頁放在冠軍故事最後
_story = [p for p in PAGES if p[0] == "冠軍故事"]
_story.sort(key=lambda p: [pg for pgs in CHAPTERS.values() for pg in pgs].index(p[1]) if p[1] in CHAPTER_OF else 999)
PAGES = [p for p in PAGES if p[0] != "冠軍故事" and p[0] != "資料與探索"] + _story + [p for p in PAGES if p[0] == "資料與探索"]
PAGE_INFO = {p[1]: p for p in PAGES}
HOME = "首頁"
# 左側的 6 個入口：（顯示名稱, 點了去哪一頁）
NAV = [("首頁", HOME), ("每日戰報", "每日戰報"), ("奪冠列車", "奪冠列車"), ("焦點人物", "焦點人物"),
       ("冠軍故事", "冠軍密碼"), ("資料與探索", "球季趨勢")]


def nav_of(page):
    """這一頁屬於左側哪一個入口"""
    return "首頁" if page == HOME else PAGE_INFO[page][0]


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
    for label, target in NAV:     # 6 個入口；目前所在的入口亮紫色
        st.button(label, key=f"nav_{label}", width="stretch", on_click=goto, args=(target,),
                  type="primary" if nav_of(PAGE) == label else "secondary")
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
  <h1>ZheN NBA 數據分析</h1>
  <div class="hero-sub">本季誰會奪冠？用歷屆冠軍留下的數據標準，每天說本季的故事。</div>
  <span class="chip">{ALL_SEASONS[0]} – {ALL_SEASONS[-1]}</span>
  <span class="chip">資料更新至 {latest_game_date() or '未知'}</span>
  <span class="chip">資料庫已有 {len(ALL_TEAMS) + len(EXTRA_TEAMS)} / 30 隊</span>
</div>
""", unsafe_allow_html=True)
else:
    grp, name, question, *_ = PAGE_INFO[PAGE]
    crumb = f"{grp}　／　{CHAPTER_OF[name]}　／　{name}" if name in CHAPTER_OF else (
        f"{grp}　／　{name}" if grp != name else grp)
    st.markdown(f'<div class="pagehead"><div class="crumb">{crumb}</div>'
                f'<h2>{name}</h2><div class="pq">{question}</div></div>', unsafe_allow_html=True)

    def _pick(key):
        """章節或頁面按鈕被點了：切到那一頁"""
        v = st.session_state.get(key)
        if v:
            goto(CHAPTERS[v][0] if v in CHAPTERS else v)

    if grp == "冠軍故事":
        ch_now = CHAPTER_OF.get(name, list(CHAPTERS)[0])
        try:
            st.pills("章節", list(CHAPTERS), selection_mode="single", default=ch_now,
                     key=f"chap_{name}", on_change=_pick, args=(f"chap_{name}",))
            st.pills(f"「{ch_now}」的 {len(CHAPTERS[ch_now])} 頁", CHAPTERS[ch_now], selection_mode="single",
                     default=name, key=f"chpg_{name}", on_change=_pick, args=(f"chpg_{name}",))
        except AttributeError:   # 舊版 Streamlit 沒有 pills
            pass
    elif grp == "資料與探索":
        opts = [p[1] for p in PAGES if p[0] == "資料與探索"]
        try:
            st.pills("頁面", opts, selection_mode="single", default=name, key=f"expg_{name}",
                     on_change=_pick, args=(f"expg_{name}",))
        except AttributeError:
            pass
SUMMARY_SLOT = st.container() if PAGE != HOME else None   # 頁首摘要的空位（1030-1），整頁畫完才填


def split_teams(available, s_from, s_to):
    """把球隊分成「這段期間拿過冠軍」和「其他球隊」兩區（冠軍隊排前面，依奪冠年份）"""
    won = {}
    for s_, a_ in CHAMP_SET:
        if s_from <= s_ <= s_to and a_ in available:
            won.setdefault(a_, s_)
            won[a_] = min(won[a_], s_)
    champs_ = sorted(won, key=lambda a_: won[a_])
    others_ = [a_ for a_ in available if a_ not in won]
    return champs_, others_


def team_picker(s_from, s_to, current):
    """多選：冠軍隊一區、其他球隊一區，兩區各自勾選、互不影響；年份範圍一改，兩區的球隊跟著換"""
    champs_, others_ = split_teams(ALL_TEAMS + EXTRA_TEAMS, s_from, s_to)
    k = f"{s_from}_{s_to}"   # 年份改了，選項就換一組
    sel_c = pills(f"奪冠球隊（{s_from}～{s_to} 拿過冠軍，{len(champs_)} 隊）", champs_, f"w_tc_{k}",
                  default=[a_ for a_ in current if a_ in champs_], multi=True, format_func=team_label) if champs_ else []
    if others_:
        sel_o = pills(f"其他球隊（這段期間沒有奪冠，{len(others_)} 隊）", others_, f"w_to_{k}",
                      default=[a_ for a_ in current if a_ in others_], multi=True, format_func=team_label)
    else:
        sel_o = []
    n_left = 30 - len(ALL_TEAMS) - len(EXTRA_TEAMS)
    if n_left > 0:
        st.caption(f"資料庫目前有 {30 - n_left} 隊的球員逐場數據，還有 {n_left} 隊每天陸續載入中。")
    return sel_c + sel_o


def _clear(key):
    st.session_state[key] = None


def team_picker_one(champs_, others_, key, champ_label, other_label):
    """單選版：兩區各一排按鈕，點了其中一區，另一區的選取會自動取消，所以永遠只選一隊"""
    kc, ko = f"{key}_c", f"{key}_o"
    if st.session_state.get(kc) is None and st.session_state.get(ko) is None and champs_:
        st.session_state[kc] = champs_[0]   # 第一次打開：預設選第一支冠軍隊
    try:
        a = st.pills(champ_label, champs_, selection_mode="single", key=kc, format_func=team_label,
                     on_change=_clear, args=(ko,))
        b = st.pills(other_label, others_, selection_mode="single", key=ko, format_func=team_label,
                     on_change=_clear, args=(kc,)) if others_ else None
    except AttributeError:   # 舊版 Streamlit 沒有 pills
        allt = champs_ + others_
        return st.selectbox(champ_label, allt, format_func=team_label, key=key)
    return a or b or (champs_[0] if champs_ else others_[0])


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
        # 先選年份與條件，球隊再依「這段期間有沒有奪冠」分成兩區
        f1, f2 = st.columns([3, 2])
        if "season" in NEED:
            with f1:
                s_from, s_to = st.select_slider("球季範圍", ALL_SEASONS, value=(s_from, s_to), key="w_range")
        if "type" in NEED:
            with f2:
                types_sel = pills("比賽類型", list(TYPE_OPTIONS), "w_types", default=types_sel, multi=True)
        if "metric" in NEED:   # 指標按鈕很多，放獨立一整排，才不會被切掉
            metric_name = pills(f"比較指標（{len(METRICS)} 項）", list(METRICS), "w_metric", default=metric_name)
        if "team" in NEED:
            teams_sel = team_picker(s_from, s_to, teams_sel)
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
# 本季模組（2026-11-23 改版）：首頁本季故事、奪冠列車、焦點人物共用
# 讀資料庫 → 交給 season_stats.py 算 → 這裡只負責畫圖和排版
# =====================================================================
SEASON_GREY = "#d9d4e3"     # 本季圖表裡「其他」的顏色：淡灰，讓主角的紫色跳出來
CHAMP_LINE = "#8f889f"      # 歷屆冠軍平均：灰色虛線


def _rf(table, filters, order, page=1000):
    """分頁讀取＋篩選（本季模組用）；資料表不存在或連線出錯時回傳空表格"""
    rows, start = [], 0
    try:
        while True:
            q = get_client().table(table).select("*")
            for op, col, val in filters:
                q = getattr(q, op)(col, val)
            for c in order:
                q = q.order(c)
            part = q.range(start, start + page - 1).execute().data
            rows += part
            if len(part) < page:
                break
            start += page
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


@st.cache_data(ttl=900)
def cur_season():
    """資料庫裡最新的球季，例如 2025-26"""
    try:
        r = get_client().table("recap_team_games").select("season").order("season", desc=True).limit(1).execute().data
        return r[0]["season"] if r else None
    except Exception:
        return None


@st.cache_data(ttl=900, show_spinner="讀取本季比賽中…")
def cur_team_games(season):
    df = _rf("recap_team_games", [("eq", "season", season)], ["game_date", "game_id", "team_id"])
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


@st.cache_data(ttl=900, show_spinner="讀取本季球員數據中…（一季約幾千筆）")
def cur_player_games(season):
    df = _rf("recap_player_games", [("eq", "season", season)], ["game_date", "game_id", "player_id"])
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


@st.cache_data(ttl=900, show_spinner="讀取關鍵時刻得分中…")
def cur_clutch(season):
    return _rf("pbp_events", [("eq", "season", season), ("eq", "is_clutch", True)], ["game_id", "action_number"])


@st.cache_data(ttl=900, show_spinner="讀取未來賽程中…")
def cur_schedule(season):
    """recap_schedule：接下來 7 天的賽程（load_recap.py 每天寫入）；表不存在時回傳空表格"""
    df = _rf("recap_schedule", [("eq", "season", season)], ["game_date", "game_id"])
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def season_data():
    """本季的所有表格，一次準備好；資料庫還沒有本季資料、或計算出錯時回傳 None（頁面改顯示提示，不會整頁壞掉）"""
    try:
        return _season_data()
    except Exception as e:   # 不讓本季模組的錯誤拖垮整個網站
        st.caption(f"本季數據暫時算不出來：{type(e).__name__}")
        return None


def _season_data():
    season = cur_season()
    if not season:
        return None
    tg = cur_team_games(season)
    if tg.empty:
        return None
    teams_ = ss.team_table(tg)
    champs_p, champ_avg = ss.champion_profiles(league, champs)
    teams_["champ_idx"] = ss.champion_index(teams_, champ_avg)
    pg = cur_player_games(season)
    players_ = ss.player_table(pg, tg) if not pg.empty else pd.DataFrame()
    n_games = tg["game_id"].nunique()
    return {"season": season, "tg": tg, "pg": pg, "teams": teams_, "champs_p": champs_p, "champ_avg": champ_avg,
            "players": players_, "n_games": n_games, "last_day": tg["game_date"].max()}


def zh(abbr):
    return ALL_ZH.get(abbr, abbr)


def radar(traces, height=400):
    """六角雷達圖：traces＝[(名稱, 六個 0～100 的值, 顏色, 線型, 要不要填色)]；外圈＝聯盟最好"""
    fig = go.Figure()
    for name, vals, color, dash, fill in traces:
        labels = [a[0] for a in ss.TEAM_AXES]
        v = [float(x) if pd.notna(x) else 0 for x in vals]
        fig.add_trace(go.Scatterpolar(
            r=v + v[:1], theta=labels + labels[:1], name=name, mode="lines+markers",
            line=dict(color=color, width=3 if fill else 2, dash=dash),
            marker=dict(size=6 if fill else 4, color=color),
            fill="toself" if fill else None, fillcolor="rgba(124,58,237,0.16)" if fill else None,
            hovertemplate=name + "<br>%{theta}：贏過聯盟 %{r:.0f}%<extra></extra>"))
    fig.update_layout(polar=dict(
        bgcolor="rgba(0,0,0,0)",
        radialaxis=dict(range=[0, 100], tickvals=[25, 50, 75, 100], ticktext=["", "中間", "", "最好"],
                        tickfont=dict(size=10, color=MUTED), gridcolor=GRID, linecolor=GRID, angle=90),
        angularaxis=dict(tickfont=dict(size=15, color=INK), gridcolor=GRID, linecolor=GRID, direction="clockwise")))
    fig = style(fig, height)
    fig.update_layout(legend=dict(orientation="h", y=-0.08, x=0.5, xanchor="center"), margin=dict(l=40, r=40, t=24, b=24))
    return fig


def hbar(labels, values, colors, texts, height, xtitle="", xfmt=None, zero=False):
    """橫向長條圖：主角紫色、其他灰色，數字直接寫在長條旁邊（不用看座標軸）"""
    fig = go.Figure(go.Bar(y=labels, x=values, orientation="h", marker_color=colors, text=texts,
                           textposition="outside", cliponaxis=False, hoverinfo="skip"))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=13, color=INK))
    fig.update_xaxes(title=xtitle, showticklabels=False)
    if zero:
        fig.add_vline(x=0, line=dict(color=MUTED, width=1))
    fig = style(fig, height)
    fig.update_layout(margin=dict(l=8, r=60, t=8, b=8), showlegend=False)
    return fig


def dumbbell(labels, a, b, a_name, b_name, height, unit=""):
    """啞鈴圖：灰點＝平常（a）、紫點＝現在（b），中間連一條線；一眼看出變多少"""
    fig = go.Figure()
    for i, (lb, x0, x1) in enumerate(zip(labels, a, b)):
        fig.add_trace(go.Scatter(x=[x0, x1], y=[lb, lb], mode="lines", line=dict(color=SEASON_GREY, width=6),
                                 showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=a, y=labels, mode="markers", name=a_name, marker=dict(size=13, color="#b8b2c6"),
                             hovertemplate="%{y}<br>" + a_name + "：%{x:.1f}" + unit + "<extra></extra>"))
    fig.add_trace(go.Scatter(x=b, y=labels, mode="markers+text", name=b_name, marker=dict(size=15, color=ACCENT),
                             text=[f"{x:.1f}" if unit != "%" else f"{x:.0f}%" for x in b], textposition="middle right",
                             hovertemplate="%{y}<br>" + b_name + "：%{x:.1f}" + unit + "<extra></extra>"))
    fig.update_yaxes(autorange="reversed", tickfont=dict(size=13, color=INK))
    fig = style(fig, height)
    fig.update_layout(legend=dict(orientation="h", y=1.08, x=0), margin=dict(l=8, r=50, t=30, b=8))
    return fig


def team_strengths(row, n=2):
    """強項與弱項（聯盟第幾名），給雷達圖旁邊的文字用"""
    r = [(name, int(row[f"rk_{c}"])) for name, c, _ in ss.TEAM_AXES if pd.notna(row.get(f"rk_{c}"))]
    r.sort(key=lambda x: x[1])
    return r[:n], r[-n:][::-1]


def home_story_cards(S, T, P):
    """首頁的 3 則本季故事：[(種類, 標題, 一句說明, 圖, 按鈕去哪一頁)]"""
    cards = []
    if len(T):
        top = T.head(5)
        lead = top.iloc[0]
        cards.append(("球隊故事", f"目前最像冠軍的是{zh(lead['abbreviation'])}",
                      f"冠軍指數 {lead['champ_idx']:.0f}（滿分 100），戰績 {int(lead['win'])}-{int(lead['l'])}，"
                      f"淨效率聯盟第 {int(lead['rk_net_rating'])}。",
                      hbar([zh(a) for a in top["abbreviation"]], top["champ_idx"],
                           [ACCENT] + [SEASON_GREY] * (len(top) - 1), [f"{v:.0f}" for v in top["champ_idx"]], 210),
                      "奪冠列車"))
        tr = S["teams"].dropna(subset=["trend"]).sort_values("trend", ascending=False).head(5)
        if len(tr):
            up = tr.iloc[0]
            cards.append(("球隊故事", f"{zh(up['abbreviation'])}最近 10 場在加速",
                          f"最近 10 場平均淨勝 {up['margin_l10']:+.1f} 分，比整季平均多 {up['trend']:.1f} 分。",
                          hbar([zh(a) for a in tr["abbreviation"]], tr["trend"],
                               [ACCENT] + [SEASON_GREY] * (len(tr) - 1), [f"{v:+.1f}" for v in tr["trend"]], 210),
                          "奪冠列車"))
    hot = ss.hot_players(P, 5) if not P.empty else pd.DataFrame()
    if len(hot):
        h = hot.iloc[0]
        cards.append(("人物故事", f"{h['player_name']} 正在爆發",
                      f"最近 5 場平均 {h['pts_l5']:.1f} 分，比本季平均多 {h['hot']:.1f} 分（{zh(h['abbreviation'])}）。",
                      dumbbell(list(hot["player_name"]), hot["pts_avg"], hot["pts_l5"],
                               "本季平均", "最近 5 場", 230, " 分"),
                      "焦點人物"))
    return cards


def champ_label(season, abbr):
    return f"{season} {zh(abbr)}"


# =====================================================================
# 首頁：像 YouTube 首頁一樣的卡片牆，一張卡＝一個研究問題
# =====================================================================
def home_findings():
    """首頁的「重點發現」：每一句都由資料即時算出來（1030-7）。回傳 [(頁面, 標題, 補充說明)]"""
    out = []
    if league.empty:
        return out
    lg = league[league["season_type"] == "Regular Season"].copy()
    for c in ["gp", "w", "fga", "fg3a", "net_rating"]:
        lg[c] = pd.to_numeric(lg[c], errors="coerce")
    lg = lg[lg["season"].isin(set(champs["season"]))]
    if lg.empty:
        return out
    lg["rk_net"] = lg.groupby("season")["net_rating"].rank(ascending=False, method="min")
    ch = lg.merge(champs[["season", "team_id"]], on=["season", "team_id"])
    if len(ch):
        med = ch["rk_net"].median()
        top5 = (ch["rk_net"] <= 5).mean()
        out.append(("冠軍密碼", f"冠軍的淨效率排名中位數是聯盟第 {med:.0f} 名",
                    f"{len(ch)} 位冠軍中，{top5:.0%} 的例行賽淨效率排在聯盟前 5。奪冠最一致的條件是整體實力，不是單一項目。"))
        rec = ch[ch["season"] >= RECENT]
        if len(rec):
            k = int((rec["rk_net"] == 1).sum())
            out.append(("籤運與傷兵", f"2019 年後 {len(rec)} 位冠軍，只有 {k} 位是例行賽淨效率第 1",
                        "最強的隊不一定奪冠。那其他冠軍是不是籤運好、遇到對手傷兵？"))
    g = lg.groupby("season")
    tp = (g["fg3a"].sum() / g["fga"].sum()).dropna()
    if len(tp) > 1:
        out.append(("投籃分布", f"聯盟三分出手比例從 {tp.iloc[0]:.0%} 變成 {tp.iloc[-1]:.0%}",
                    f"{tp.index[0]} 到 {tp.index[-1]}，每 10 次出手裡的三分球多了 {(tp.iloc[-1] - tp.iloc[0]) * 10:.1f} 次。冠軍是怎麼調整出手位置的？"))
    try:
        tr = prep_tracking(load_tracking("team"), league)
    except Exception:
        tr = pd.DataFrame()
    if not tr.empty and "champion" in tr:
        c_ = tr[(tr["season_type"] == "Regular Season") & tr["champion"]]
        if len(c_):
            out.append(("跑動距離", f"冠軍的跑動距離排名中位數是第 {c_['rk_dist_km'].median():.0f} 名",
                        f"{len(c_)} 位冠軍（2016-17 起）每場平均跑 {c_['dist_km'].mean():.1f} 公里。跑得多不一定贏得多。"))
    return out


if PAGE == HOME:
    # ===== 1. 本季故事：每天用數據挑 3 則（球隊 2、人物 1）=====
    S = season_data()
    st.markdown('<div class="home-group" style="margin-top:0">本季故事</div>', unsafe_allow_html=True)
    if S is None:
        st.info("本季的比賽數據還沒載入。每天 15:30 自動更新後就會出現本季故事。")
    else:
        T = S["teams"].dropna(subset=["champ_idx"]).sort_values("champ_idx", ascending=False)
        P = S["players"]
        st.caption(f"{S['season']} 球季，資料更新到 {S['last_day']:%Y-%m-%d}（美國比賽日），已打 {S['n_games']} 場。"
                   "每則故事都只用數據寫，點按鈕看完整的圖。")
        cards = []
        try:
            cards = home_story_cards(S, T, P)
        except Exception as e:   # 故事卡出錯也不影響下面的入口
            st.caption(f"本季故事暫時無法顯示：{type(e).__name__}")
        cols = st.columns(len(cards) or 1, gap="medium")
        for col_, (kind, title, sub, fig, page) in zip(cols, cards):
            with col_:
                st.markdown(f'<div class="feature"><div class="feature-top">{kind}</div><div class="feature-body">'
                            f'<div class="feature-title" style="font-size:1.2rem">{title}</div>'
                            f'<div class="feature-text">{sub}</div></div></div>', unsafe_allow_html=True)
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=f"home_{title}")
                st.button(f"看「{page}」　→", key=f"story_{title}", on_click=goto, args=(page,), type="primary")
    # ===== 2. 六個入口 =====
    st.markdown('<div class="home-group">六個入口</div>', unsafe_allow_html=True)
    ENTRY = [("每日戰報", "昨晚發生什麼事？", "全聯盟比分、比賽走勢、關鍵時刻、下一場預測與預測準不準。"),
             ("奪冠列車", "今年誰最像冠軍？", "用歷屆冠軍的六項標準衡量本季 30 隊，每隊一張雷達圖。"),
             ("焦點人物", "本季誰最值得看？", "爆發中、不可或缺、關鍵先生；每位球員的雷達圖與完整數據。"),
             ("冠軍故事", "冠軍是怎麼贏的？", f"28 個研究問題分成 5 章：{'、'.join(CHAPTERS)}。"),
             ("資料與探索", "想自己查？", "球季趨勢、熱力圖、冠軍球季比較、球員、數據表下載。")]
    cols = st.columns(3, gap="medium")
    for i, (name, q_, desc) in enumerate(ENTRY):
        with cols[i % 3]:
            st.markdown(f'<div class="card"><div class="card-body"><div class="card-title">{name}</div>'
                        f'<div class="card-q">{q_}</div><div class="card-desc">{desc}</div></div></div>',
                        unsafe_allow_html=True)
            st.button(f"前往「{name}」", key=f"entry_{name}", width="stretch", on_click=goto, args=(dict(NAV)[name],))
    # ===== 3. 歷史的重點發現（奪冠列車的標準從這裡來）=====
    finds = home_findings()
    if finds:
        st.markdown('<div class="home-group">冠軍故事的重點發現（奪冠列車的標準從這裡來）</div>', unsafe_allow_html=True)
        for i, (p_, t_, x_) in enumerate(finds):
            st.markdown(f'<div class="headline-item"><div class="hp">{p_}</div><div class="ht">{t_}</div></div>',
                        unsafe_allow_html=True)
            try:
                st.button("前往　→", key=f"hl_{i}", on_click=goto, args=(p_,), type="tertiary")
            except Exception:
                st.button("前往　→", key=f"hl_{i}", on_click=goto, args=(p_,))
    st.markdown('<div class="footnote">DATA · NBA STATS API　｜　STORAGE · SUPABASE　｜　BUILT WITH STREAMLIT</div>',
                unsafe_allow_html=True)
    st.stop()


# ---------- 奪冠列車：今年誰最像冠軍？（2026-11-23 改版新頁）----------
if PAGE == "奪冠列車":
    S = season_data()
    if S is None or S["teams"].empty:
        st.info("本季的比賽數據還沒載入。每天 15:30 自動更新後就會出現。")
    elif S["champ_avg"].empty:
        st.info("歷屆冠軍的標準需要 league_team_seasons 和 champions 兩張表，目前讀不到。")
    else:
        T = S["teams"].sort_values("champ_idx", ascending=False).reset_index(drop=True)
        CP = S["champs_p"]
        hypothesis("今年誰最像冠軍？",
                   "歷屆冠軍幾乎都是淨效率聯盟前段、而且六項裡很少有明顯弱點；本季能同時做到的球隊只有少數幾支。")
        lead = T.iloc[0]
        k1, k2, k3, k4 = st.columns(4)
        kpi(k1, "本季已打", f"{S['n_games']} 場", f"資料到 {S['last_day']:%m/%d}")
        kpi(k2, "最像冠軍", zh(lead["abbreviation"]), f"冠軍指數 {lead['champ_idx']:.0f}")
        n90 = int((T["champ_idx"] >= 90).sum())
        kpi(k3, "冠軍指數 90 以上", f"{n90} 隊", "六項幾乎都不輸歷屆冠軍")
        kpi(k4, "歷屆冠軍", f"{len(CP)} 位", f"{CP['season'].min()} ～ {CP['season'].max()}")

        # ===== 1. 冠軍指數排行 =====
        slot1 = section("1　奪冠列車：30 隊離冠軍標準有多遠",
                        "冠軍指數 100＝六項都不輸歷屆冠軍的平均；每輸一項就扣分。紫色＝前 4 名（列車的車頭）。"
                        "冠軍指數怎麼算：六項各換成「贏過聯盟幾 % 的球隊」（0～100），和歷屆冠軍平均比；"
                        "只要不輸就不扣分，輸多少扣多少，六項扣分平均後用 100 減掉。", anchor="train1")
        cols_ = [ACCENT if i < 4 else SEASON_GREY for i in range(len(T))]
        txt = [f"{v:.0f}　{int(w)}-{int(l)}" for v, w, l in zip(T["champ_idx"], T["win"], T["l"])]
        st.plotly_chart(hbar([zh(a) for a in T["abbreviation"]], T["champ_idx"], cols_, txt, 26 * len(T) + 40),
                        width="stretch", config={"displayModeBar": False})
        top4 = "、".join(zh(a) for a in T["abbreviation"].head(4))
        lines = [f"目前最像冠軍的是{zh(lead['abbreviation'])}（冠軍指數 {lead['champ_idx']:.0f}，戰績 {int(lead['win'])}-{int(lead['l'])}）",
                 f"列車前 4 名：{top4}。冠軍指數 90 以上的有 {n90} 隊。"]
        insight(lines, where=slot1, check=(
            f"歷屆冠軍的淨效率排名中位數是第 {CP['rk_net_rating'].median():.0f} 名；"
            f"本季冠軍指數前 4 名裡，有 {int((T.head(4)['rk_net_rating'] <= 10).sum())} 隊淨效率在聯盟前 10。"))

        # ===== 2. 雷達圖 =====
        slot2 = section("2　每一隊的六角輪廓：和歷屆冠軍比", "紫色＝這一隊；灰色虛線＝歷屆冠軍平均；淡紫點線＝輪廓最像的那一位冠軍。"
                        "外圈＝這一項聯盟最好，中間圈＝聯盟中間。", anchor="train2")
        pick = st.selectbox("選一支球隊", list(T["abbreviation"]), index=0, key="train_team",
                            format_func=lambda a: f"{zh(a)}（冠軍指數 {T.set_index('abbreviation').loc[a, 'champ_idx']:.0f}）")
        row = T.set_index("abbreviation").loc[pick]
        like = ss.most_like(row, CP)
        traces = [(zh(pick), [row[f"p_{c}"] for _, c, _ in ss.TEAM_AXES], ACCENT, "solid", True),
                  ("歷屆冠軍平均", [S["champ_avg"][f"p_{c}"] for _, c, _ in ss.TEAM_AXES], CHAMP_LINE, "dash", False)]
        if like:
            lr = CP[(CP["season"] == like[0]) & (CP["abbreviation"] == like[1])].iloc[0]
            traces.append((f"最像：{champ_label(like[0], like[1])}", [lr[f"p_{c}"] for _, c, _ in ss.TEAM_AXES],
                           "#b9a6f0", "dot", False))
        cA, cB = st.columns([3, 2], gap="large")
        with cA:
            st.plotly_chart(radar(traces, 430), width="stretch", config={"displayModeBar": False})
        with cB:
            good, bad = team_strengths(row)
            st.markdown(f'<div class="feature"><div class="feature-top">{zh(pick)}　{int(row["win"])}-{int(row["l"])}</div>'
                        f'<div class="feature-body"><div class="feature-text">'
                        f'<b>強項</b>：{"、".join(f"{n}（聯盟第 {r}）" for n, r in good)}<br>'
                        f'<b>弱項</b>：{"、".join(f"{n}（聯盟第 {r}）" for n, r in bad)}<br>'
                        f'<b>淨效率</b>：{row["net_rating"]:+.1f}（聯盟第 {int(row["rk_net_rating"])}）<br>'
                        + (f'<b>最像的冠軍</b>：{champ_label(like[0], like[1])}<br>' if like else "")
                        + f'<b>冠軍指數</b>：{row["champ_idx"]:.0f}</div></div></div>', unsafe_allow_html=True)
        lacks = [n for n, c, _ in ss.TEAM_AXES if row[f"p_{c}"] < S["champ_avg"][f"p_{c}"] - 10]
        insight([f"{zh(pick)}的輪廓最像 {champ_label(like[0], like[1])}" if like else f"{zh(pick)}的六角輪廓",
                 ("和歷屆冠軍平均比，明顯落後的是：" + "、".join(lacks) + "。") if lacks else "六項都沒有明顯落後歷屆冠軍平均。"],
                where=slot2, to_summary=False)
        with st.expander("六項的數字與排名（全部 30 隊）"):
            nice_table(pd.DataFrame({
                "球隊": [zh(a) for a in T["abbreviation"]], "_key": T["abbreviation"],
                "戰績": [f"{int(w)}-{int(l)}" for w, l in zip(T["win"], T["l"])],
                "冠軍指數": [f"{v:.0f}" for v in T["champ_idx"]],
                "進攻效率": [f"{v:.1f}（{int(r)}）" for v, r in zip(T["off_rating"], T["rk_off_rating"])],
                "防守效率": [f"{v:.1f}（{int(r)}）" for v, r in zip(T["def_rating"], T["rk_def_rating"])],
                "三分命中率": [f"{v:.1%}（{int(r)}）" for v, r in zip(T["fg3_pct"], T["rk_fg3_pct"])],
                "籃板率": [f"{v:.1%}（{int(r)}）" for v, r in zip(T["reb_pct"], T["rk_reb_pct"])],
                "助攻比例": [f"{v:.1%}（{int(r)}）" for v, r in zip(T["ast_ratio"], T["rk_ast_ratio"])],
                "失誤率": [f"{v:.1%}（{int(r)}）" for v, r in zip(T["tov_pct"], T["rk_tov_pct"])],
            }), num_cols=("冠軍指數", "進攻效率", "防守效率", "三分命中率", "籃板率", "助攻比例", "失誤率"),
                dot_col="球隊", colors=TEAM_COLORS)
            st.caption("括號＝聯盟第幾名。助攻比例＝投進的球裡有幾成是助攻來的；失誤率＝每回合失誤的比例（越低越好）。")

        # ===== 3. 最近 10 場 =====
        slot3 = section("3　誰在加速、誰在減速", "最近 10 場的平均淨勝分，比整季平均多（右）或少（左）幾分。紫色＝加速最多的 3 隊。",
                        anchor="train3")
        R = S["teams"].dropna(subset=["trend"]).sort_values("trend", ascending=False)
        cols_ = [ACCENT if i < 3 else SEASON_GREY for i in range(len(R))]
        st.plotly_chart(hbar([zh(a) for a in R["abbreviation"]], R["trend"], cols_, [f"{v:+.1f}" for v in R["trend"]],
                             26 * len(R) + 40, zero=True), width="stretch", config={"displayModeBar": False})
        if len(R):
            u, d_ = R.iloc[0], R.iloc[-1]
            insight([f"{zh(u['abbreviation'])}最近 10 場比整季平均多淨勝 {u['trend']:.1f} 分，加速最多",
                     f"減速最多的是{zh(d_['abbreviation'])}（{d_['trend']:+.1f} 分）。開季前幾週場數少，這個數字變動會比較大。"],
                    where=slot3)


        # ===== 4. 輸球之後（2026-11-24 本季故事；11/25 重建）=====
        slot4 = section("4　輸球之後：誰最會馬上贏回來",
                        "列車前 8 名。灰點＝整季勝率，紫點＝輸球後下一場的勝率；紫點在灰點右邊＝輸完特別會贏。"
                        "括號＝本季最長連敗。輸球後少於 3 場的隊先不畫（一場就差 30 幾個百分點，太不穩）。", anchor="train4")
        B = ss.bounce_table(S["tg"])
        top8 = list(T["abbreviation"].head(8))
        Bt = B.set_index("abbreviation").reindex(top8).dropna(subset=["aft_pct"]) if not B.empty else B
        Bt = Bt[Bt["aft_g"] >= 3].sort_values("bounce", ascending=False) if len(Bt) else Bt
        if len(Bt) == 0:
            insight(["還沒有足夠的輸球場次：列車前 8 名輸球後的下一場都還不到 3 場，等多打幾場再看。"], where=slot4)
        else:
            st.plotly_chart(dumbbell([f"{zh(a)}（最長連敗 {int(r.max_lose)}）" for a, r in Bt.iterrows()],
                                     Bt["win_pct"] * 100, Bt["aft_pct"] * 100, "整季勝率", "輸球後下一場", 46 * len(Bt) + 70, "%"),
                            width="stretch", config={"displayModeBar": False})
            b0 = Bt.iloc[0]
            insight([f"{zh(Bt.index[0])}輸球後下一場贏 {int(b0.aft_w)}/{int(b0.aft_g)}，比自己整季勝率高 {b0.bounce:.0f} 個百分點，最會馬上贏回來",
                     f"列車前 8 名裡，最長連敗只有 1 場的：{'、'.join(zh(a) for a, r in Bt.iterrows() if r.max_lose <= 1) or '沒有'}。"
                     "開季場數少，一場就會讓數字大幅變動。"], where=slot4)
            with st.expander("全部 30 隊：輸球之後的下一場"):
                Ba = B.sort_values(["bounce"], ascending=False)
                nice_table(pd.DataFrame({
                    "球隊": [zh(a) for a in Ba["abbreviation"]], "_key": Ba["abbreviation"],
                    "戰績": [f"{w}-{l}" for w, l in zip(Ba["win"], Ba["l"])],
                    "輸球後下一場": [f"{w}-{g - w}" if g else "—" for w, g in zip(Ba["aft_w"], Ba["aft_g"])],
                    "反彈（百分點）": [f"{v:+.0f}" if pd.notna(v) else "—" for v in Ba["bounce"]],
                    "最長連敗": [f"{v} 場" for v in Ba["max_lose"]], "目前": Ba["streak"]}),
                    num_cols=("戰績", "輸球後下一場", "反彈（百分點）", "最長連敗"), signed_cols=("反彈（百分點）",),
                    dot_col="球隊", colors=TEAM_COLORS)
        st.button("歷史證據：冠軍輸球後會馬上反彈嗎？ → 冠軍故事 ／ 輸球之後", key="train_to_bounce",
                  on_click=goto, args=("輸球之後",))

        # ===== 5. 賽程來了：未來 7 天誰最累（2026-11-25 本季故事）=====
        slot5 = section("5　賽程來了：未來 7 天誰最累",
                        "每一列是一支球隊，每個點是一場比賽（上面的字＝對手，@＝客場）。"
                        "紫色連線＝背靠背（連兩天出賽）；空心點＝最後一場已打完的比賽。只列出未來 7 天有背靠背的球隊。",
                        anchor="train5")
        SC = cur_schedule(S["season"])
        start = S["last_day"]
        LD, GD = ss.schedule_load(SC, S["tg"], start, 7)
        if LD.empty:
            insight(["還沒有未來賽程：recap_schedule 這張表是空的或不存在。每天 15:30 自動更新（load_recap.py）後就會出現；"
                     "如果一直沒有，請先在 Supabase 執行 schema_schedule.sql。"], where=slot5)
        else:
            rank8 = {a: i + 1 for i, a in enumerate(T["abbreviation"])}
            busy = LD[LD["b2b"] > 0]
            if busy.empty:
                insight([f"未來 7 天（{start + pd.Timedelta(days=1):%m/%d}～{start + pd.Timedelta(days=7):%m/%d}）沒有球隊背靠背",
                         f"場數最多的是{zh(LD.iloc[0]['abbreviation'])}（{int(LD.iloc[0]['games'])} 場）。"], where=slot5)
            else:
                order = list(busy["abbreviation"])
                lab = {a: f"{zh(a)}（列車第 {rank8.get(a, '–')}）" for a in order}
                fig = go.Figure()
                for a in order:
                    x = GD[GD["abbreviation"] == a]
                    y = lab[a]
                    for r in x[x["b2b"]].itertuples():          # 背靠背：前一場和這一場連一條紫線
                        fig.add_trace(go.Scatter(x=[r.prev, r.game_date], y=[y, y], mode="lines",
                                                 line=dict(color=ACCENT, width=5), hoverinfo="skip", showlegend=False))
                        if r.prev <= start:                         # 前一場已打完：空心點
                            fig.add_trace(go.Scatter(x=[r.prev], y=[y], mode="markers", showlegend=False,
                                                     marker=dict(size=12, color="white", line=dict(color=ACCENT, width=2)),
                                                     hovertemplate=f"{zh(a)}　%{{x|%m/%d}} 已打完<extra></extra>"))
                    in_b2b = set(x.loc[x["b2b"], "game_date"]) | set(x.loc[x["b2b"], "prev"])
                    fig.add_trace(go.Scatter(
                        x=x["game_date"], y=[y] * len(x), mode="markers+text", showlegend=False,
                        marker=dict(size=13, color=[ACCENT if d in in_b2b else "#b8b2c6" for d in x["game_date"]]),
                        text=[("vs " if h else "@") + o for h, o in zip(x["is_home"], x["opp"])], textposition="top center",
                        textfont=dict(size=11, color=INK),
                        hovertemplate=[f"{zh(a)}　%{{x|%m/%d}}　{'主場對' if h else '客場對'}{zh(o)}<extra></extra>"
                                       for h, o in zip(x["is_home"], x["opp"])]))
                for r in busy.itertuples():                          # 右邊直接寫「幾組背靠背」
                    fig.add_annotation(x=start + pd.Timedelta(days=7.6), y=lab[r.abbreviation], xanchor="left",
                                       text=f"<b>{r.b2b} 組</b>　{r.games} 場（客 {r.away}）", showarrow=False,
                                       font=dict(size=12, color=ACCENT if r.b2b == busy["b2b"].max() else INK))
                fig.update_yaxes(autorange="reversed", tickfont=dict(size=13, color=INK),
                                 categoryorder="array", categoryarray=[lab[a] for a in order])
                fig.update_xaxes(range=[start - pd.Timedelta(days=0.5), start + pd.Timedelta(days=9.6)],
                                 tickformat="%m/%d", dtick=86400000, showgrid=True)
                fig = style(fig, 44 * len(order) + 80)
                fig.update_layout(margin=dict(l=8, r=8, t=24, b=8))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                mx = busy["b2b"].max()
                most = [zh(a) for a in busy[busy["b2b"] == mx]["abbreviation"]]
                tops = [a for a in T["abbreviation"].head(8)]
                t_b2b = [f"{zh(a)}（{int(LD.set_index('abbreviation').loc[a, 'b2b'])} 組）" for a in tops
                         if a in set(busy["abbreviation"])]
                easy = LD[LD["abbreviation"].isin(tops)].sort_values(["b2b", "games"]).iloc[0]
                rs = ss.rest_split(S["tg"])
                insight([f"未來 7 天背靠背最多的是{'、'.join(most)}（{mx} 組），賽程最累",
                         ("列車前 8 名裡有背靠背的：" + "、".join(t_b2b) + "。" if t_b2b else "列車前 8 名未來 7 天都沒有背靠背。")
                         + f"前 8 名裡賽程最輕鬆的是{zh(easy['abbreviation'])}（{int(easy['games'])} 場、{int(easy['b2b'])} 組背靠背）。"],
                        where=slot5,
                        check=(f"本季到目前，背靠背第二場的勝率 {rs['b2b_pct']:.0%}（{rs['b2b_g']} 場），有休息的 {rs['rest_pct']:.0%}（{rs['rest_g']} 場），"
                               + (f"有休息的高 {rs['gap']:.0f} 個百分點" if rs["gap"] >= 0.5 else
                                  f"背靠背反而高 {-rs['gap']:.0f} 個百分點（開季場數少，還看不出累的影響）")
                               + "；歷屆長期的證據在「冠軍故事 ／ 賽程與休息」。") if rs else None)
            with st.expander("全部 30 隊：未來 7 天的賽程"):
                rows_ = []
                for r in LD.itertuples():
                    x = GD[GD["abbreviation"] == r.abbreviation]
                    rows_.append({"球隊": zh(r.abbreviation), "_key": r.abbreviation, "列車": f"第 {rank8.get(r.abbreviation, '–')}",
                                  "場數": f"{r.games}", "背靠背": f"{r.b2b} 組", "主／客": f"{r.home}／{r.away}",
                                  "賽程": "・".join(f"{d:%m/%d} {'vs ' if h else '@'}{o}" + ("（背靠背）" if b else "")
                                                   for d, h, o, b in zip(x["game_date"], x["is_home"], x["opp"], x["b2b"]))})
                nice_table(pd.DataFrame(rows_), num_cols=("場數",), dot_col="球隊", colors=TEAM_COLORS)
                st.caption("背靠背＝和前一場只差 1 天（第一場也和最後一場已打完的比賽比）。賽程來自 NBA 官網，每天 15:30 更新。")
        st.button("歷史證據：背靠背會不會輸比較多？ → 冠軍故事 ／ 賽程與休息", key="train_to_rest",
                  on_click=goto, args=("賽程與休息",))

# ---------- 焦點人物：本季誰最值得看？（2026-11-23 改版新頁）----------
if PAGE == "焦點人物":
    S = season_data()
    P = S["players"] if S else pd.DataFrame()
    if S is None or P.empty:
        st.info("本季的球員數據還沒載入。每天 15:30 自動更新後就會出現。")
    else:
        Q = P[P["qualified"]]
        st.caption(f"{S['season']} 球季，資料到 {S['last_day']:%Y-%m-%d}。夠格球員＝出賽至少本季場數的 4 成、"
                   f"場均 15 分鐘以上（目前 {len(Q)} 人）；排名只在夠格球員裡比。")
        hot = ss.hot_players(P, 8)
        ww = ss.with_without(S["pg"], S["tg"], P)
        cl = ss.clutch_table(cur_clutch(S["season"]))
        # ===== 0. 三種人物 =====
        c1, c2, c3 = st.columns(3, gap="medium")
        if len(hot):
            h = hot.iloc[0]
            c1.markdown(f'<div class="feature"><div class="feature-top">爆發中</div><div class="feature-body">'
                        f'<div class="feature-title" style="font-size:1.2rem">{h["player_name"]}</div>'
                        f'<div class="feature-text">{zh(h["abbreviation"])}｜最近 5 場 {h["pts_l5"]:.1f} 分，'
                        f'比本季平均多 {h["hot"]:.1f} 分</div></div></div>', unsafe_allow_html=True)
        if len(ww):
            w_ = ww.iloc[0]
            c2.markdown(f'<div class="feature"><div class="feature-top">不可或缺</div><div class="feature-body">'
                        f'<div class="feature-title" style="font-size:1.2rem">{w_["player_name"]}</div>'
                        f'<div class="feature-text">{zh(w_["abbreviation"])}｜有他勝率 {w_["w_on"]:.0%}、'
                        f'沒他 {w_["w_off"]:.0%}（缺陣 {int(w_["g_off"])} 場）</div></div></div>', unsafe_allow_html=True)
        if len(cl):
            c_ = cl.iloc[0]
            c3.markdown(f'<div class="feature"><div class="feature-top">關鍵先生</div><div class="feature-body">'
                        f'<div class="feature-title" style="font-size:1.2rem">{c_["player_name"]}</div>'
                        f'<div class="feature-text">{zh(c_["team_abbr"])}｜關鍵時刻得 {int(c_["pts"])} 分，'
                        f'聯盟最多</div></div></div>', unsafe_allow_html=True)

        # ===== 1. 爆發中 =====
        if len(hot):
            slot = section("1　爆發中：最近 5 場比本季平均多得最多分", "灰點＝本季平均、紫點＝最近 5 場；線越長，進步越多。"
                           "只看夠格、而且最近 10 天有上場的球員。", anchor="ppl1")
            st.plotly_chart(dumbbell([f"{n}（{zh(a)}）" for n, a in zip(hot["player_name"], hot["abbreviation"])],
                                     hot["pts_avg"], hot["pts_l5"], "本季平均", "最近 5 場", 44 * len(hot) + 60, " 分"),
                            width="stretch", config={"displayModeBar": False})
            h = hot.iloc[0]
            insight([f"{h['player_name']} 最近 5 場平均 {h['pts_l5']:.1f} 分，比本季平均多 {h['hot']:.1f} 分"], where=slot)
        # ===== 2. 不可或缺 =====
        if len(ww):
            W = ww.head(8)
            slot = section("2　不可或缺：少了他，球隊勝率掉最多", "灰點＝他缺陣時球隊的勝率、紫點＝他有上場時；"
                           "只看場均 25 分鐘以上、至少缺陣 3 場的球員（從他本季第一次上場後算）。", anchor="ppl2")
            st.plotly_chart(dumbbell([f"{n}（{zh(a)}）" for n, a in zip(W["player_name"], W["abbreviation"])],
                                     W["w_off"] * 100, W["w_on"] * 100, "他缺陣時", "他上場時", 44 * len(W) + 60, "%"),
                            width="stretch", config={"displayModeBar": False})
            w_ = W.iloc[0]
            insight([f"{w_['player_name']} 上場時{zh(w_['abbreviation'])}勝率 {w_['w_on']:.0%}，缺陣時只有 {w_['w_off']:.0%}",
                     f"他缺陣 {int(w_['g_off'])} 場、上場 {int(w_['g_on'])} 場。缺陣場數少，數字只能當參考；"
                     "也可能剛好遇到強隊（「冠軍故事 ／ 缺陣場的對手」有扣掉對手強弱的方法）。"], where=slot)
        # ===== 3. 關鍵先生 =====
        if len(cl):
            C = cl.head(10)
            slot = section("3　關鍵先生：關鍵時刻得分最多", "關鍵時刻＝第四節或延長賽最後 5 分鐘、得分前分差 5 分以內。"
                           "紫色＝前 3 名。", anchor="ppl3")
            st.plotly_chart(hbar([f"{n}（{zh(a)}）" for n, a in zip(C["player_name"], C["team_abbr"])], C["pts"],
                                 [ACCENT if i < 3 else SEASON_GREY for i in range(len(C))],
                                 [f"{int(v)} 分（{int(g)} 場）" for v, g in zip(C["pts"], C["games"])], 30 * len(C) + 40),
                            width="stretch", config={"displayModeBar": False})
            insight([f"本季關鍵時刻得分最多的是 {C.iloc[0]['player_name']}（{int(C.iloc[0]['pts'])} 分）"], where=slot)

        # ===== 4. 球員雷達圖＋完整數據 =====
        slot = section("4　球員雷達圖", "外圈＝這一項在夠格球員裡最好；灰色虛線＝聯盟中間（贏過一半的人）。點下方「完整數據」看所有傳統與進階數據。",
                       anchor="ppl4")
        Qs = Q.sort_values("pts_g", ascending=False)
        default = hot.iloc[0]["player_id"] if len(hot) else Qs.iloc[0]["player_id"]
        names = dict(zip(Qs["player_id"], [f"{n}（{zh(a)}，{v:.1f} 分）" for n, a, v in
                                           zip(Qs["player_name"], Qs["abbreviation"], Qs["pts_g"])]))
        ids = list(Qs["player_id"])
        pid = st.selectbox("選一位球員（依場均得分排序）", ids, index=ids.index(default) if default in ids else 0,
                           format_func=lambda i: names.get(i, str(i)), key="ppl_pick")
        r = P.set_index("player_id").loc[pid]
        cA, cB = st.columns([3, 2], gap="large")
        with cA:
            st.plotly_chart(radar([(r["player_name"], [r[f"p_{c}"] for _, c, _ in ss.PLAYER_AXES], ACCENT, "solid", True),
                                   ("聯盟中間", [50] * 6, CHAMP_LINE, "dash", False)], 420),
                            width="stretch", config={"displayModeBar": False})
        with cB:
            lab = {"pts": "得分", "stocks": "抄截＋阻攻", "fg3m": "三分命中", "reb": "籃板", "ast": "助攻", "tov": "失誤"}
            items = "".join(f'<b>{n}</b>（{lab[c]}）　{(r["stocks"] if c == "stocks" else r[f"{c}_g"]):.1f}'
                            f'　第 {int(r[f"rk_{c}"])}<br>' for n, c, _ in ss.PLAYER_AXES if pd.notna(r.get(f"rk_{c}")))
            st.markdown(f'<div class="feature"><div class="feature-top">{r["player_name"]}　{zh(r["abbreviation"])}</div>'
                        f'<div class="feature-body"><div class="feature-text">{items}'
                        f'<span style="color:var(--ink-2)">場均，括號＝在 {len(Q)} 位夠格球員裡第幾名</span></div></div></div>',
                        unsafe_allow_html=True)
        G = ss.player_games(S["pg"], pid).tail(10)
        if len(G):
            fig = go.Figure(go.Bar(x=[f"{d:%m/%d}" for d in G["game_date"]], y=G["pts"], marker_color=ACCENT,
                                   text=[f"{int(v)}" for v in G["pts"]], textposition="outside", cliponaxis=False,
                                   hovertemplate="%{x}：%{y} 分<extra></extra>"))
            fig.add_hline(y=r["pts_g"], line=dict(color=CHAMP_LINE, dash="dash"),
                          annotation_text=f"本季平均 {r['pts_g']:.1f}", annotation_position="top left")
            fig.update_yaxes(title="得分")
            st.markdown('<div class="section-sub">最近 10 場得分</div>', unsafe_allow_html=True)
            st.plotly_chart(style(fig, 240), width="stretch", config={"displayModeBar": False})
        with st.expander("完整數據：傳統＋進階（點開）"):
            f1 = lambda v, f=".1f": "-" if pd.isna(v) else format(v, f)
            st.markdown("**傳統數據（場均）**")
            nice_table(pd.DataFrame([{
                "出賽": int(r["gp"]), "分鐘": f1(r["mpg"]), "得分": f1(r["pts_g"]), "籃板": f1(r["reb_g"]),
                "進攻籃板": f1(r["oreb_g"]), "防守籃板": f1(r["dreb_g"]), "助攻": f1(r["ast_g"]), "抄截": f1(r["stl_g"]),
                "阻攻": f1(r["blk_g"]), "失誤": f1(r["tov_g"]), "犯規": f1(r["pf_g"]),
                "投籃": f"{f1(r['fgm_g'])}/{f1(r['fga_g'])}", "三分": f"{f1(r['fg3m_g'])}/{f1(r['fg3a_g'])}",
                "罰球": f"{f1(r['ftm_g'])}/{f1(r['fta_g'])}", "正負值": f1(r["plus_minus_g"], "+.1f")}]),
                num_cols=("出賽", "分鐘", "得分", "籃板", "進攻籃板", "防守籃板", "助攻", "抄截", "阻攻", "失誤", "犯規", "正負值"))
            st.markdown("**命中率**")
            nice_table(pd.DataFrame([{"投籃命中率": f1(r["fg_pct"], ".1%"), "三分命中率": f1(r["fg3_pct"], ".1%"),
                                      "罰球命中率": f1(r["ft_pct"], ".1%"), "真實命中率": f1(r["ts"], ".1%"),
                                      "有效命中率": f1(r["efg"], ".1%")}]),
                       num_cols=("投籃命中率", "三分命中率", "罰球命中率", "真實命中率", "有效命中率"))
            st.markdown("**進階數據**")
            nice_table(pd.DataFrame([{"使用率": f1(r.get("usg"), ".1%"), "三分出手比例": f1(r["tpar"], ".1%"),
                                      "罰球出手比": f1(r["ftr"], ".2f"), "助攻失誤比": f1(r["ast_to"], ".2f"),
                                      "每 36 分鐘得分": f1(r["pts_36"]), "每 36 分鐘籃板": f1(r["reb_36"]),
                                      "每 36 分鐘助攻": f1(r["ast_36"]), "最近 5 場得分": f1(r["pts_l5"])}]),
                       num_cols=("使用率", "三分出手比例", "罰球出手比", "助攻失誤比", "每 36 分鐘得分", "每 36 分鐘籃板",
                                 "每 36 分鐘助攻", "最近 5 場得分"))
            st.markdown('<div class="howread">真實命中率＝把二分、三分、罰球都算進去的命中率；有效命中率＝三分球多算半顆的命中率；'
                        '使用率＝他在場上時，球隊的回合有幾成由他結束（出手、罰球或失誤）；罰球出手比＝每次投籃出手對應幾次罰球；'
                        '每 36 分鐘＝把數據換算成打滿 36 分鐘，替補和先發可以公平比較。</div>', unsafe_allow_html=True)




# ---------- 0. 冠軍密碼：三個問題 ----------
FACTORS = [  # （名稱, 欄位, 數值越高越好?, 顯示格式）
    ("淨效率", "net_rating", True, "signed"), ("進攻效率", "off_rating", True, "num1"),
    ("防守效率", "def_rating", False, "num1"), ("真實命中率", "ts_pct", True, "pct"),
    ("三分出手比例", "tpar", True, "pct"), ("三分命中率", "fg3_pct", True, "pct"),
    ("失誤率", "tm_tov_pct", False, "pct"), ("進攻籃板率", "oreb_pct", True, "pct"),
    ("防守籃板率", "dreb_pct", True, "pct"), ("助攻失誤比", "ast_to", True, "num2"),
]
# 名詞小辭典：每項指標白話解釋（意思, 怎麼算, 排名第 1 代表什麼）；其他頁也可以共用
GLOSSARY = {
    "淨效率": ("整體實力：每打 100 個回合，自己得分比對手多幾分", "進攻效率 − 防守效率", "淨勝最多"),
    "進攻效率": ("進攻能力：每打 100 個回合能得幾分。用回合算，不會因為節奏快、出手多就虛胖", "得分 ÷ 回合數 × 100", "得分最有效率"),
    "防守效率": ("防守能力：每 100 個回合讓對手得幾分，數字越低越好", "對手得分 ÷ 回合數 × 100", "失分最少"),
    "真實命中率": ("把二分、三分、罰球都算進去的命中率，看每次出手換到多少分", "得分 ÷［2 ×（投籃出手 ＋ 0.44 × 罰球出手）］", "投得最有效率"),
    "三分出手比例": ("打法：全部出手中三分球佔幾成。代表風格，不代表好壞", "三分出手 ÷ 投籃出手", "最愛投三分"),
    "三分命中率": ("三分球投進的比例", "三分命中 ÷ 三分出手", "三分最準"),
    "失誤率": ("每 100 個回合發生幾次失誤（傳球被抄、走步、出界…），越低越好", "失誤 ÷ 回合數 × 100", "最少失誤"),
    "進攻籃板率": ("自己投不進時，搶回籃板、多一次進攻機會的比例", "進攻籃板 ÷（自己進攻籃板 ＋ 對手防守籃板）", "最會搶進攻籃板"),
    "防守籃板率": ("對手投不進時，自己把籃板搶下來、不給二次進攻的比例", "防守籃板 ÷（自己防守籃板 ＋ 對手進攻籃板）", "最會保護籃板"),
    "助攻失誤比": ("傳球品質：每 1 次失誤對應幾次助攻，越高代表傳得多又穩", "助攻 ÷ 失誤", "傳球最穩"),
    "節奏": ("比賽快慢：每 48 分鐘打幾個回合", "回合數 ÷ 上場分鐘 × 48", "打得最快"),
}


def glossary_table(names):
    """把指標的白話解釋做成精簡表格，依圖上的順序排列"""
    rows = [{"指標": n, "意思": GLOSSARY[n][0], "怎麼算": GLOSSARY[n][1], "聯盟第 1 名代表": GLOSSARY[n][2]}
            for n in names if n in GLOSSARY]
    if rows:
        nice_table(pd.DataFrame(rows))


# 全站共用的名詞小辭典（1031-3 投籃區域、1101-2 戰術、1102-2 陣容）：名詞 → (白話意思, 怎麼算／在哪裡)
TERMS = {
    "頭號得分手（本頁）": ("這一季在這隊例行賽場均得分最高、至少上場 20 場的球員（和「頭號得分手缺陣」頁同一個人）", "依例行賽場均得分排名"),
    "缺陣（本頁）": ("球隊有打這一場，但他沒有出賽紀錄或上場 0 分鐘；不知道是受傷、休息還是禁賽", "季中被交易的球員只算他在隊期間"),
    "補回比例": ("缺陣時隊友每場多得的分數，佔他平常場均得分的幾 %；100% ＝全部補回來", "隊友多得的分數 ÷ 他有上場時的場均"),
    "第 2 號、第 3 號得分手": ("扣掉頭號得分手，隊上場均得分第 1、第 2 高的人（至少出賽 10 場）", "用他有上場的那些比賽排名"),
    # 投籃區域（球場圖上的五大區）
    "禁區籃下": ("籃框正下方半圓（半徑 4 英尺）裡的出手，多半是上籃、灌籃", "球場圖最靠近籃框的小半圓"),
    "油漆區": ("籃下半圓以外、但還在罰球線長方形（油漆區）裡的出手，例如拋投、小勾射", "罰球線長方形扣掉籃下半圓"),
    "中距離": ("油漆區外、三分線內的兩分球，最「不划算」的出手", "長方形外、三分線內"),
    "底角三分": ("左右兩側底角的三分球；這裡的三分線最近（22 英尺），比弧頂近約 1.75 英尺", "三分線的兩條直線段後面"),
    "弧頂三分": ("底角以外的三分球（左翼、正面、右翼）", "三分弧線後面"),
    "每次出手得分": ("平均每出手一次換到幾分，用來比「哪裡出手比較划算」", "命中率 × 分值（兩分或三分）"),
    # 戰術（Synergy 分類）
    "單打": ("持球者自己一對一進攻，隊友拉開空間", "Isolation"),
    "快攻轉換": ("搶到球後，對手防守還沒站好就快速推進出手", "Transition"),
    "擋拆持球者": ("隊友來幫忙擋人（掩護），由持球的人自己投、切或傳", "Pick & Roll Ball Handler"),
    "擋拆順下": ("幫忙擋人的那位（通常是長人）擋完往籃下跑，接球出手", "Pick & Roll Roll Man"),
    "低位背框": ("在籃下附近背對籃框接球，再轉身或靠身體出手", "Post Up"),
    "定點投籃": ("站著接隊友的傳球直接出手，多半是空檔投籃", "Spot Up"),
    "手遞手": ("把球「交」到隊友手上的同時順便擋住防守者", "Handoff"),
    "空手切入": ("沒有球的人突然往籃下跑，接球上籃", "Cut"),
    "繞掩護": ("沒有球的射手繞過隊友的掩護，跑出空檔接球投籃", "Off Screen"),
    "進攻籃板補進": ("自己人沒投進，搶到進攻籃板直接補進", "Putbacks"),
    "使用率": ("這種戰術佔全隊進攻（或防守）回合的比例", "這種戰術的回合 ÷ 全部回合"),
    "每回合得分（PPP）": ("用這種戰術進攻一次，平均得幾分；防守端是讓對手得幾分（越低越好）", "得分 ÷ 回合數"),
    # 上場陣容
    "核心五人": ("同一季、同一種比賽裡，同時在場時間最久的那 5 個人", "依同時在場分鐘排第 1 的組合"),
    "同時在場分鐘": ("這 5 個人「一起」在場上的分鐘數，不是每個人各自的上場時間", "NBA 官方陣容數據"),
    "佔全隊時間": ("這組陣容在場的時間，佔全隊整季比賽時間的比例（約略值）", "同時在場分鐘 ÷（場數 × 48）"),
    "陣容集中度": ("在場最久的前 5 組加起來佔全隊多少時間，越高代表教練越固定用那幾組人", "前 5 組的佔全隊時間相加"),
    "球星（本頁）": ("這一季例行賽場均得分隊內前 3 名、出賽至少 40 場的球員；第 1 名叫「頭號球星」", "依例行賽場均得分排名"),
    "每 36 分鐘得分": ("把上場時間換算成同樣 36 分鐘時能得幾分，排除「上場比較久所以得比較多」", "得分 ÷ 上場分鐘 × 36"),
    "季後賽 − 例行賽": ("同一位球員、同一季，季後賽數字減例行賽數字；正數＝季後賽比較好", "命中率的差用「百分點」：50% → 47% 是 −3 百分點"),
    "每場跑動距離": ("球員追蹤攝影機記錄的距離；球隊是全隊在場球員合計的每場平均", "NBA 官方追蹤數據，英里 × 1.609 換成公里"),
    "平均速度": ("在場上所有時間的平均移動速度，包含走路和站著，所以比衝刺慢很多", "跑動距離 ÷ 在場時間"),
    "進攻速度／防守速度": ("自己隊進攻時、防守時各自的平均速度；表格裡是聯盟排名（1＝最快）", "分進攻、防守時間計算"),
    "比同季聯盟平均多多少": ("這隊減掉同一季 30 隊的平均。不同年代打法不同，和同季比才公平", "這隊數值 − 同季 30 隊平均"),
    "每 36 分鐘跑動": ("把上場時間換算成同樣 36 分鐘，替補和先發才能公平比", "每場距離 ÷ 場均分鐘 × 36"),
    "相關係數 r": ("兩件事一起變大或變小的程度，−1～+1；0 代表沒關係", "|r| < 0.1 幾乎沒有、0.3 中等、0.5 以上強"),
    "得分起伏": ("每場得分忽高忽低的程度；越小越穩定", "這一季每場得分的標準差 ÷ 場均得分"),
    "同得分水準": ("和「場均得分差不多」的球員比；得分越多的人起伏自然越小，直接比不公平", "所有頭號球星畫一條「起伏 vs 場均」的直線"),
    "低迷場": ("得分不到自己這一季平均的六成，例如場均 25 分的人只得 14 分", "得分 < 0.6 × 自己的場均"),
    "爆發場": ("得分到自己這一季平均的 1.5 倍以上", "得分 ≥ 1.5 × 自己的場均"),
    "前半季／後半季": ("這一季自己的比賽依日期排好，前一半場次和後一半場次", "82 場＝前 41 場、後 41 場"),
    "其他強隊": ("整季勝率六成以上、但沒有奪冠的球隊季；用來和冠軍比「同樣強的隊會不會也越打越好」", "例行賽勝率 ≥ 60%"),
    "勝率變化（百分點）": ("兩個勝率相減；60% → 70% 是 +10 個百分點", "後半季勝率 − 前半季勝率"),
    "陣容戰績": ("這 5 人「有同時上場過」的那些比賽的勝負，不代表他們打滿全場", "例：8 勝 2 敗＝10 場裡有同時上場"),
    "回合": ("一次進攻機會：從拿到球開始，到投進、投失被對手搶到籃板、失誤或罰球結束為止", "約等於 出手 ＋ 0.44 × 罰球出手 − 進攻籃板 ＋ 失誤"),
    "季後賽節奏變化": ("同一隊、同一季，季後賽節奏減掉例行賽節奏；負數＝季後賽打得比較慢", "季後賽節奏 − 例行賽節奏"),
}


def term_table(names, first_note=None):
    """名詞小辭典表格（名詞／白話意思／怎麼算）；淨效率這類指標也從冠軍密碼的 GLOSSARY 拿"""
    if first_note:
        st.markdown(f'<div class="howread"><b>先看這裡：</b>{first_note}</div>', unsafe_allow_html=True)
    rows = []
    for n in names:
        if n in TERMS:
            rows.append({"名詞": n, "意思": TERMS[n][0], "怎麼算／英文": TERMS[n][1]})
        elif n in GLOSSARY:
            rows.append({"名詞": n, "意思": GLOSSARY[n][0], "怎麼算／英文": GLOSSARY[n][1]})
    if rows:
        nice_table(pd.DataFrame(rows))


STYLE = [("節奏", "pace", True), ("三分出手比例", "tpar", True), ("進攻效率", "off_rating", True),
         ("防守效率", "def_rating", False), ("進攻籃板率", "oreb_pct", True),
         ("助攻失誤比", "ast_to", True), ("失誤少", "tm_tov_pct", False)]


def show(v, kind):
    if pd.isna(v):
        return "-"
    if kind == "pct":
        return f"{(v if v > 1 else v * 100):.1f}%"
    return {"signed": f"{v:+.1f}", "num1": f"{v:.1f}", "num2": f"{v:.2f}"}[kind]


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
            # 本頁目錄（1030-11：只做在這一頁）
            st.markdown('<div class="toc"><div class="toc-k">本頁目錄</div>'
                        '<div><a href="#q1">Q1　奪冠的最佳因素是什麼？</a></div>'
                        '<div><a href="#q2">Q2　三分球時代是否造就了近年的冠軍？</a></div>'
                        '<div><a href="#q3">Q3　為什麼這幾年冠軍球隊都不一樣？</a></div>'
                        '<div class="t2"><a href="#q3-1">3-1　實力差距變小了嗎？</a></div>'
                        '<div class="t2"><a href="#q3-2">3-2　每支冠軍的打法都不同嗎？</a></div></div>',
                        unsafe_allow_html=True)

            # ===== Q1 =====
            st.markdown('<div id="q1"></div>', unsafe_allow_html=True)
            q1_slot = section("Q1　奪冠的最佳因素是什麼？",
                    "每個點是一位冠軍在該項指標的聯盟排名（1 = 最好）；◆ 是中位數；越集中在左邊，越是冠軍的共同點", anchor="q1h")
            with q1_slot:
                hypo_only("冠軍最一致的特徵是「淨效率」（整體實力），而不是三分、籃板這類單一項目。")
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
                                   text=f"{f['top5']:.0%} 的冠軍進前 5", font=dict(size=11, color=INK_2))
            fig.update_xaxes(title="聯盟排名（1 = 最好，30 = 最差）", range=[0.3, 38],
                             tickvals=[1, 5, 10, 15, 20, 25, 30])
            fig.update_yaxes(tickvals=list(range(n_f)), ticktext=list(summ["label"][::-1]),
                             showgrid=False, range=[-0.6, n_f - 0.2])
            st.plotly_chart(style(fig, 90 + 46 * n_f), width="stretch")
            with st.expander("這 10 項指標是什麼？（名詞小辭典）", expanded=True):
                st.caption("「回合」＝一隊拿到球、直到投進、失誤或被搶走籃板為止，算一次進攻機會。"
                           "用每 100 回合來比，才不會因為某隊節奏快、出手次數多而看起來比較強。")
                glossary_table(list(summ["label"]))
            best, worst = summ.iloc[0], summ.iloc[-1]
            insight(where=q1_slot, label="發現", check=(
                f"成立：最一致的就是淨效率。" if best["label"] == "淨效率" else
                f"不完全成立：最一致的是{best['label']}，淨效率排第 "
                f"{int(summ.index[summ['label'] == '淨效率'][0]) + 1 if (summ['label'] == '淨效率').any() else '-'} 名。"), lines=[
                f"<b>最一致的因素：{best['label']}</b>：{int(best['n'])} 位冠軍的排名中位數是第 {best['median']:.0f} 名，"
                f"{best['top5']:.0%} 排在聯盟前 5。",
                f"<b>第二、三名：</b>{summ.iloc[1]['label']}（中位數第 {summ.iloc[1]['median']:.0f} 名）、"
                f"{summ.iloc[2]['label']}（第 {summ.iloc[2]['median']:.0f} 名）。",
                f"<b>最不一致：{worst['label']}</b>：中位數第 {worst['median']:.0f} 名，代表冠軍在這項上沒有共同特徵。",
            ])
            st.divider()

            # ===== Q2 =====
            st.markdown('<div id="q2"></div>', unsafe_allow_html=True)
            q2_slot = section("Q2　三分球時代是否造就了近年的冠軍？",
                    "灰線是聯盟平均，淡紫色帶是 30 隊的最低到最高，★ 是當季冠軍；要看的是冠軍「相對於同季聯盟」的位置")
            with q2_slot:
                hypo_only("2019 年後的冠軍，三分出手比例都高於同季聯盟平均（三分投得多的隊伍比較會奪冠）。")
            q2_opts = {"三分出手比例": ("tpar", "pct"), "三分命中率": ("fg3_pct", "pct"),
                       "場均三分出手": ("fg3a_pg", "num1")}
            qa, qb = st.columns([3, 2])
            with qa:
                q2_name = seg("指標", list(q2_opts), "q2")
            with qb:
                q2_view = seg("怎麼看", ["看實際值", "看和聯盟的差"], "q2_view")
            q2_col, q2_kind = q2_opts[q2_name]
            g = LG.groupby("season")
            avg = {"tpar": g["fg3a"].sum() / g["fga"].sum(), "fg3_pct": g["fg3m"].sum() / g["fg3a"].sum(),
                   "fg3a_pg": g["fg3a"].sum() / g["gp"].sum()}[q2_col]
            lo, hi = g[q2_col].min(), g[q2_col].max()
            ch2 = CH.set_index("season")
            diff = (ch2[q2_col] - avg.reindex(ch2.index))
            scale = 100 if q2_kind == "pct" else 1
            unit = "百分點" if q2_kind == "pct" else "次"
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
            if q2_view == "看實際值":
                st.plotly_chart(style(fig, 420), width="stretch")
            fig = go.Figure(go.Bar(
                x=diff.index, y=diff.values * scale,
                marker=dict(color=[ACCENT if v >= 0 else MUTED for v in diff.values]),
                customdata=ch2[["abbreviation"]].values,
                hovertemplate="%{x} 冠軍 %{customdata[0]}<br>比聯盟平均 %{y:+.1f} " + unit + "<extra></extra>"))
            rounded(fig)
            fig.add_hline(y=0, line=dict(color=INK_2, width=1))
            fig.update_xaxes(categoryorder="array", categoryarray=q_seasons, type="category", showgrid=False)
            fig.update_yaxes(title=f"冠軍 − 聯盟平均（{unit}）")
            if q2_view == "看和聯盟的差":
                st.caption("紫色＝冠軍高於當季聯盟平均，灰色＝低於聯盟平均")
                st.plotly_chart(style(fig, 320), width="stretch")
            above = int((diff > 0).sum())
            recent = diff[diff.index >= RECENT]
            r_up = int((recent > 0).sum())
            q2_check = None
            if q2_col == "tpar" and len(recent):
                q2_check = ("成立：2019 年後每一位冠軍都高於聯盟平均。" if r_up == len(recent) else
                            f"不成立：2019 年後 {len(recent)} 位冠軍只有 {r_up} 位高於聯盟平均，三分投得多不是奪冠的必要條件。")
            elif len(recent):
                q2_check = "假設是講三分出手比例；切回「三分出手比例」就能看到對照結果。"
            insight(where=q2_slot, label="發現", check=q2_check, lines=[
                f"<b>聯盟趨勢：</b>{q2_name}從 {q_seasons[0]} 的 {show(avg.iloc[0], q2_kind)} "
                f"變成 {q_seasons[-1]} 的 {show(avg.iloc[-1], q2_kind)}。",
                f"<b>冠軍 vs 聯盟：</b>{len(diff)} 位冠軍中有 {above} 位高於當季聯盟平均"
                + (f"；2019 年後的 {len(recent)} 位中有 {int((recent > 0).sum())} 位。" if len(recent) else "。"),
            ])
            st.divider()

            # ===== Q3 =====
            st.markdown('<div id="q3"></div>', unsafe_allow_html=True)
            section("Q3　為什麼這幾年冠軍球隊都不一樣？", "2019～2026 連續 8 年不同冠軍。下面用兩個可能的原因分別檢驗")
            st.markdown('<div id="q3-1"></div>', unsafe_allow_html=True)
            q3_slot = section("3-1　實力差距變小了嗎？",
                    "用 30 隊的標準差衡量：數值越小，代表強弱越接近", level=2)
            with q3_slot:
                hypo_only("2019 年後，30 隊的實力差距（淨效率標準差）比之前小，所以誰都有機會奪冠。")
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
                             + ("差距變小了。" if change < 0 else "差距沒有變小。"))
            if len(ch_recent):
                k = int((ch_recent["rk_net_rating"] == 1).sum())
                lines.append(f"<b>最強的隊不一定奪冠：</b>2019 年後 {len(ch_recent)} 位冠軍中，"
                             f"只有 {k} 位是例行賽淨效率第 1 名。")
            q3_check = None
            if len(before) and len(after):
                q3_check = ("成立：2019 年後標準差比較小，強弱比較接近。" if after.mean() < before.mean()
                            else "不成立：2019 年後標準差沒有變小，冠軍輪替不是因為大家實力變接近。")
            insight(lines, where=q3_slot, label="發現", check=q3_check)

            st.markdown('<div id="q3-2"></div>', unsafe_allow_html=True)
            q32_slot = section("3-2　每支冠軍的打法都不同嗎？",
                    "近年冠軍在各項打法的聯盟排名；顏色越深代表排名越前面。節奏第 1 = 最快，失誤少第 1 = 失誤最少", level=2)
            with q32_slot:
                hypo_only("近年冠軍的打法各不相同：7 項打法中，沒有任何一項是每位冠軍都排聯盟前 10。")
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
            zdf = pd.DataFrame(zr, columns=[x[0] for x in STYLE])
            all10 = [c for c in zdf.columns if (zdf[c] <= 10).all()]
            most = (zdf <= 10).mean().sort_values(ascending=False)
            insight(where=q32_slot, label="發現", lines=[
                (f"{len(labels)} 位近年冠軍都排前 10 的打法：{'、'.join(all10)}。" if all10 else
                 f"{len(labels)} 位近年冠軍中，沒有任何一項打法是每位都排聯盟前 10。"),
                f"最多冠軍排前 10 的是<b>{most.index[0]}</b>（{most.iloc[0]:.0%}）；最少的是<b>{most.index[-1]}</b>（{most.iloc[-1]:.0%}）。",
                "讀法：如果每一列亮的位置都不同，代表冠軍靠的是不同的打法，沒有單一的致勝公式。",
            ], check=("成立：冠軍打法各不相同，沒有單一的致勝公式。" if not all10
                      else f"不成立：{'、'.join(all10)}是每位近年冠軍的共同點。"))


# ---------- 每日戰報：昨晚發生什麼事？（全聯盟比分、值得關注的球員、球隊隱憂、戰績榜）----------
EAST = {"ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL", "NYK", "ORL", "PHI", "TOR", "WAS"}
RECAP_TYPES = {"Regular Season": "例行賽", "PlayIn": "附加賽", "Playoffs": "季後賽"}


def _read_filtered(table, filters, order, page=1000):
    """分頁讀取＋篩選；資料表不存在或連線出錯時回傳空表格（畫面會提示要先載入資料）"""
    rows, start = [], 0
    try:
        while True:
            q = get_client().table(table).select("*")
            for op, col, val in filters:
                q = getattr(q, op)(col, val)
            for c in order:
                q = q.order(c)
            part = q.range(start, start + page - 1).execute().data
            rows += part
            if len(part) < page:
                break
            start += page
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


@st.cache_data(ttl=900, show_spinner="讀取本季比分中…")
def load_recap_teams():
    """全聯盟本季（最新球季）每場比賽 × 每隊；一季約 2,500 筆"""
    try:
        latest = (get_client().table("recap_team_games").select("season")
                  .order("season", desc=True).limit(1).execute().data)
    except Exception:
        return pd.DataFrame()
    if not latest:
        return pd.DataFrame()
    df = _read_filtered("recap_team_games", [("eq", "season", latest[0]["season"])],
                        ["game_date", "game_id", "team_id"])
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


@st.cache_data(ttl=900, show_spinner="讀取球員數據中…")
def load_recap_players(season, since):
    """某球季、某天之後的球員逐場（只讀最近兩週，不用每次搬整季）"""
    df = _read_filtered("recap_player_games", [("eq", "season", season), ("gte", "game_date", since)],
                        ["game_date", "game_id", "player_id"])
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


@st.cache_data(ttl=900)
def load_recap_season(season):
    return _read_filtered("recap_player_season", [("eq", "season", season)], ["player_id", "team_id"])


def badge(abbr, size=46):
    """球隊徽章：球衣主色的圓角方塊＋縮寫（不用官方隊徽，避免商標問題）"""
    c = TEAM_COLORS.get(abbr, "#4b4560")
    return (f'<div class="rc-badge" style="background:{c};width:{size}px;height:{size}px;'
            f'font-size:{size * 0.3:.0f}px">{abbr}</div>')


def record_through(tg, abbr, day):
    """某隊到某一天為止的戰績（含當天）"""
    d = tg[(tg["abbreviation"] == abbr) & (tg["game_date"] <= day) & (tg["season_type"] == "Regular Season")]
    return f'{int((d["wl"] == "W").sum())}-{int((d["wl"] == "L").sum())}'


def stat_line(r):
    """球員數據：只列有亮點的項目，像 NBA 官方圖卡"""
    parts = [f'<b>{int(r.pts)}</b> 分']
    if r.reb >= 5:
        parts.append(f'<b>{int(r.reb)}</b> 籃板')
    if r.ast >= 5:
        parts.append(f'<b>{int(r.ast)}</b> 助攻')
    if r.fg3m >= 4:
        parts.append(f'<b>{int(r.fg3m)}</b> 三分')
    if r.stl >= 3:
        parts.append(f'<b>{int(r.stl)}</b> 抄截')
    if r.blk >= 3:
        parts.append(f'<b>{int(r.blk)}</b> 阻攻')
    return "　".join(parts)


def game_score(r):
    """一場表現的綜合分數（Hollinger Game Score 簡化版），用來挑每場的最佳球員"""
    return (r.pts + 0.4 * r.fgm - 0.7 * r.fga - 0.4 * (r.fta - r.ftm) + 0.7 * r.oreb + 0.3 * r.dreb
            + r.stl + 0.7 * r.ast + 0.7 * r.blk - 0.4 * r.pf - r.tov)


def standouts(day_rows, season_avg):
    """依規則找出值得關注的球員：每條規則都寫得出原因，不是黑盒子"""
    out = []
    avg = season_avg.set_index(["player_id", "team_id"]) if not season_avg.empty else None
    for _, r in day_rows.iterrows():
        tags, score = [], 0
        fga_fta = r.fga + 0.44 * r.fta
        ts = r.pts / (2 * fga_fta) if fga_fta > 0 else None
        doubles = sum(v >= 10 for v in [r.pts, r.reb, r.ast, r.stl, r.blk])
        base = None
        if avg is not None and (r.player_id, r.team_id) in avg.index:
            a = avg.loc[(r.player_id, r.team_id)]
            if a.gp >= 3:   # 扣掉今天這場，算「平常」場均
                base = (a.pts - r.pts) / (a.gp - 1)
        if r.pts >= 40:
            tags.append(f"{int(r.pts)} 分爆發"); score += 4
        elif r.pts >= 30:
            tags.append(f"{int(r.pts)} 分"); score += 2
        if doubles >= 3:
            tags.append("大三元"); score += 4
        if r.fg3m >= 7:
            tags.append(f"{int(r.fg3m)} 記三分"); score += 2
        if ts and ts >= 0.70 and r.fga >= 12:
            tags.append(f"真實命中率 {ts:.0%}"); score += 2
        if base is not None and r.pts >= base + 12 and r.pts >= 20:
            tags.append(f"比平常多 {r.pts - base:.0f} 分"); score += 3
            if base < 12:
                tags.append("超常發揮"); score += 1
        if r.stl + r.blk >= 6:
            tags.append(f"抄截＋阻攻 {int(r.stl + r.blk)}"); score += 2
        if tags:
            out.append({**r.to_dict(), "tags": tags, "score": score + game_score(r) / 20, "base": base})
    return sorted(out, key=lambda x: -x["score"])


def team_concerns(tg, pl, season_avg, day):
    """球隊隱憂：比較「最近幾場」和「本季平均」，加上連敗與主力缺陣；每條都附數字"""
    out = []
    reg = tg[(tg["game_date"] <= day) & (tg["season_type"] == "Regular Season")]
    for abbr, g in reg.groupby("abbreviation"):
        g = g.sort_values("game_date")
        n, items = len(g), []
        # 連敗
        streak = 0
        for wl in g["wl"][::-1]:
            if wl != "L":
                break
            streak += 1
        if streak >= 3:
            items.append((3 + streak - 3, f"{streak} 連敗"))
        if n >= 6:   # 開季太早，近況和平均幾乎一樣，不比
            last, allg = g.tail(5), g
            d_opp = last["opp_pts"].mean() - allg["opp_pts"].mean()
            if d_opp >= 6:
                items.append((2, f"防守下滑：近 5 場失分 {last['opp_pts'].mean():.0f}，比本季平均多 {d_opp:.0f}"))
            p3_l = last["fg3m"].sum() / max(last["fg3a"].sum(), 1)
            p3_a = allg["fg3m"].sum() / max(allg["fg3a"].sum(), 1)
            if p3_a - p3_l >= 0.04:
                items.append((2, f"三分失準：近 5 場 {p3_l:.1%}，本季 {p3_a:.1%}"))
            d_tov = last["tov"].mean() - allg["tov"].mean()
            if d_tov >= 2.5:
                items.append((1, f"失誤變多：近 5 場每場 {last['tov'].mean():.1f} 次（多 {d_tov:.1f}）"))
            d_pm = last["plus_minus"].mean() - allg["plus_minus"].mean()
            if d_pm <= -8:
                items.append((2, f"近況變差：近 5 場淨勝分 {last['plus_minus'].mean():+.1f}，本季 {allg['plus_minus'].mean():+.1f}"))
        # 主力：這隊本季場均上場最多的球員
        if not season_avg.empty and not pl.empty:
            sa = season_avg[(season_avg["abbreviation"] == abbr) & (season_avg["gp"] >= 2)].copy()
            if not sa.empty:
                sa["mpg"] = sa["min"] / sa["gp"]
                sa["ppg"] = sa["pts"] / sa["gp"]
                star = sa.sort_values("mpg").iloc[-1]
                last_game = g.iloc[-1]["game_id"]
                played = set(pl[pl["game_id"] == last_game]["player_id"])
                if pl["game_id"].eq(last_game).any() and star.player_id not in played:
                    items.append((3, f"主力未出賽：{star.player_name}（場均 {star.mpg:.0f} 分鐘）上一場沒有上場"))
                top = sa.sort_values("ppg").iloc[-1]
                rec = pl[(pl["player_id"] == top.player_id) & (pl["abbreviation"] == abbr)].sort_values("game_date").tail(3)
                if len(rec) == 3 and top.gp >= 6 and rec["pts"].mean() < top.ppg * 0.7:
                    items.append((2, f"得分手低迷：{top.player_name} 近 3 場 {rec['pts'].mean():.1f} 分，本季 {top.ppg:.1f} 分"))
        if items:
            items.sort(key=lambda x: -x[0])
            w, l = int((g["wl"] == "W").sum()), int((g["wl"] == "L").sum())
            out.append({"abbr": abbr, "record": f"{w}-{l}", "items": [t for _, t in items],
                        "severity": sum(s for s, _ in items), "played_today": (g["game_date"] == day).any()})
    return sorted(out, key=lambda x: (-x["severity"], x["abbr"]))


def standings(tg, day, conf):
    reg = tg[(tg["game_date"] <= day) & (tg["season_type"] == "Regular Season")]
    rows = []
    for abbr, g in reg.groupby("abbreviation"):
        if (abbr in EAST) != (conf == "東區"):
            continue
        g = g.sort_values("game_date")
        w, l = int((g["wl"] == "W").sum()), int((g["wl"] == "L").sum())
        s, last = 0, None
        for wl in g["wl"][::-1]:
            if last is None:
                last = wl
            if wl != last:
                break
            s += 1
        l10 = g.tail(10)
        rows.append({"_key": abbr, "球隊": team_label(abbr), "勝": w, "敗": l, "_pct": w / max(w + l, 1),
                     "勝率": f"{w / max(w + l, 1):.3f}".lstrip("0") if w + l else "-",
                     "近 10 場": f'{int((l10["wl"] == "W").sum())}-{int((l10["wl"] == "L").sum())}',
                     "連勝敗": f"{'連勝' if last == 'W' else '連敗'} {s}" if last else "-",
                     "場均淨勝": f"{g['plus_minus'].mean():+.1f}"})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).sort_values(["_pct", "勝"], ascending=[False, False]).reset_index(drop=True)
    lead = df.iloc[0]
    df["勝差"] = [("-" if i == 0 else f"{((lead['勝'] - r['勝']) + (r['敗'] - lead['敗'])) / 2:g}")
                  for i, r in df.iterrows()]
    df.insert(0, "#", range(1, len(df) + 1))
    return df[["#", "_key", "球隊", "勝", "敗", "勝率", "勝差", "近 10 場", "連勝敗", "場均淨勝"]]


# ---------- 每日戰報：下一場預測（比賽勝率、球員表現）----------
from predict import (B2B_PENALTY, GAME_SD, HOME_EDGE, SHRINK, STAR_PENALTY,  # noqa: E402  共用的預測算法
                     missing_stars, predict_game, project_players, team_ratings, win_prob)


@st.cache_data(ttl=900)
def load_schedule_after(season, after):
    df = _read_filtered("recap_schedule", [("eq", "season", season), ("gt", "game_date", after)],
                        ["game_date", "game_id"])
    if not df.empty:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


@st.cache_data(ttl=900, show_spinner="計算預測準確率中…")
def backtest(tg):
    """回頭驗證：本季每場已打完的比賽，只用「比賽前」的資料預測，看猜對幾場"""
    reg = tg[tg["season_type"] == "Regular Season"]
    right = total = 0
    for day in sorted(reg["game_date"].unique()):
        day = pd.Timestamp(day)
        ratings, lg = team_ratings(reg[reg["game_date"] < day])
        for _, g in reg[reg["game_date"] == day].groupby("game_id"):
            if len(g) != 2 or not g["is_home"].astype(bool).any():
                continue
            hm = g[g["is_home"].astype(bool)].iloc[0]
            aw = g[~g["is_home"].astype(bool)].iloc[0]
            if ratings.get(hm["abbreviation"], {}).get("n", 0) < 3 or ratings.get(aw["abbreviation"], {}).get("n", 0) < 3:
                continue
            p = predict_game(hm["abbreviation"], aw["abbreviation"], day, ratings, lg)
            if p:
                total += 1
                right += int((p["p_home"] >= 0.5) == (hm["wl"] == "W"))
    return right, total


def render_predictions(tg, season):
    last_done = tg["game_date"].max()
    sched = load_schedule_after(season, last_done.strftime("%Y-%m-%d"))
    section("下一個比賽日：預測", "勝率與預估比分只用本季打過的比賽計算；球員是預估的合理範圍，不是保證")
    if sched.empty:
        st.info("還沒有賽程資料。請先在 Supabase 執行 schema_schedule.sql，再在電腦上執行：python load_recap.py")
        return
    day = sched["game_date"].min()
    games = sched[sched["game_date"] == day]
    since = (last_done - pd.Timedelta(days=21)).strftime("%Y-%m-%d")
    pl_ = load_recap_players(season, since)
    sa_ = load_recap_season(season)
    ratings, lg = team_ratings(tg)
    missing = missing_stars(pl_, sa_)
    right, total = backtest(tg)
    acc = f"本季已回頭驗證 {total} 場：猜對 {right} 場（{right / total:.0%}）。" if total else "開季場數還太少，尚未驗證準確率。"
    insight([f"<b>{day:%m/%d}</b>（美國時間）共 <b>{len(games)}</b> 場比賽。{acc}"
             "NBA 預測模型一般的猜對率大約 6～7 成，比賽本來就有很大的運氣成分。"])

    cards = []
    for g in games.itertuples():
        p = predict_game(g.home_abbr, g.away_abbr, day, ratings, lg, missing)
        if p is None:
            cards.append(f'<div class="rc-card"><div class="rc-row"><div class="rc-team">{badge(g.away_abbr)}</div>'
                         f'<div class="rc-final">本季還沒打過<br>無法預測</div><div class="rc-team">{badge(g.home_abbr)}</div></div></div>')
            continue
        ph = p["p_home"]
        ca, chh = TEAM_COLORS.get(g.away_abbr, "#6f6883"), TEAM_COLORS.get(g.home_abbr, "#6f6883")
        fav = g.home_abbr if ph >= 0.5 else g.away_abbr
        players = ""
        for abbr, opp in [(g.away_abbr, g.home_abbr), (g.home_abbr, g.away_abbr)]:
            for r in project_players(abbr, opp, pl_, sa_, ratings, lg, n=2):
                warn = '<span style="color:#f59e0b">（上一場未出賽）</span>' if r["out"] else ""
                players += (f'<div class="rc-pp"><span class="ab" style="background:{TEAM_COLORS.get(abbr, "#4b4560")}">{abbr}</span>'
                            f'<span class="nm">{r["name"]}</span>{warn}<span class="v"><b>{r["pts"]:.0f}</b> 分'
                            f'<small>（{r["lo"]:.0f}–{r["hi"]:.0f}）</small>　{r["reb"]:.0f} 板　{r["ast"]:.0f} 助</span></div>')
        status = g.status if isinstance(g.status, str) and g.status and "Final" not in g.status else ""
        cards.append(f'''<div class="rc-card"><div class="rc-row">
  <div class="rc-team">{badge(g.away_abbr)}<div class="rc-rec">{record_through(tg, g.away_abbr, last_done)}</div></div>
  <div class="rc-score {'rc-win' if ph < 0.5 else 'rc-lose'}">{p["away_pts"]:.0f}</div>
  <div class="rc-final">預測<small>{status}</small></div>
  <div class="rc-score {'rc-win' if ph >= 0.5 else 'rc-lose'}">{p["home_pts"]:.0f}</div>
  <div class="rc-team">{badge(g.home_abbr)}<div class="rc-rec">{record_through(tg, g.home_abbr, last_done)}</div></div>
</div>
<div class="rc-prob"><span style="width:{(1 - ph) * 100:.0f}%;background:{ca}"></span><span style="width:{ph * 100:.0f}%;background:{chh}"></span></div>
<div class="rc-probtxt"><span>{g.away_abbr} {1 - ph:.0%}</span><span>{fav} 較有機會</span><span>{g.home_abbr} {ph:.0%}</span></div>
<div class="rc-why">{"・".join(p["factors"])}</div>{players}</div>''')
    with fold(f"{len(cards)} 場預測卡（勝率、預估比分、球員表現範圍）"):
        cols = st.columns(3, gap="medium")
        for i, c in enumerate(cards):
            cols[i % 3].markdown(c, unsafe_allow_html=True)

    with st.expander("預測怎麼算的"):
        st.markdown(f"""
**比賽勝率**
1. 每隊的實力＝本季**場均淨勝分**。開季場數少不穩定，所以打了 n 場只相信 n／(n+{SHRINK})，其餘當作聯盟平均（0 分）。
2. 預測分差＝主隊實力 − 客隊實力 ＋ 主場優勢 {HOME_EDGE} 分；前一天才打過（背靠背）的球隊 −{B2B_PENALTY} 分；上場時間最多的主力上一場沒上場 −{STAR_PENALTY:g} 分（不知道他下一場會不會回來，只是提醒）。
3. 分差換成勝率：真實比賽和預測大約會差 ±{GAME_SD:g} 分，所以預測贏 5 分的球隊，勝率大約 66%，不是 100%。
4. 預估比分＝（自己平常得分＋對手平常失分）÷ 2，再依預測分差左右分開。
5. **回頭驗證**：本季每一場打完的比賽，都只用「那一天以前」的資料重算一次，看猜對幾場；兩隊都至少打過 3 場才算。
6. **每天對答案**：這份預測每天會在比賽前存進資料庫，隔天比賽打完，下方「預測準不準」會把預測和實際結果對照，所有紀錄都能回頭看。

**球員表現**
- 預估＝最近 10 場平均 × 0.6 ＋ 本季平均 × 0.4（最近狀況比較重要，但不能只看最近）。
- 得分再看對手防守：對手平常失分比聯盟平均高，就往上調，最多 ±8%。
- 括號裡是合理範圍：用他最近幾場得分的起伏（標準差）估計，大約 7 成的比賽會落在這個範圍內。

**沒有考慮的**：傷兵名單、先發陣容、交易、旅行距離、球員之間的對位。這些資料庫目前沒有。
""")


# ---------- 每日戰報：預測準不準（前一天存下的預測 vs 實際結果）----------
OK_TXT = '<span style="color:#15803d;font-weight:700">✓ 猜對</span>'
NG_TXT = '<span style="color:#b91c1c;font-weight:700">✗ 猜錯</span>'


@st.cache_data(ttl=900, show_spinner="讀取預測紀錄中…")
def load_saved_predictions(season):
    g = _read_filtered("recap_predictions", [("eq", "season", season)], ["game_date", "game_id"])
    p = _read_filtered("recap_player_predictions", [("eq", "season", season)], ["game_date", "game_id", "player_id"])
    for d in (g, p):
        if not d.empty:
            d["game_date"] = pd.to_datetime(d["game_date"])
    return g, p


def graded_games(tg, preds):
    """把存下的預測和實際比分對起來：猜對沒、比分差多少"""
    if preds.empty:
        return pd.DataFrame()
    t = tg[[c for c in ["game_id", "is_home", "pts", "abbreviation", "matchup"] if c in tg]].copy()
    # 主客標示：空白（None）一律先當成 False，不能直接 astype(bool)
    t["is_home"] = t["is_home"].map(lambda v: str(v).strip().lower() in ("true", "t", "1"))
    bad = t.groupby("game_id")["is_home"].transform("sum") != 1    # 這場不是「剛好一個主隊」
    if bad.any() and "matchup" in t:
        host = t["matchup"].astype(str).str.extract(r"@\s*(\w+)")[0]   # 「LAL @ UTA」→ UTA 是主隊
        host = host.groupby(t["game_id"]).transform("first")
        t.loc[bad, "is_home"] = t.loc[bad, "abbreviation"] == host[bad]
    home = t[t["is_home"]].drop_duplicates("game_id").set_index("game_id")    # 每場只留一列，避免對答案時重複
    away = t[~t["is_home"]].drop_duplicates("game_id").set_index("game_id")
    df = preds[preds["game_id"].isin(home.index) & preds["game_id"].isin(away.index)].copy()
    if df.empty:
        return df
    for c in ["p_home", "home_pts", "away_pts", "margin"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["act_home"] = df["game_id"].map(home["pts"]).astype(float)
    df["act_away"] = df["game_id"].map(away["pts"]).astype(float)
    df["fav"] = [h if p >= 0.5 else a for h, a, p in zip(df["home_abbr"], df["away_abbr"], df["p_home"])]
    df["winner"] = [h if x > y else a for h, a, x, y in zip(df["home_abbr"], df["away_abbr"], df["act_home"], df["act_away"])]
    df["right"] = df["fav"] == df["winner"]
    df["conf"] = df["p_home"].where(df["p_home"] >= 0.5, 1 - df["p_home"])
    df["margin_err"] = ((df["act_home"] - df["act_away"]) - df["margin"]).abs()
    df["score_err"] = ((df["act_home"] - df["home_pts"]).abs() + (df["act_away"] - df["away_pts"]).abs()) / 2
    return df


def day_summary(gd):
    if gd.empty:
        return pd.DataFrame()
    out = (gd.groupby("game_date")
             .agg(n=("right", "size"), right=("right", "sum"), margin_err=("margin_err", "mean"),
                  live=("source", lambda s: (s == "當天存下").all()))
             .reset_index().sort_values("game_date"))
    out["acc"] = out["right"] / out["n"]
    out["cum_acc"] = out["right"].cumsum() / out["n"].cumsum()
    return out


def render_pred_review(tg, season):
    section("預測準不準（對答案）", "前一天存下的預測 vs 實際結果；每天自動對一次，所有紀錄都可以回頭看")
    preds, ppreds = load_saved_predictions(season)
    if preds.empty:
        st.info("還沒有存下的預測。請先在 Supabase 執行 schema_predictions.sql，"
                "之後每天的自動更新（daily_update.py）就會把預測存起來，隔天比賽打完自動對答案。"
                "想立刻補上本季每一天，可以在電腦上執行：python save_predictions.py --backfill")
        return
    gd = graded_games(tg, preds)
    if gd.empty:
        st.caption("已經存下預測，但那些比賽還沒打完。等比賽結束、隔天資料更新後，這裡就會出現對答案的結果。")
        return
    ds = day_summary(gd)
    last = ds.iloc[-1]
    lines = [f"<b>{last['game_date']:%m/%d}</b>（美國時間）預測 <b>{int(last['n'])}</b> 場，"
             f"猜對 <b>{int(last['right'])}</b> 場（{last['acc']:.0%}）；預測分差平均差了 {last['margin_err']:.1f} 分。"]
    if len(ds) >= 2:
        prev = ds.iloc[-2]
        diff = (last["acc"] - prev["acc"]) * 100
        trend = "持平" if abs(diff) < 0.5 else (f"進步 {diff:.0f} 個百分點" if diff > 0 else f"退步 {-diff:.0f} 個百分點")
        lines.append(f"和前一個比賽日 <b>{prev['game_date']:%m/%d}</b>（{int(prev['right'])}/{int(prev['n'])}，"
                     f"{prev['acc']:.0%}）相比：<b>{trend}</b>。")
    live = gd[gd["source"] == "當天存下"]
    if len(live):
        lines.append(f"本季累計（比賽前就存下的）：{int(live['right'].sum())}/{len(live)}（{live['right'].mean():.0%}）"
                     + (f"；加上事後回推的共 {int(gd['right'].sum())}/{len(gd)}（{gd['right'].mean():.0%}）。"
                        if len(live) < len(gd) else "。"))
    else:
        lines.append(f"本季累計（事後回推）：{int(gd['right'].sum())}/{len(gd)}（{gd['right'].mean():.0%}）。"
                     "從現在開始，每天比賽前存下的預測會另外統計。")
    insight(lines)

    # 每天的猜對率：直條＝當天，折線＝累計
    with fold(f"每天的猜對率（共 {len(ds)} 個比賽日）"):
        fig = go.Figure()
        fig.add_trace(go.Bar(x=ds["game_date"], y=ds["acc"], name="當天猜對率",
                             marker=dict(color=[ACCENT if l else "#c4b5fd" for l in ds["live"]]),
                             customdata=ds[["right", "n"]].values,
                             hovertemplate="%{x|%m/%d}　猜對 %{customdata[0]}/%{customdata[1]}（%{y:.0%}）<extra></extra>"))
        fig.add_trace(go.Scatter(x=ds["game_date"], y=ds["cum_acc"], name="本季累計", mode="lines+markers",
                                 line=dict(color=INK_2, width=2), marker=dict(size=5),
                                 hovertemplate="%{x|%m/%d}　累計 %{y:.0%}<extra></extra>"))
        fig.add_hline(y=0.5, line=dict(color=MUTED, dash="dot", width=1),
                      annotation_text="亂猜 50%", annotation_position="bottom right")
        fig.update_yaxes(tickformat=".0%", range=[0, 1.05])
        fig.update_xaxes(tickformat="%m/%d")
        rounded(fig)
        st.caption("深紫色＝比賽前就存下的預測；淺紫色＝事後用「那天以前的資料」回推的。")
        st.plotly_chart(style(fig, 300), width="stretch")

    # 選一天回頭看
    # 整季每一天都列出來（下拉選單），最新的在最上面；選項裡直接寫那天猜對幾場
    days = list(ds["game_date"][::-1])
    acc_txt = {d: f"猜對 {int(r)}/{int(n)}" for d, r, n in zip(ds["game_date"], ds["right"], ds["n"])}
    pick = st.selectbox(f"回頭看哪一天的預測（美國時間，本季共 {len(days)} 天）", days, index=0, key="pr_day_all",
                        format_func=lambda d: f"{pd.Timestamp(d):%m/%d}（週{'一二三四五六日'[pd.Timestamp(d).weekday()]}）"
                                              f"　{acc_txt.get(d, '')}" + ("　最新" if d == days[0] else ""))
    day = pd.Timestamp(pick)
    g = gd[gd["game_date"] == day].sort_values("conf", ascending=False)
    rows = []
    for r in g.itertuples():
        rows.append({"比賽": f"{r.away_abbr} @ {r.home_abbr}", "看好": team_label(r.fav), "_key": r.fav,
                     "勝率": f"{r.conf:.0%}", "預測比分": f"{r.away_pts:.0f} : {r.home_pts:.0f}",
                     "實際比分": f"{r.act_away:.0f} : {r.act_home:.0f}", "結果": OK_TXT if r.right else NG_TXT,
                     "分差差了": f"{r.margin_err:.0f} 分", "來源": r.source})
    st.markdown(f'<div class="chart-headline">{day:%m/%d}：猜對 {int(g["right"].sum())}/{len(g)} 場</div>',
                unsafe_allow_html=True)
    nice_table(pd.DataFrame(rows), num_cols=("勝率", "預測比分", "實際比分", "分差差了"), dot_col="看好", colors=TEAM_COLORS)
    wrong_sure = g[(~g["right"]) & (g["conf"] >= 0.65)]
    if len(wrong_sure):
        st.caption("爆冷門（有 65% 以上把握卻猜錯）：" + "、".join(
            f"{r.winner} 贏了（原本看好 {r.fav} {r.conf:.0%}）" for r in wrong_sure.itertuples()))

    # 球員：預估 vs 實際
    pp = ppreds[ppreds["game_date"] == day] if not ppreds.empty else ppreds
    if pp.empty:
        return
    act = load_recap_players(season, day.strftime("%Y-%m-%d"))
    act = act[act["game_date"] == day] if not act.empty else act
    a_idx = act.set_index(["game_id", "player_id"]) if not act.empty else None
    prow, inside, n_played = [], 0, 0
    for r in pp.itertuples():
        key = (r.game_id, int(r.player_id))
        has = a_idx is not None and key in a_idx.index
        a = a_idx.loc[key] if has else None
        if a is not None and isinstance(a, pd.DataFrame):
            a = a.iloc[0]
        lo, hi, est = float(r.pts_lo), float(r.pts_hi), float(r.pts)
        if a is None:
            verdict, apts = '<span style="color:#8f889f">沒上場</span>', "-"
        else:
            n_played += 1
            v = float(a["pts"])
            apts = f"{v:.0f}"
            if lo <= v <= hi:
                inside += 1
                verdict = '<span style="color:#15803d;font-weight:700">在範圍內</span>'
            else:
                verdict = ('<span style="color:#7c3aed;font-weight:700">比預估好</span>' if v > hi
                           else '<span style="color:#b45309;font-weight:700">比預估差</span>')
        prow.append({"球員": r.player_name, "_key": r.abbreviation, "球隊": team_label(r.abbreviation),
                     "預估得分": f"{est:.0f}", "範圍": f"{lo:.0f}–{hi:.0f}", "實際得分": apts, "判定": verdict,
                     "籃板 預估→實際": f"{float(r.reb):.0f} → {a['reb']:.0f}" if a is not None else "-",
                     "助攻 預估→實際": f"{float(r.ast):.0f} → {a['ast']:.0f}" if a is not None else "-"})
    head = (f"球員得分：{n_played} 位有上場，{inside} 位落在預估範圍內（{inside / n_played:.0%}）"
            if n_played else "球員得分：被預估的球員都沒有上場")
    with fold(head):
        st.caption("範圍是用他最近幾場得分的起伏估的，理想上大約 7 成會落在範圍內。")
        nice_table(pd.DataFrame(prow), num_cols=("預估得分", "範圍", "實際得分", "籃板 預估→實際", "助攻 預估→實際"),
                   dot_col="球隊", colors=TEAM_COLORS)



def fold(label):
    """每日戰報的大區塊：可以收起來的框。最上面的「全部展開／全部收起」決定一開始是打開還是收起
    （每個區塊的一句話結論放在框外面，收起來也看得到重點）"""
    return st.expander(label, expanded=st.session_state.get("rc_open", "全部展開") == "全部展開")


# ---------- 每日戰報：逐回合紀錄（比賽走勢、關鍵時刻、今日戰報稿）----------
@st.cache_data(ttl=900, show_spinner="讀取比賽走勢中…")
def load_pbp_flow(season, day):
    """某一天所有比賽的走勢摘要（pbp_game_flow，一場一筆）"""
    return _read_filtered("pbp_game_flow", [("eq", "season", season), ("eq", "game_date", day)], ["game_id"])


@st.cache_data(ttl=900, show_spinner="讀取逐回合得分中…")
def load_pbp_events(season, day):
    """某一天所有比賽的每一次得分（一場約 120 筆）"""
    df = _read_filtered("pbp_events", [("eq", "season", season), ("eq", "game_date", day)],
                        ["game_id", "action_number"])
    for c in ["period", "clock_sec", "elapsed_sec", "points", "score_home", "score_away"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def period_name(p):
    p = int(p or 0)
    return f"第 {p} 節" if p <= 4 else ("延長賽" if p == 5 else f"第 {p - 4} 次延長")


def drama(r):
    """這場有多精彩：領先互換＋平手＋關鍵時刻＋逆轉，數字越大越值得看"""
    return (int(r["lead_changes"] or 0) + int(r["times_tied"] or 0) * 0.5
            + (8 if r["clutch_game"] else 0) + int(r["comeback_pts"] or 0) * 0.4
            - abs(int(r["home_pts"] or 0) - int(r["away_pts"] or 0)) * 0.3)


def clutch_leaders(ev):
    """關鍵時刻（第四節或延長賽最後 5 分鐘、分差 5 分以內）誰得最多分"""
    if ev.empty or "is_clutch" not in ev:
        return pd.DataFrame()
    c = ev[ev["is_clutch"].astype(bool)]
    if c.empty:
        return pd.DataFrame()
    g = (c.groupby(["player_name", "team_abbr", "game_id"])
         .agg(pts=("points", "sum"), threes=("action_type", lambda s: int((s == "3PT").sum())),
              shots=("points", "size")).reset_index())
    return g.sort_values(["pts", "threes"], ascending=False)


def recap_script(day, n_games, flow, ev, top, recs=None):
    """今日戰報稿：只講重點，一行一件事，每一句都由資料算出來"""
    zh = lambda a_: ALL_ZH.get(a_, a_)                       # noqa: E731
    out = [f"{day:%m/%d}（美國時間）{n_games} 場比賽"]
    if not flow.empty:
        f = flow.copy()
        f["drama"] = [drama(r) for _, r in f.iterrows()]
        b = f.sort_values("drama").iloc[-1]
        hw = b["home_pts"] > b["away_pts"]
        w, l_ = (b["home_abbr"], b["away_abbr"]) if hw else (b["away_abbr"], b["home_abbr"])
        out.append(f"精選對戰：{zh(w)} {int(max(b['home_pts'], b['away_pts']))}–{int(min(b['home_pts'], b['away_pts']))} {zh(l_)}，"
                   f"領先互換 {int(b['lead_changes'])} 次、平手 {int(b['times_tied'])} 次"
                   + ("，最後 5 分鐘仍在 5 分差內" if b["clutch_game"] else ""))
        cb = f.sort_values("comeback_pts").iloc[-1]
        if int(cb["comeback_pts"] or 0) >= 10:
            loser = cb["away_abbr"] if cb["comeback_team"] == cb["home_abbr"] else cb["home_abbr"]
            out.append(f"逆轉勝：{zh(cb['comeback_team'])} 落後 {int(cb['comeback_pts'])} 分逆轉 {zh(loser)}")
        run_ = f.sort_values("best_run_pts").iloc[-1]
        if int(run_["best_run_pts"] or 0) >= 10:
            out.append(f"攻勢亮點：{zh(run_['best_run_team'])} {period_name(run_['best_run_period'])} {int(run_['best_run_pts'])}–0")
        blow = f.assign(m=(f["home_pts"] - f["away_pts"]).abs()).sort_values("m").iloc[-1]
        if int(blow["m"]) >= 20:
            w_ = blow["home_abbr"] if blow["home_pts"] > blow["away_pts"] else blow["away_abbr"]
            out.append(f"大勝：{zh(w_)} 贏 {int(blow['m'])} 分")
    if top is not None:
        out.append(f"最佳球員：{top.player_name}（{zh(top.abbreviation)}）{int(top.pts)} 分 {int(top.reb)} 籃板 {int(top.ast)} 助攻")
    cl = clutch_leaders(ev)
    if not cl.empty and int(cl.iloc[0]["pts"]) >= 4:
        c0 = cl.iloc[0]
        out.append(f"關鍵先生：{c0['player_name']}（{zh(c0['team_abbr'])}）最後 5 分鐘 {int(c0['pts'])} 分"
                   + (f"（{int(c0['threes'])} 記三分）" if int(c0["threes"]) else ""))
    for name_, why in (recs or []):
        out.append(f"推薦球員：{name_}，{why}")
    return out


def recommend_players(day_pl, pl, sa, day, top, n=2):
    """推薦球員：①今天值得關注（扣掉最佳球員）②近況火熱（最近 5 場平均比本季平常多 5 分以上）。回傳 [(名字, 原因)]"""
    zh = lambda a_: ALL_ZH.get(a_, a_)                       # noqa: E731
    skip = {getattr(top, "player_id", None)}
    out = []
    so = standouts(day_pl, sa) if not day_pl.empty else []
    for r in so:
        if r.get("player_id") in skip:
            continue
        out.append((f"{r['player_name']}（{zh(r['abbreviation'])}）", "今天 " + "、".join(r["tags"][:2])))
        skip.add(r.get("player_id"))
        break
    if not pl.empty and not sa.empty:
        recent = pl[pl["game_date"] <= day].sort_values("game_date")
        last5 = recent.groupby(["player_id", "team_id"]).tail(5)
        g = last5.groupby(["player_id", "team_id"]).agg(n=("pts", "size"), pts5=("pts", "mean"),
                                                         name=("player_name", "last"), abbr=("abbreviation", "last"))
        a = sa.set_index(["player_id", "team_id"])[["gp", "pts"]].apply(pd.to_numeric, errors="coerce")
        g = g.join(a.rename(columns={"pts": "pts_all"}), how="inner")
        g = g[(g["n"] >= 4) & (g["gp"] >= 6)]
        g["base"] = (g["pts_all"] - g["pts5"] * g["n"]) / (g["gp"] - g["n"]).where(g["gp"] > g["n"])
        g["up"] = g["pts5"] - g["base"]
        g = g[(g["up"] >= 5) & (g["pts5"] >= 15)].sort_values("up", ascending=False)
        for (pid, _), r in g.iterrows():
            if pid in skip or len(out) >= n:
                continue
            out.append((f"{r['name']}（{zh(r['abbr'])}）",
                        f"近 {int(r['n'])} 場平均 {r['pts5']:.1f} 分，比之前多 {r['up']:.1f} 分"))
            skip.add(pid)
    return out[:n]

def render_pbp(season, day, n_games, top, part, recs=None):
    """每日戰報裡的三個區塊：part="script" 只畫今日戰報稿（放在最上面）；part="flow" 畫比賽走勢＋關鍵時刻"""
    status = table_status("pbp_game_flow")
    flow = load_pbp_flow(season, day.strftime("%Y-%m-%d")) if status == "ok" else pd.DataFrame()
    ev = load_pbp_events(season, day.strftime("%Y-%m-%d")) if not flow.empty else pd.DataFrame()
    for c in ["home_pts", "away_pts", "lead_changes", "times_tied", "home_max_lead", "away_max_lead",
              "comeback_pts", "best_run_pts", "best_run_period"]:
        if c in flow:
            flow[c] = pd.to_numeric(flow[c], errors="coerce").fillna(0)

    # ---- 今日戰報稿 ----
    if part == "script":
        section("今日戰報稿", "這一天的重點，一行一件事；每一句都由資料自動算出來，可以直接複製")
        script = recap_script(day, n_games, flow, ev, top, recs)
        st.markdown('<div class="hypo" style="line-height:2">' + "<br>".join(script) + "</div>", unsafe_allow_html=True)
        with st.expander("複製文字稿"):
            st.code("\n".join(script), language=None)
        if flow.empty:
            st.caption("最精彩的一場、最大逆轉、關鍵先生需要逐回合紀錄："
                       + ("請先在 Supabase SQL Editor 執行 schema_pbp.sql，再執行 python load_pbp.py --all"
                          if status == "missing" else "尚未載入資料，請執行 python load_pbp.py --all"))
        return
    if flow.empty:
        section("比賽走勢", "")
        st.info("尚未載入資料，請執行 python load_pbp.py --all"
                + ("（第一次要先在 Supabase SQL Editor 執行 schema_pbp.sql）" if status == "missing" else ""))
        return

    # ---- 比賽走勢 ----
    slot = section("比賽走勢", "線在 0 上面＝主隊領先、下面＝客隊領先；顏色是領先那一隊的球衣色，虛線是每一節的分界")
    f = flow.copy()
    f["drama"] = [drama(r) for _, r in f.iterrows()]
    f = f.sort_values("drama", ascending=False)
    with fold("比賽走勢圖與每節比分"):
        opts = list(f["game_id"])
        lab = {r["game_id"]: f"{r['away_abbr']} @ {r['home_abbr']}" + ("　★" if i == 0 else "")
               for i, (_, r) in enumerate(f.iterrows())}
        gid = pills("選一場比賽（★ 是今天最精彩的一場）", opts, f"pbp_game_{day:%m%d}", default=opts[0],
                    format_func=lambda g: lab.get(g, g))
        r = f[f["game_id"] == gid].iloc[0]
        e = ev[ev["game_id"] == gid].sort_values(["elapsed_sec", "action_number"])
        if e.empty:
            st.info("這場的逐回合紀錄還沒載入。")
        else:
            x = [0] + list(e["elapsed_sec"] / 60)
            y = [0] + list(e["score_home"] - e["score_away"])
            hc, ac = TEAM_COLORS.get(r["home_abbr"], ACCENT), TEAM_COLORS.get(r["away_abbr"], MUTED)
            hov = ["開賽"] + [f"{period_name(p)} 剩 {int(c // 60)}:{int(c % 60):02d}<br>{n}（{t}）<br>"
                              f"{r['away_abbr']} {int(sa)} – {int(sh)} {r['home_abbr']}"
                              for p, c, n, t, sh, sa in zip(e["period"], e["clock_sec"].fillna(0), e["player_name"].fillna(""),
                                                           e["action_type"], e["score_home"], e["score_away"])]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=x, y=[max(v, 0) for v in y], mode="lines", line=dict(width=0, shape="hv"),
                                     fill="tozeroy", fillcolor=hc, opacity=0.35, name=f"{r['home_abbr']} 領先", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=x, y=[min(v, 0) for v in y], mode="lines", line=dict(width=0, shape="hv"),
                                     fill="tozeroy", fillcolor=ac, opacity=0.35, name=f"{r['away_abbr']} 領先", hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color=INK, width=1.6, shape="hv"), name="分差",
                                     text=hov, hovertemplate="%{text}<extra></extra>"))
            n_per = int(e["period"].max())
            ends = [12, 24, 36, 48] + [48 + 5 * k for k in range(1, max(0, n_per - 4) + 1)]
            for xe in ends[:-1]:
                fig.add_vline(x=xe, line=dict(color=MUTED, dash="dot", width=1))
            fig.add_hline(y=0, line=dict(color=INK_2, width=1))
            top_y = max(abs(v) for v in y) or 5
            fig.add_annotation(x=1, y=top_y, xref="paper", xanchor="right", yanchor="top", showarrow=False,
                               text=f"{r['home_abbr']} 領先 ↑", font=dict(size=11, color=hc))
            fig.add_annotation(x=1, y=-top_y, xref="paper", xanchor="right", yanchor="bottom", showarrow=False,
                               text=f"{r['away_abbr']} 領先 ↓", font=dict(size=11, color=ac))
            fig.update_xaxes(title="比賽時間（分鐘）", tickvals=[0] + ends, range=[0, ends[-1]])
            fig.update_yaxes(title=f"{r['home_abbr']} − {r['away_abbr']}（分）", range=[-top_y * 1.15, top_y * 1.15])
            fig.update_layout(showlegend=False)
            st.plotly_chart(style(fig, 340), width="stretch")
            hp, ap = r["home_periods"] or "", r["away_periods"] or ""
            if hp and ap:
                hs, as_ = hp.split(","), ap.split(",")
                per_tb = pd.DataFrame([[r["away_abbr"]] + as_ + [int(r["away_pts"])], [r["home_abbr"]] + hs + [int(r["home_pts"])]],
                                      columns=["球隊"] + [("Q" + str(i + 1)) if i < 4 else ("OT" + ("" if i == 4 else str(i - 3)))
                                                         for i in range(len(hs))] + ["總分"])
                per_tb["_key"] = per_tb["球隊"]
                nice_table(per_tb, num_cols=tuple(per_tb.columns[1:-1]), dot_col="球隊", colors=TEAM_COLORS)
        win = r["home_abbr"] if r["home_pts"] > r["away_pts"] else r["away_abbr"]
        lines = [f"{team_label(r['away_abbr'])} @ {team_label(r['home_abbr'])}：領先互換 {int(r['lead_changes'])} 次、"
                 f"平手 {int(r['times_tied'])} 次" + ("，是一場關鍵時刻比賽" if r["clutch_game"] else "") + "。",
                 f"{r['home_abbr']} 最多領先 {int(r['home_max_lead'])} 分，{r['away_abbr']} 最多領先 {int(r['away_max_lead'])} 分；"
                 + (f"{team_label(win)} 一度落後 {int(r['comeback_pts'])} 分還是贏了。" if int(r["comeback_pts"]) > 0
                    else f"{team_label(win)} 一路沒有落後。"),
                 f"最長的連續得分：{team_label(r['best_run_team'])} 在{period_name(r['best_run_period'])}打出 {int(r['best_run_pts'])} 比 0。"]
        if str(r.get("score_check")).lower() in ("false", "0"):
            lines.append("注意：這場逐回合加總的比分和官方比分不同，走勢圖可能少了幾球，參考就好。")
        insight(lines, where=slot, label="發現", to_summary=False)

    # ---- 關鍵時刻 ----
    section("關鍵時刻", "第四節或延長賽最後 5 分鐘、進球前分差 5 分以內的得分；這個時候得分最難，也最決定勝負")
    cl = clutch_leaders(ev)
    if cl.empty:
        st.caption("這一天沒有關鍵時刻比賽（最後 5 分鐘分差都超過 5 分）。")
    else:
        opp = {g_: (rr["home_abbr"], rr["away_abbr"]) for g_, rr in flow.set_index("game_id").iterrows()}
        tb = pd.DataFrame({
            "球員": cl["player_name"], "球隊": [team_label(a) for a in cl["team_abbr"]],
            "對手": [team_label(next((x for x in opp.get(g_, ("", "")) if x != a), "")) for g_, a in zip(cl["game_id"], cl["team_abbr"])],
            "關鍵得分": cl["pts"].astype(int), "三分": cl["threes"].astype(int), "_key": cl["team_abbr"],
            "_b": cl["pts"] / cl["pts"].max()}).head(8)
        c0 = tb.iloc[0]
        st.markdown(f'<div class="chart-headline">關鍵先生：{c0["球員"]}（{c0["球隊"]}）最後 5 分鐘拿下 {c0["關鍵得分"]} 分</div>',
                    unsafe_allow_html=True)
        with fold(f"關鍵時刻得分榜（前 {len(tb)} 名）"):
            nice_table(tb, num_cols=("關鍵得分", "三分"), dot_col="球隊", colors=TEAM_COLORS, bars={"關鍵得分": "_b"})


if PAGE == "每日戰報":
    st.markdown("""
<style>
.rc-grid-note { color: var(--muted); font-size: 0.82rem; margin: -2px 0 10px 0; }
.rc-card { background: #0d0a14; border-radius: 14px; padding: 14px 16px 12px; margin-bottom: 14px;
           border: 1px solid #241b38; }
.rc-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.rc-team { display: flex; flex-direction: column; align-items: center; gap: 4px; width: 64px; }
.rc-badge { border-radius: 10px; display: flex; align-items: center; justify-content: center;
            color: #ffffff; font-weight: 900; letter-spacing: 0.02em; box-shadow: inset 0 0 0 2px rgba(255,255,255,0.18); }
.rc-rec { color: #b9b1cf; font-size: 0.74rem; font-variant-numeric: tabular-nums; }
.rc-score { font-size: 2.2rem; font-weight: 900; font-variant-numeric: tabular-nums; line-height: 1; }
.rc-win { color: #ffffff; } .rc-lose { color: #6f6883; }
.rc-final { color: #a78bfa; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.16em; text-align: center; }
.rc-final small { display: block; color: #6f6883; letter-spacing: 0.02em; font-weight: 500; margin-top: 2px; }
.rc-star { border-top: 1px solid #241b38; margin-top: 12px; padding-top: 9px; color: #d9d0f5; font-size: 0.84rem; }
.rc-star .nm { color: #ffffff; font-weight: 700; margin-right: 6px; }
.rc-star b { color: #ffffff; font-size: 1rem; }
.rc-hero { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-bottom: 8px; }
.rc-p { background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; }
.rc-p .top { display: flex; align-items: center; gap: 10px; }
.rc-p .nm { font-weight: 900; color: var(--ink); font-size: 1.02rem; line-height: 1.2; }
.rc-p .sub { color: var(--muted); font-size: 0.78rem; }
.rc-p .line { margin: 10px 0 8px 0; color: var(--ink-2); font-size: 0.9rem; }
.rc-p .line b { color: var(--ink); font-size: 1.25rem; font-weight: 900; }
.rc-tag { display: inline-block; font-size: 0.74rem; font-weight: 700; color: #4c1d95; background: var(--brand-soft);
          border: 1px solid #ddd0fb; border-radius: 999px; padding: 2px 9px; margin: 0 6px 6px 0; }
.rc-c { background: var(--surface); border: 1px solid var(--line); border-left: 4px solid #c8102e;
        border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; }
.rc-prob { display: flex; height: 6px; border-radius: 3px; overflow: hidden; margin: 12px 0 4px 0; gap: 2px; }
.rc-probtxt { display: flex; justify-content: space-between; color: #b9b1cf; font-size: 0.76rem; font-variant-numeric: tabular-nums; }
.rc-probtxt span:nth-child(2) { color: #a78bfa; font-weight: 700; }
.rc-why { color: #8d86a3; font-size: 0.74rem; margin: 6px 0 2px 0; line-height: 1.5; }
.rc-pp { display: flex; align-items: baseline; gap: 6px; color: #d9d0f5; font-size: 0.8rem; padding: 4px 0;
         border-top: 1px solid #241b38; flex-wrap: wrap; }
.rc-pp:first-of-type { margin-top: 6px; }
.rc-pp .ab { color: #fff; font-size: 0.64rem; font-weight: 900; border-radius: 4px; padding: 1px 5px; }
.rc-pp .nm { color: #ffffff; font-weight: 700; }
.rc-pp .v { margin-left: auto; } .rc-pp .v b { color: #ffffff; font-size: 0.95rem; } .rc-pp small { color: #8d86a3; }
.rc-c .top { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.rc-c .nm { font-weight: 900; color: var(--ink); }
.rc-c .rec { color: var(--muted); font-size: 0.8rem; }
.rc-c ul { margin: 0 0 0 4px; padding-left: 18px; } .rc-c li { color: var(--ink-2); font-size: 0.88rem; margin: 2px 0; }
</style>
""", unsafe_allow_html=True)

    tg = load_recap_teams()
    if tg.empty:
        st.info("尚未載入資料。請先在 Supabase 執行 schema_recap.sql，再在電腦上執行：python load_recap.py")
    else:
        season = tg["season"].iloc[0]
        seg("頁面區塊", ["全部展開", "全部收起"], "rc_open")
        st.caption("每個大區塊都可以點標題收起來；收起來時，區塊上方的一句話結論還是看得到。")
        render_predictions(tg, season)
        st.divider()
        render_pred_review(tg, season)
        st.divider()
        section("比賽結果", "選一個比賽日，看比分、值得關注的球員、球隊隱憂與戰績榜")
        # 整季每一個比賽日都列出來（下拉選單），最新的在最上面；選項裡直接寫那天打幾場
        dates = sorted(tg["game_date"].unique(), reverse=True)
        n_games = tg.groupby("game_date")["game_id"].nunique()
        pick = st.selectbox(f"比賽日（美國時間，本季共 {len(dates)} 天）", dates, index=0, key="rc_day_all",
                            format_func=lambda d: f"{pd.Timestamp(d):%m/%d}（週{'一二三四五六日'[pd.Timestamp(d).weekday()]}）"
                                                  f"　{int(n_games.get(d, 0))} 場" + ("　最新" if d == dates[0] else ""))
        day = pd.Timestamp(pick)
        since = (day - pd.Timedelta(days=21)).strftime("%Y-%m-%d")
        pl = load_recap_players(season, since)
        sa = load_recap_season(season)
        today = tg[tg["game_date"] == day]
        day_pl = pl[pl["game_date"] == day] if not pl.empty else pl

        # ---- 三行重點：先讀結論 ----
        games = today.groupby("game_id")
        margins = games["plus_minus"].max()
        top = None
        if not day_pl.empty:
            dp = day_pl.copy()
            dp["gs"] = [game_score(r) for r in dp.itertuples()]
            top = dp.sort_values("gs").iloc[-1]
        lines = [f"<b>{day:%m/%d}</b> 共 <b>{games.ngroups}</b> 場比賽"
                 + (f"；分差最大的一場贏 <b>{int(margins.max())}</b> 分，最膠著的一場只差 <b>{int(margins.min())}</b> 分。"
                    if len(margins) else "。")]
        if top is not None:
            lines.append(f"今日最佳：<b>{top.player_name}</b>（{team_label(top.abbreviation)}）"
                         f" {int(top.pts)} 分 {int(top.reb)} 籃板 {int(top.ast)} 助攻。")
        insight(lines)
        recs = recommend_players(day_pl, pl, sa, day, top)
        render_pbp(season, day, games.ngroups, top, "script", recs)  # 今日戰報稿（逐回合紀錄）

        # ---- 1. 比分卡：一場一張，像 NBA 官方圖卡 ----
        section("比分", "左邊客隊、右邊主隊；下方是這場表現最好的球員（綜合得分、籃板、助攻、效率）")
        cards = []
        for gid, g in games:
            if len(g) < 2:
                continue
            away = g[~g["is_home"].astype(bool)].iloc[0] if (~g["is_home"].astype(bool)).any() else g.iloc[0]
            home = g[g["is_home"].astype(bool)].iloc[0] if g["is_home"].astype(bool).any() else g.iloc[1]
            star_html = ""
            if not day_pl.empty:
                gp_ = day_pl[day_pl["game_id"] == gid]
                if not gp_.empty:
                    s = max(gp_.itertuples(), key=game_score)
                    star_html = (f'<div class="rc-star"><span class="nm">{s.player_name}</span>'
                                 f'<span style="color:#8d86a3">{s.abbreviation}</span>　{stat_line(s)}</div>')
            ot = int(round((float(home["min"] or 240) - 240) / 25)) if pd.notna(home.get("min")) else 0
            tag = RECAP_TYPES.get(home["season_type"], "")
            cards.append(f'''<div class="rc-card"><div class="rc-row">
  <div class="rc-team">{badge(away["abbreviation"])}<div class="rc-rec">{record_through(tg, away["abbreviation"], day)}</div></div>
  <div class="rc-score {'rc-win' if away['wl'] == 'W' else 'rc-lose'}">{int(away["pts"])}</div>
  <div class="rc-final">FINAL{f"／OT{ot if ot > 1 else ''}" if ot > 0 else ""}<small>{tag}</small></div>
  <div class="rc-score {'rc-win' if home['wl'] == 'W' else 'rc-lose'}">{int(home["pts"])}</div>
  <div class="rc-team">{badge(home["abbreviation"])}<div class="rc-rec">{record_through(tg, home["abbreviation"], day)}</div></div>
</div>{star_html}</div>''')
        with fold(f"{len(cards)} 場比分卡"):
            cols = st.columns(3, gap="medium")
            for i, c in enumerate(cards):
                cols[i % 3].markdown(c, unsafe_allow_html=True)

        render_pbp(season, day, games.ngroups, top, "flow")        # 比賽走勢＋關鍵時刻（逐回合紀錄）

        # ---- 2. 值得關注的球員 ----
        section("值得關注的球員", "每位都寫出被選上的原因：爆發、大三元、三分雨、高效率、比自己平常多很多…")
        so = standouts(day_pl, sa) if not day_pl.empty else []
        if not so:
            st.caption("這一天沒有符合條件的突出表現。")
        else:
            html = []
            for r in so[:8]:
                base = f"本季平常 {r['base']:.1f} 分" if r["base"] is not None else "本季前幾場"
                html.append(f'''<div class="rc-p"><div class="top">{badge(r["abbreviation"], 38)}
<div><div class="nm">{r["player_name"]}</div><div class="sub">{team_label(r["abbreviation"])}・{r["matchup"]}・{"勝" if r["wl"] == "W" else "敗"}</div></div></div>
<div class="line">{stat_line(pd.Series(r))}　<span style="color:var(--muted);font-size:0.78rem">{base}</span></div>
<div>{"".join(f'<span class="rc-tag">{t}</span>' for t in r["tags"])}</div></div>''')
            with fold(f"{len(html)} 位值得關注的球員"):
                st.markdown(f'<div class="rc-hero">{"".join(html)}</div>', unsafe_allow_html=True)

        # ---- 3. 球隊隱憂 ----
        section("球隊隱憂", "比較每隊「最近 5 場」和「本季平均」：防守、三分、失誤、淨勝分變差，或連敗、主力未出賽、得分手低迷")
        cc = team_concerns(tg, pl, sa, day)
        only_today = seg("顯示", ["今天有比賽的球隊", "全聯盟"], "rc_cc")
        if only_today == "今天有比賽的球隊":
            cc = [c for c in cc if c["played_today"]]
        scope = tg[(tg["game_date"] <= day) & (tg["season_type"] == "Regular Season")]
        if only_today == "今天有比賽的球隊":
            scope = scope[scope["abbreviation"].isin(set(today["abbreviation"]))]
        all_abbr = sorted(set(scope["abbreviation"]))
        flagged = {c["abbr"] for c in cc}
        calm = [a_ for a_ in all_abbr if a_ not in flagged]
        st.caption(f"{len(all_abbr)} 隊中有 {len(cc)} 隊出現隱憂，依嚴重程度排序。"
                   "開季前 6 場只看連敗、主力未出賽、得分手低迷；打滿 6 場後才加上「近 5 場 vs 本季平均」的比較。")

        def concern_cards(items):
            cols = st.columns(2, gap="medium")
            for i, c in enumerate(items):
                cols[i % 2].markdown(
                    f'<div class="rc-c" style="border-left-color:{TEAM_COLORS.get(c["abbr"], "#c8102e")}">'
                    f'<div class="top">{badge(c["abbr"], 32)}<span class="nm">{team_label(c["abbr"])}</span>'
                    f'<span class="rec">{c["record"]}</span></div>'
                    f'<ul>{"".join(f"<li>{t}</li>" for t in c["items"])}</ul></div>', unsafe_allow_html=True)

        if not cc:
            st.caption("目前沒有明顯的隱憂。")
        else:
            with fold(f"{len(cc)} 隊的隱憂"):           # 框裡面不能再放框，所以「其餘幾隊」改用開關
                concern_cards(cc[:10])
                if len(cc) > 10 and st.toggle(f"顯示其餘 {len(cc) - 10} 隊", key="rc_cc_more"):
                    concern_cards(cc[10:])
        if calm:
            st.caption("目前沒有隱憂：" + "、".join(team_label(a_) for a_ in calm))

        # ---- 4. 戰績榜 ----
        section("戰績榜", f"{season} 例行賽，到 {day:%m/%d} 為止；勝差以各區第一名為準")
        with fold("東區、西區戰績榜"):
            left, right = st.columns(2, gap="large")
            for col, conf in [(left, "東區"), (right, "西區")]:
                with col:
                    st.markdown(f"**{conf}**")
                    tb = standings(tg, day, conf)
                    if tb.empty:
                        st.caption("還沒有比賽。")
                    else:
                        nice_table(tb, num_cols=("#", "勝", "敗", "勝率", "勝差", "場均淨勝"),
                                   signed_cols=("場均淨勝",), dot_col="球隊", colors=TEAM_COLORS)

        with st.expander("資料來源與方法"):
            st.markdown("""
- **資料**：NBA 官方數據 LeagueGameLog（全聯盟每場比賽的球隊與球員數據），每天由電腦上的 `daily_update.py` 自動抓進 `recap_team_games`、`recap_player_games`。日期是**美國比賽日**（台灣時間通常是隔天早上）。
- **每場最佳球員**：用 Game Score（得分＋命中＋籃板＋助攻＋抄截＋阻攻，扣掉投失、失誤、犯規）挑出綜合表現最好的人。
- **值得關注**：40 分以上、30 分以上、大三元、單場 7 記三分以上、真實命中率 70% 以上（至少 12 次出手）、比自己本季平常多 12 分以上（平常不到 12 分的標「超常發揮」：角色球員今天跳出來）、抄截＋阻攻 6 次以上。
- **球隊隱憂**：3 連敗以上；打滿 6 場後，比較最近 5 場和本季平均：失分多 6 分以上、三分命中率低 4 個百分點以上、失誤多 2.5 次以上、淨勝分少 8 分以上；本季上場時間最多的球員上一場沒有出賽；本季得分最多的球員近 3 場得分不到平常的 7 成。
- **今日戰報稿、比賽走勢、關鍵時刻**：NBA 官方逐回合紀錄 PlayByPlayV3，由 `load_pbp.py` 每天補最近 3 天的比賽，只存「得分的那一刻」進 `pbp_events`，並替每場算好走勢摘要存進 `pbp_game_flow`（領先互換、平手、最大領先、最大逆轉、最長連續得分）。比分是從 0 開始自己累加；和官方比分不同的場次會標示。關鍵時刻＝第四節或延長賽最後 5 分鐘、進球前分差 5 分以內。「最精彩的一場」用領先互換、平手、關鍵時刻、逆轉幅度加總，扣掉最終分差。
- **沒有的資料**：官方傷兵名單與原因、NBA 盃分組戰績（沒有分組資料），所以「未出賽」只說明沒有上場，不代表一定受傷。
""")


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
    hypothesis("奪冠那一季的出手位置，和聯盟平均、和自己其他球季有什麼不同？",
               "冠軍會把出手集中在「禁區籃下＋三分」這兩個每次出手得分最高的地方，少投中距離。")
    status = table_status("shots")
    if status != "ok":
        st.info("尚未載入資料，請執行 python load_extra.py --only shots"
                + ("（資料表還不存在：請先到 Supabase SQL Editor 執行 schema_extra.sql）" if status == "missing" else ""))
    else:
        shot_seasons = [s for s in ALL_SEASONS if s >= SHOT_START][::-1]
        # 比賽類型是整頁條件（第 1、2、3 節都跟著變；1031-1）
        sh_type_zh = seg("比賽類型（整頁）", ["例行賽", "季後賽"], "sh_type")
        sh_type = TYPE_OPTIONS[sh_type_zh]
        zl_page = load_zone_league()

        # ===== 1 每一位冠軍 vs 同季聯盟（先回答假設，不用選球隊；1031-1）=====
        CH_GROUPS = {"中距離": ["中距離"], "禁區籃下": ["禁區籃下"], "三分（底角＋弧頂）": ["底角三分", "弧頂三分"]}

        def champ_zone_rows():
            """每一個冠軍球季：五大區出手佔比（冠軍）與同季聯盟。先讀 shot_zone_team 檢視表，沒有就改讀逐筆出手（比較慢）"""
            out = []
            for _, c in champs[(champs["season"] >= SHOT_START)].sort_values("season").iterrows():
                if c["abbreviation"] not in ALL_TEAMS:
                    continue
                tid = int(c["team_id"])
                zt_ = load_zone_team(tid)
                if zt_ is not None and not zt_.empty:
                    z_ = zt_[(zt_["season"] == c["season"]) & (zt_["season_type"] == sh_type)]
                else:
                    s_ = load_shots(tid, c["season"], sh_type)
                    z_ = shots_to_zone_rows(s_) if not s_.empty else pd.DataFrame()
                lz = (zl_page[(zl_page["season"] == c["season"]) & (zl_page["season_type"] == sh_type)]
                      if not zl_page.empty else pd.DataFrame())
                if z_.empty or lz.empty:
                    continue
                za_, zb_ = zone_table(z_), zone_table(lz)
                if za_.empty or zb_.empty:
                    continue
                ga_, gb_ = group_table(za_), group_table(zb_)
                row = {"season": c["season"], "abbr": c["abbreviation"], "fga": float(za_["fga"].sum())}
                for g_ in GROUP_ORDER:
                    row[f"c_{g_}"], row[f"l_{g_}"] = ga_.loc[g_, "share"], gb_.loc[g_, "share"]
                for k_, gs in CH_GROUPS.items():
                    row[f"c_{k_}"] = sum(ga_.loc[g_, "share"] for g_ in gs)
                    row[f"l_{k_}"] = sum(gb_.loc[g_, "share"] for g_ in gs)
                out.append(row)
            return pd.DataFrame(out)

        slot_c = section(f"1　每一位冠軍 vs 同季聯盟（{sh_type_zh}）",
                         "一列一位冠軍：灰點＝同季聯盟平均、彩色點＝冠軍，點旁數字＝冠軍比聯盟多或少幾個百分點；"
                         "可以切換看中距離、禁區籃下、三分")
        CZ = champ_zone_rows()
        if CZ.empty:
            st.info("還沒有冠軍球季的投籃資料（或聯盟各區資料 shot_zone_league 還沒載入），"
                    "請執行 python load_extra.py --only shots")
        else:
            cz_pick = seg("看哪一區", list(CH_GROUPS), "sh_c_zone")
            labels = [f"{s} {ALL_ZH.get(a, a)}" for s, a in zip(CZ["season"], CZ["abbr"])]
            cv, lv = CZ[f"c_{cz_pick}"], CZ[f"l_{cz_pick}"]
            dv = (cv - lv) * 100
            fig = go.Figure()
            for lab, c_, l_ in zip(labels, cv, lv):
                fig.add_trace(go.Scatter(x=[l_, c_], y=[lab, lab], mode="lines", showlegend=False, hoverinfo="skip",
                                         line=dict(color="#d9d3e6", width=3)))
            fig.add_trace(go.Scatter(x=lv, y=labels, mode="markers", name="同季聯盟平均",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>聯盟 %{x:.1%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=cv, y=labels, mode="markers+text", name="冠軍",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in CZ["abbr"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     text=[f"{v:+.1f}" for v in dv],
                                     textposition=["middle right" if v >= 0 else "middle left" for v in dv],
                                     textfont=dict(size=11, color=INK_2),
                                     hovertemplate="%{y}<br>冠軍 %{x:.1%}（比聯盟 %{text} 個百分點）<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            lo_, hi_ = min(cv.min(), lv.min()), max(cv.max(), lv.max())
            pad = max(0.01, (hi_ - lo_) * 0.25)
            fig.update_xaxes(title=f"{cz_pick}出手佔比（每 100 次出手有幾次）", tickformat=".0%",
                             range=[max(0, lo_ - pad), hi_ + pad], showgrid=True, gridcolor=GRID)
            st.plotly_chart(style(fig, 90 + 44 * len(CZ)), width="stretch", config={"displayModeBar": False})

            # 發現：一次檢查假設的三個部分（少投中距離、籃下多、三分多）
            n_ = len(CZ)
            parts = []
            for k_, want_less, txt in [("中距離", True, "中距離比聯盟少"), ("禁區籃下", False, "禁區籃下比聯盟多"),
                                       ("三分（底角＋弧頂）", False, "三分比聯盟多")]:
                d_ = CZ[f"c_{k_}"] - CZ[f"l_{k_}"]
                k = int((d_ < 0).sum() if want_less else (d_ > 0).sum())
                parts.append((txt, k))
            ok_parts = sum(k > n_ / 2 for _, k in parts)
            verdict = "成立" if ok_parts == 3 else ("部分成立" if ok_parts else "不成立")
            big = CZ.assign(d=dv).sort_values("d")
            lines = [f"<b>{cz_pick}：</b>{n_} 位冠軍裡，有 {int((dv < 0).sum())} 位比同季聯盟少、{int((dv > 0).sum())} 位比較多"
                     f"（平均差 {dv.mean():+.1f} 個百分點）。",
                     f"差最多的是 {big.iloc[0]['season']} {ALL_ZH.get(big.iloc[0]['abbr'], '')}（{big.iloc[0]['d']:+.1f}）"
                     f"與 {big.iloc[-1]['season']} {ALL_ZH.get(big.iloc[-1]['abbr'], '')}（{big.iloc[-1]['d']:+.1f}）。",
                     "讀法：彩色點在灰點左邊＝冠軍在這一區投得比聯盟少，右邊＝比較多；線越長差越多。"
                     "切換三個區域，就能一次檢查假設的三個部分。"]
            chk = f"{verdict}：" + "；".join(f"{t} {k} / {n_} 位" for t, k in parts) + "（超過一半才算成立）。"
            insight(lines, where=slot_c, check=chk)
            with st.expander("看每一位冠軍五大區的明細"):
                rows = []
                for _, r in CZ.iterrows():
                    row = {"球季": r["season"], "冠軍": ALL_ZH.get(r["abbr"], r["abbr"]), "_key": r["abbr"]}
                    for g_ in GROUP_ORDER:
                        row[g_] = f"{r[f'c_{g_}']:.0%}（{(r[f'c_{g_}'] - r[f'l_{g_}']) * 100:+.1f}）"
                    rows.append(row)
                nice_table(pd.DataFrame(rows), num_cols=tuple(GROUP_ORDER), dot_col="冠軍", colors=TEAM_COLORS)
                st.caption("每一格：冠軍這一區的出手佔比（括號＝比同季聯盟多或少幾個百分點）。")
        # 名詞小辭典：五大區在哪裡（1031-3；1031-1 移到第一張圖下面）
        with st.expander("五大區是哪裡？（名詞小辭典）"):
            g1, g2 = st.columns([2, 3], gap="large")
            with g1:
                zf = go.Figure()
                for x_, y_, t_ in [(0, 12, "禁區籃下"), (0, 95, "油漆區"), (-150, 110, "中距離"),
                                   (150, 110, "中距離"), (-236, 40, "底角<br>三分"), (236, 40, "底角<br>三分"),
                                   (0, 280, "弧頂三分")]:
                    zf.add_annotation(x=x_, y=y_, text=t_, showarrow=False,
                                      font=dict(size=12, color=INK), bgcolor="rgba(255,255,255,0.85)")
                zf.add_shape(type="rect", x0=-80, y0=-47.5, x1=80, y1=142.5, line=dict(width=0),
                             fillcolor="rgba(124,58,237,0.10)", layer="below")
                zf.add_shape(type="circle", x0=-40, y0=-40, x1=40, y1=40, line=dict(width=0),
                             fillcolor="rgba(124,58,237,0.22)", layer="below")
                zf.update_layout(shapes=court_shapes() + list(zf.layout.shapes or []))
                zf.update_xaxes(range=[-255, 255], visible=False, fixedrange=True, constrain="domain")
                zf.update_yaxes(range=[-55, 310], visible=False, fixedrange=True, constrain="domain",
                                scaleanchor="x", scaleratio=1)
                zf = style(zf, 300)
                zf.update_layout(showlegend=False)
                zf.add_trace(go.Scatter(x=[0], y=[0], mode="markers", hoverinfo="skip",
                                        marker=dict(size=1, color="rgba(0,0,0,0)")))
                st.plotly_chart(zf, width="stretch", config={"displayModeBar": False, "staticPlot": True})
            with g2:
                term_table(GROUP_ORDER + ["每次出手得分"],
                           first_note="油漆區和禁區籃下都在籃框附近：<b>禁區籃下</b>只算最裡面的小半圓，"
                                      "<b>油漆區</b>是長方形裡剩下的部分。")
        st.divider()

        # ===== 2 單一球隊深入看（球隊、球季、球員、比較對象只放在這一節）=====
        section("2　單一球隊深入看", "選一支球隊和一個球季；底下 2-1 球場圖、2-2 五大區對照")
        # 球隊按鈕放在獨立一整排，8 隊才排得下
        sh_team = pills("球隊（投籃位置資料只有八支冠軍隊）", ALL_TEAMS, "sh_team", default=ALL_TEAMS[0],
                        format_func=team_label)
        sh_tid = int(team_raw[team_raw["abbreviation"] == sh_team]["team_id"].iloc[0])
        champ_s = [s for s in shot_seasons if (s, sh_team) in CHAMP_SET]
        c2, c4, c5 = st.columns([3, 3, 4])
        with c2:
            sh_season = st.selectbox(
                "球季", shot_seasons, key=f"sh_season_{sh_team}",
                index=shot_seasons.index(champ_s[0]) if champ_s else 0,
                format_func=lambda s: s + ("　★ 奪冠" if (s, sh_team) in CHAMP_SET else ""))
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
        color = TEAM_COLORS.get(sh_team, ACCENT)
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

            # ---- 球場圖 ----
            def court_top(*ys, pad=30):
                """球場往上畫到哪裡：最遠的出手再多留一點邊就好，沒人投籃的地方不要留白"""
                vals = [pd.to_numeric(pd.Series(y if hasattr(y, "__len__") else [y]), errors="coerce").dropna()
                        for y in ys if y is not None]   # 可以傳一整欄，也可以傳單一個數字
                vals = [v for v in vals if len(v)]
                if not vals:
                    return 300
                return float(min(330, max(250, max(v.max() for v in vals) + pad)))

            def court_axes(fig, top=330):
                """把圖變成半場球場：畫線、隱藏座標軸、長寬等比例；高度跟著 top 縮，上方不留大片空白"""
                fig.update_layout(shapes=court_shapes())
                fig.update_xaxes(range=[-255, 255], visible=False, fixedrange=True, constrain="domain")
                fig.update_yaxes(range=[-55, top], visible=False, fixedrange=True, constrain="domain",
                                 scaleanchor="x", scaleratio=1)
                fig = style(fig, int(16 + 560 * (top + 55) / 510))   # 依球場的長寬比算高度（以半版寬約 560 像素估）
                fig.update_layout(legend=dict(y=-0.02))
                return fig

            def points_fig(df, top=None):
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
                # 超遠的零星出手（例如半場球）不納入，取 99% 的出手都看得到的高度
                return court_axes(fig, top or court_top(df["loc_y"].quantile(0.99) if len(df) else None, pad=15))

            def shot_summary(df):
                """圖上方的一行摘要：出手數、命中率、三分出手比例"""
                n = len(df)
                fg = df["made"].astype(bool).mean() if n else float("nan")
                three = df["zone_basic"].isin(["Left Corner 3", "Right Corner 3", "Above the Break 3"]).mean()
                return f"出手 {n:,} 次｜命中率 {fg:.1%}｜三分出手佔 {three:.0%}"

            # 「另一季」＋「每一次出手」：兩季的球場圖左右並排，一眼比較
            shot_slot = st.container()   # 結論放在圖的上面（先讀結論，再看圖）
            a_short = sh_season + ("★" if (sh_season, sh_team) in CHAMP_SET else "")
            b_short = "聯盟" if vs == "聯盟平均" else (sh_season_b + ("★" if (sh_season_b, sh_team) in CHAMP_SET else ""))

            def zone_fig(za_, zb_, colored=True, colorbar=True, ref_label=None, top=None):
                """分區命中率球場圖：圈的大小＝出手佔比、圈內數字＝命中率；colored=True 時顏色＝和對照組的命中率差"""
                zm = za_.copy()
                if colored and zb_ is not None and not zb_.empty:
                    zm = zm.merge(zb_[["zone_basic", "zone_area", "fg_pct"]], on=["zone_basic", "zone_area"],
                                  how="left", suffixes=("", "_b"))
                else:
                    zm["fg_pct_b"] = float("nan")
                zm["diff"] = pd.to_numeric(zm["fg_pct"] - zm["fg_pct_b"], errors="coerce") * 100
                size = 16 + 46 * (zm["share"] / 0.30).clip(upper=1) ** 0.5   # 兩張圖用同一個比例尺
                marker = dict(size=size, line=dict(width=1, color="rgba(26,20,38,0.25)"))
                if colored:
                    marker.update(color=zm["diff"].fillna(0), cmin=-8, cmax=8,
                                  colorscale=[[0, "#3d74c9"], [0.5, "#ece9f2"], [1, "#7c3aed"]],
                                  showscale=colorbar,
                                  colorbar=dict(title=dict(text="命中率差<br>（百分點）", font=dict(size=11, color=INK_2)),
                                                thickness=10, outlinewidth=0, len=0.6, tickfont=dict(color=INK_2)))
                else:
                    marker.update(color="#e4e0ec")
                f = go.Figure(go.Scatter(
                    x=zm["x"], y=zm["y"], mode="markers+text",
                    text=[f"{v:.0%}" for v in zm["fg_pct"]], textfont=dict(size=11, color=INK), marker=marker,
                    customdata=zm[["name", "fga", "share", "fg_pct", "fg_pct_b", "diff", "pps"]].values,
                    hovertemplate="<b>%{customdata[0]}</b><br>出手 %{customdata[1]:,} 次（佔 %{customdata[2]:.1%}）"
                                  "<br>命中率 %{customdata[3]:.1%}"
                                  + ("｜" + (ref_label or b_label) + " %{customdata[4]:.1%}<br>差距 %{customdata[5]:+.1f} 百分點"
                                     if colored else "")
                                  + "<br>每次出手 %{customdata[6]:.2f} 分<extra></extra>", showlegend=False))
                return court_axes(f, top or court_top(zm["y"]))

            # 樣本太少時先提醒：剛開打的球季、出手很少的球員，命中率會忽高忽低
            few_a = len(shots_a) < 300
            few_b = vs == "另一季" and not zb.empty and len(shots_b) < 300
            if few_a or few_b:
                st.warning("樣本很少，先不要下結論："
                           + "、".join(x for x in [f"{a_label} 只有 {len(shots_a):,} 次出手" if few_a else "",
                                                   f"{b_label} 只有 {len(shots_b):,} 次出手" if few_b else ""] if x)
                           + "（至少幾百次出手，命中率才比較穩定）。")

            # 和「另一季」比較時：兩張球場圖左右並排，一眼看出差在哪
            two_up = vs == "另一季" and not zb.empty
            if two_up:
                section(f"2-1　球場圖：{a_label} vs {b_label}", "左右兩張用同一套規則，可以直接對照", level=2)
                ca, cb = st.columns(2, gap="large")
                if view == "每一次出手":
                    top2 = court_top(shots_a["loc_y"].quantile(0.99), shots_b["loc_y"].quantile(0.99), pad=15)
                    for c_, df_, lab in [(ca, shots_a, a_label), (cb, shots_b, b_label)]:
                        with c_:
                            section(f"{lab} 出手位置", shot_summary(df_))
                            st.plotly_chart(points_fig(df_, top=top2), width="stretch")
                    st.caption("兩張圖用同一套顏色和比例：彩色＝投進、灰色 × ＝沒進。"
                               "比一比哪一區的點變多變少（出手選擇的改變）、哪一區彩色點變多（命中區的改變）。")
                else:
                    # 兩張圖用「完全一樣」的畫法：顏色都和「自己那一季的聯盟平均」比，
                    # 這樣左右兩張的紫、藍代表同一件事，可以直接對照
                    zl_all = load_zone_league()

                    def league_zone(season_):
                        z_ = zl_all[(zl_all["season"] == season_) & (zl_all["season_type"] == sh_type)] \
                            if not zl_all.empty else pd.DataFrame()
                        return zone_table(z_) if not z_.empty else None

                    top2 = court_top(za["y"], zb["y"])   # 兩張圖同一個高度，左右才對得齊
                    for c_, z_, df_, lab, sea_ in [(ca, za, shots_a, a_label, sh_season),
                                                   (cb, zb, shots_b, b_label, sh_season_b)]:
                        with c_:
                            ref = league_zone(sea_)
                            section(lab, shot_summary(df_))
                            st.plotly_chart(zone_fig(z_, ref, colored=ref is not None, colorbar=False,
                                                     ref_label=f"{sea_} 聯盟平均", top=top2), width="stretch")
                    st.markdown('<div class="legend-row"><span class="sw" style="background:#7c3aed"></span>比當季聯盟平均準'
                                '<span class="sw" style="background:#ece9f2;border:1px solid #d9d3e6"></span>和聯盟差不多'
                                '<span class="sw" style="background:#3d74c9"></span>比聯盟不準'
                                '<span class="lg-note">兩張圖同一套規則：圈越大＝那一區出手越多，圈內數字＝命中率</span></div>',
                                unsafe_allow_html=True)
                left, right = None, st.container()   # 下面的五大區對照改成整排寬
            else:
                left, right = st.columns([5, 4], gap="large")
                with left:
                    if view == "每一次出手":
                        fig = points_fig(shots_a)
                        sub = f"每個點是一次出手：彩色＝投進、灰色 × ＝沒進。{shot_summary(shots_a)}"
                        if vs == "另一季":
                            sub += "（比較球季沒有資料，所以只顯示一張）"
                    else:
                        fig = zone_fig(za, zb, colored=not zb.empty)
                        sub = f"圈越大＝出手越多；圈內數字是命中率；紫色＝比「{b_label}」準、藍色＝比較不準"
                    section(f"2-1　{a_label} 出手位置", sub, level=2)
                    st.plotly_chart(fig, width="stretch")

            # ---- 五大區對照 ----
            with right:
                ga = group_table(za)
                gb = group_table(zb) if not zb.empty else None
                section(f"2-2　五大區出手佔比：{a_short} vs {b_short}",
                        f"每 100 次出手有幾次在這一區；彩色長條＝{a_label}、灰色長條＝{b_label}", level=2)
                fig = go.Figure()
                if gb is not None:
                    fig.add_trace(go.Bar(y=GROUP_ORDER, x=gb["share"], orientation="h", name=b_label,
                                         marker=dict(color="#c9c3d6"), text=[fmt(v, ".0%") for v in gb["share"]],
                                         textposition="outside", cliponaxis=False, textfont=dict(color=INK_2),
                                         hovertemplate="%{y}　%{x:.1%}<extra>" + b_label + "</extra>"))
                fig.add_trace(go.Bar(y=GROUP_ORDER, x=ga["share"], orientation="h", name=a_label,
                                     marker=dict(color=color), text=[fmt(v, ".0%") for v in ga["share"]],
                                     textposition="outside", cliponaxis=False, textfont=dict(color=INK),
                                     hovertemplate="%{y}　%{x:.1%}<extra>" + a_label + "</extra>"))
                rounded(fig)
                fig.update_yaxes(autorange="reversed", showgrid=False)
                fig.update_xaxes(showticklabels=False, showgrid=False)
                fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08,
                                  legend=dict(orientation="h", y=1.08, x=0, traceorder="reversed"))
                st.plotly_chart(style(fig, 360), width="stretch")
                rows = []
                for grp in GROUP_ORDER:
                    ra = ga.loc[grp]
                    rb = gb.loc[grp] if gb is not None else None
                    dif = (ra["share"] - rb["share"]) * 100 if rb is not None else float("nan")
                    dfg = (ra["fg_pct"] - rb["fg_pct"]) * 100 if rb is not None else float("nan")
                    rows.append({"區域": grp,
                                 f"{a_short} 佔比": fmt(ra["share"], ".1%"),
                                 f"{b_short} 佔比": fmt(rb["share"], ".1%") if rb is not None else "-",
                                 "佔比差": "-" if pd.isna(dif) else f"{dif:+.1f}",
                                 f"{a_short} 命中率": fmt(ra["fg_pct"], ".1%"),
                                 f"{b_short} 命中率": fmt(rb["fg_pct"], ".1%") if rb is not None else "-",
                                 "命中率差": "-" if pd.isna(dfg) else f"{dfg:+.1f}",
                                 f"{a_short} 每次出手得分": fmt(ra["pps"], ".2f")})
                tb = pd.DataFrame(rows)
                nice_table(tb, num_cols=tuple(tb.columns[1:]), signed_cols=("佔比差", "命中率差"))
                st.caption("佔比差、命中率差的單位是「百分點」：+3.0 代表比對照多 3 個百分點。")

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
            insight(lines, where=shot_slot)

        # ===== 3 跨球季的變化（1031-2：折線、熱力圖、小球場並排合併成一節；不受第 2 節「這一季有沒有紀錄」影響）=====
        st.divider()
        slot3 = section(f"3　跨球季的變化：{sh_pname or team_label(sh_team)}（{sh_type_zh}）",
                        "和第 2 節同一支球隊（選了球員就看球員），★ 是奪冠球季；"
                        "折線＝某一區的出手佔比 vs 聯盟、熱力圖＝每季 × 每區一眼看完、小球場並排＝挑幾季放在一起比")
        cross = seg("看法", ["折線", "熱力圖", "小球場並排"], "sh_cross")
        zt = load_zone_team(sh_tid) if sh_pid is None else load_zone_player(sh_pid)
        zl = load_zone_league()
        view_file = "shot_zone_team" if sh_pid is None else "shot_zone_player"

        if cross == "折線":
            trend_grp = seg("區域", ["中距離", "三分（底角＋弧頂）", "禁區籃下"], "sh_trend")
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
                    # 發現（1031-2）：幾季比聯盟少、奪冠季差多少
                    both = pd.concat([ts_team.rename("t"), ts_lg.rename("l")], axis=1).dropna()
                    if not both.empty:
                        dd = (both["t"] - both["l"]) * 100
                        n_less = int((dd < 0).sum())
                        lines = [f"<b>{trend_grp}：</b>{who}有資料的 {len(dd)} 季裡，"
                                 f"有 {n_less} 季比同季聯盟少、{len(dd) - n_less} 季比較多"
                                 f"（平均差 {dd.mean():+.1f} 個百分點）。"]
                        cs_in = [s for s in cs if s in dd.index] if not ts_team.empty else []
                        if cs_in:
                            lines.append("奪冠季：" + "、".join(f"{s} {dd[s]:+.1f}" for s in cs_in) + " 個百分點"
                                         + (f"；其他球季平均 {dd.drop(cs_in).mean():+.1f}。" if len(dd) > len(cs_in) else "。"))
                        lines.append("讀法：彩色線在灰線下面＝這一區投得比聯盟少；★ 那幾季和旁邊的球季比，"
                                     "看奪冠是不是伴隨著出手選擇的改變。")
                        insight(lines, where=slot3)
                else:
                    st.info("檢視表已建立，但還沒有這個選擇的資料。")

        if cross != "折線":
            mv_slot = slot3
            if zt is None or zt.empty:
                st.info(f"多季對照需要彙總檢視表：請到 Supabase SQL Editor 執行 docs/sql/2026-10-28_{view_file}.sql。")
                if view_file in VIEW_ERRORS:
                    st.caption(f"錯誤訊息：{VIEW_ERRORS[view_file]}")
            else:
                if cross == "熱力圖":
                    m1, m2 = st.columns([4, 3])
                    with m1:
                        mv_metric = seg("顏色代表", ["出手佔比", "命中率", "命中率 vs 聯盟"], "mv_metric")
                    with m2:
                        mv_level = seg("區域分法", ["五大區", "細分區域"], "mv_level")
                else:
                    mv_metric, mv_level = "出手佔比", "五大區"

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

                    if cross == "熱力圖":
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
                            insight(lines, where=mv_slot)

                    if cross == "小球場並排":
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
                                small_top = min(330, max(250, max((v[1] for v in POS.values()), default=270) + 30))
                            else:
                                POS = {}
                                small_top = 300
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
                                fig.update_yaxes(range=[-55, small_top], visible=False, fixedrange=True, constrain="domain",
                                                 scaleanchor="x", scaleratio=1)   # 每張小球場比例、大小都一樣
                                star = " ★" if s in champ_cols else ""
                                c_.markdown(f'<div class="section-sub" style="margin-left:0;text-align:center">'
                                            f'<b style="color:#1a1426">{s}{star}</b>　出手 {int(f["fga"].sum()):,}</div>',
                                            unsafe_allow_html=True)
                                fig = style(fig, int(10 + 300 * (small_top + 55) / 510))
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
    hypothesis("冠軍隊的進攻是「某種戰術用得特別多」，還是「同樣的戰術打得特別有效率」？",
               "冠軍的戰術比例和聯盟差不多，真正拉開差距的是每回合得分（效率）。")
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

        # 戰術數據有全聯盟 30 隊：預設列出冠軍隊（＋已載入的球隊），想看別隊可以切到「全聯盟 30 隊」
        abbr2id = {v: k for k, v in id2abbr.items()}
        pt_abbrs = {id2abbr[t] for t in PT["team_id"].unique() if t in id2abbr}
        pt_s = sorted(PT["season"].unique())
        pc, po = split_teams(sorted(pt_abbrs), pt_s[0], pt_s[-1])
        po = sorted(po, key=lambda a_: (a_ not in EXTRA_TEAMS, a_))   # 已載入球員數據的球隊排前面
        # 比賽類型、看哪一端是整頁條件（1101-1）
        k1_, k2_ = st.columns(2)
        with k1_:
            pl_type_zh = seg("比賽類型（整頁）", ["例行賽", "季後賽"], "pl_type")
        with k2_:
            side_zh = seg("看哪一端（整頁）", ["進攻", "防守"], "pl_side")
        pl_type = TYPE_OPTIONS[pl_type_zh]
        side = "offensive" if side_zh == "進攻" else "defensive"
        is_off = side == "offensive"

        # ===== 1 八位冠軍的共同點（先回答假設，不用選球隊；1101-1）=====
        slot_pc = section(f"1　八位冠軍的共同點：每種戰術在聯盟排第幾？（{side_zh}）",
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
            how_read("橫著看一列，如果八位冠軍大多在前 10 名（深紫色），這個戰術就是「冠軍共同點」。"
                       + (f"目前中位數在前 10 名的：{'、'.join(strong)}。" if strong else
                          "目前沒有任何戰術的中位數在前 10 名：冠軍各有各的打法。")
                       + "改成「使用率」，就能檢查假設：如果使用率排名分散、效率排名集中在前面，代表冠軍贏在效率。")
            # 發現：每位冠軍的「效率排名中位數」是不是比「使用率排名中位數」前面
            cmp_rows = []
            for _, c in ch.iterrows():
                d = PT[(PT["team_id"] == c["team_id"]) & (PT["season"] == c["season"]) & (PT["season_type"] == pl_type)
                       & (PT["side"] == side) & (PT["play_type"] != "Misc")]
                if len(d):
                    cmp_rows.append((c["season"], c["abbreviation"], d["rk_ppp"].median(), d["rk_use"].median()))
            if cmp_rows:
                k_eff = sum(e < u for _, _, e, u in cmp_rows)
                n_c = len(cmp_rows)
                e_all = pd.Series([r_[2] for r_ in cmp_rows]).median()
                u_all = pd.Series([r_[3] for r_ in cmp_rows]).median()
                lines = [f"<b>效率比使用率前面：</b>{n_c} 位冠軍裡，有 {k_eff} 位的效率排名（中位數）比使用率排名前面"
                         f"（全部冠軍：效率第 {e_all:.0f} 名、使用率第 {u_all:.0f} 名）。",
                         (f"中位數在前 10 名的戰術：{'、'.join(strong)}。" if strong else
                          "沒有任何戰術的中位數在前 10 名：冠軍各有各的打法。")]
                chk = ((f"成立：{k_eff} / {n_c} 位冠軍贏在效率，不是用得特別多。" if k_eff > n_c / 2 else
                        f"不成立：只有 {k_eff} / {n_c} 位冠軍的效率排名比使用率排名前面。")
                       + "（排名都是同一季、同一種比賽、全聯盟 30 隊比。）")
                insight(lines, where=slot_pc, check=chk)
        with st.expander("這些戰術是什麼？（戰術小辭典）"):
            term_table(["使用率", "每回合得分（PPP）"] + [PLAY_ZH[p] for p in PLAY_ORDER if p != "Misc"],
                       first_note="「回合」＝拿到球到投進、失誤或被搶籃板為止的一次進攻；"
                                  "NBA 把每一次進攻依「最後怎麼出手」分到下面其中一種戰術。")
        st.divider()


        # ===== 2 單一球隊深入看（球隊、球季只放在這一節）=====
        section("2　單一球隊深入看", "選一支球隊和一個球季；底下 2-1 戰術地圖、2-2 戰術表、2-3 逐季變化")
        pl_team = team_picker_one(pc, po, "pl_team",
                                  f"奪冠球隊（{pt_s[0]}～{pt_s[-1]} 拿過冠軍）",
                                  f"其他球隊（戰術數據有全聯盟 30 隊）")
        c2, _ = st.columns([1, 2])
        pl_tid = int(abbr2id[pl_team])
        pl_seasons = sorted(PT[PT["team_id"] == pl_tid]["season"].unique())[::-1]
        if not pl_seasons:   # 這隊完全沒有戰術數據：仍列出所有球季，下面會顯示「沒有資料」
            pl_seasons = sorted(PT["season"].unique())[::-1]
        champ_pl = [s for s in pl_seasons if (s, pl_team) in CHAMP_SET]
        with c2:
            pl_season = st.selectbox(
                "球季", pl_seasons, key=f"pl_season_{pl_team}",
                index=pl_seasons.index(champ_pl[0]) if champ_pl else 0,
                format_func=lambda s: s + ("　★ 奪冠" if (s, pl_team) in CHAMP_SET else ""))
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
            who = f"{pl_season} {ALL_ZH.get(pl_team, pl_team)}{star}"

            pl_slot = st.container()   # 結論放在圖的上面（先讀結論，再看圖）
            left, right = st.columns([5, 4], gap="large")
            with left:
                section(f"2-1　{who} 戰術地圖（{side_zh}）", level=2, sub=
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
                section("2-2　每種戰術的使用率與效率",
                        "長條＝使用率；排名是每回合" + ("得分" if is_off else "失分") + "在全聯盟的名次（1 = 最好）", level=2)
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
                insight(where=pl_slot, lines=[
                    f"<b>{who}</b> {side_zh}端最常{'用' if is_off else '面對'}的三種戰術：{top3}。",
                    f"最大優勢：<b>{best['name']}</b>，每回合比聯盟{'多得' if is_off else '少失'} "
                    f"{best['d_ppp']:.2f} 分（聯盟第 {best['rk_ppp']:.0f} 名）。",
                    f"相對弱點：<b>{worst['name']}</b>，每回合比聯盟{'少得' if is_off else '多失'} "
                    f"{abs(worst['d_ppp']):.2f} 分（聯盟第 {worst['rk_ppp']:.0f} 名）。",
                    "讀法：如果圈大多落在「上方」而不是「右邊」，代表這支隊伍贏在效率，而不是打法特別不一樣。",
                ])

            # ===== 奪冠前後：某一種戰術的逐季變化 =====
            st.write("")
            section(f"2-3　{ALL_ZH.get(pl_team, pl_team)}的某一種戰術，逐季怎麼變？",
                    "紫色直條是奪冠球季；看看奪冠那季是突然變強，還是一路累積上來", level=2)
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
                        fig.add_trace(go.Scatter(x=tr_seasons, y=tr[val], name=ALL_ZH.get(pl_team, pl_team),
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

        section("3　延伸：全聯盟比較與奪冠方程式", "3-1 各隊戰術比較、3-2 奪冠方程式、3-3 檢驗方程式、3-4 單一戰術")
        cmp_seasons = pt_s[::-1]
        champ_of = {s_: a_ for s_, a_ in CHAMP_SET}
        cmp_season = st.selectbox("3-1 的球季（只影響這一張圖）", cmp_seasons,
                                  index=cmp_seasons.index(pl_season) if pl_season in cmp_seasons else 0,
                                  key="pl_cmp_season",
                                  format_func=lambda s: s + (f"　★ {ALL_ZH.get(champ_of[s], champ_of[s])}"
                                                             if s in champ_of else ""))
        section(f"3-1　{cmp_season} 各隊戰術比較（{side_zh}）",
                "每一列是一支球隊，依例行賽勝率由高到低排；框起來的那一列是當季冠軍；最下面是聯盟平均", level=2)
        k1, k2 = st.columns(2)
        with k1:
            cmp_metric = seg("比較什麼", ["使用率", "每回合" + ("得分" if is_off else "失分"), "效率排名"], "pl_cmp_metric")
        with k2:
            cmp_scope = seg("球隊範圍", ["全聯盟 30 隊", "八支冠軍隊"], "pl_cmp_scope")
        sea = PT[(PT["season"] == cmp_season) & (PT["season_type"] == pl_type) & (PT["side"] == side)
                 & (PT["play_type"] != "Misc")]
        if cmp_scope == "八支冠軍隊":
            sea = sea[sea["team_id"].isin(set(team_raw["team_id"]))]
        if sea.empty:
            st.caption("這個條件沒有資料。")
        else:
            col_key = {"使用率": "poss_pct", "效率排名": "rk_ppp"}.get(cmp_metric, "ppp")
            hm = sea.pivot_table(index="team_id", columns="play_type", values=col_key, aggfunc="first")
            hm = hm[[p for p in PLAY_ORDER if p in hm.columns]]
            wp = win[win["season"] == cmp_season].set_index("team_id")["win_pct"] if not win.empty else pd.Series(dtype=float)
            order = sorted(hm.index, key=lambda t: -(wp.get(t, float("nan")) if pd.notna(wp.get(t, float("nan"))) else -1))
            hm = hm.reindex(order)
            # 最下面加一列聯盟平均（全聯盟 30 隊，不受「球隊範圍」影響）
            lg = PT_LG[(PT_LG["season"] == cmp_season) & (PT_LG["season_type"] == pl_type) & (PT_LG["side"] == side)]
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
                star = " ★" if (cmp_season, t) in champ_ids else ""
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
                if (cmp_season, t) in champ_ids:
                    fig.add_shape(type="rect", xref="x", yref="y", x0=-0.5, x1=len(xs) - 0.5, y0=i - 0.5, y1=i + 0.5,
                                  line=dict(color=ACCENT, width=2))
            fig.update_yaxes(autorange="reversed", showgrid=False)
            fig.update_xaxes(showgrid=False, side="top")
            st.plotly_chart(style(fig, 90 + 30 * len(hm)), width="stretch")
            how_read("上面幾列是勝率最高的球隊。直著看一欄，如果深色集中在上半部、淺色在下半部，"
                       "代表這個戰術「打得好的隊伍比較會贏」。30 隊時格子裡不寫數字，把滑鼠移到格子上就能看到。")

        # ===== 奪冠方程式 =====
        st.write("")
        st.divider()
        eq_slot = section("3-2　奪冠方程式：哪些戰術和贏球最有關？", level=2, sub=
                "用全聯盟 30 隊、每一季的例行賽：每種戰術的「效率」和「使用率」，各自和球隊勝率的相關係數。"
                "長條越長（越往右），代表這件事做得好的隊伍越會贏")
        with eq_slot:
            hypo_only("和勝率最有關的是戰術的「效率」，不是「使用率」；用效率算出的方程式分數，冠軍會在當季前 3 名。")
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
                insight(where=eq_slot, lines=[
                    f"{side_zh}端和勝率最有關的三種戰術效率：<b>{'、'.join(PLAY_ZH.get(p, p) for p in top['play_type'])}</b>"
                    f"（相關係數 {'、'.join(format(v, '+.2f') for v in top['r_eff'])}）。",
                    f"{len(cs)} 種戰術中，有 {use_stronger} 種是「用得多」比「打得好」更和勝率有關。"
                    + ("這支持今天的假設：贏球靠的是效率，不是打法。" if use_stronger <= len(cs) / 3
                       else "這和今天的假設不太一樣：有不少戰術是「用多用少」本身就和勝率有關。"),
                    f"資料：{n_seasons} 季 × 30 隊的例行賽。相關不等於因果，例如好球隊快攻多，"
                    "也可能是因為防守好、搶到球就快攻。",
                ])

                # ---- 方程式分數：用上面的相關係數當權重，替每支球隊打分數，看冠軍會不會排在前面 ----
                chk_slot = section("3-3　檢驗方程式：用這個公式幫每隊打分數，冠軍會排第幾？", level=2, sub=
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
                    use_win = int((cs["r_use"].abs() > cs["r_eff"]).sum())
                    eq_check = ("前半成立：" if use_win <= len(cs) / 3 else "前半不成立：") + \
                        f"{len(cs)} 種戰術中 {use_win} 種是使用率比效率更和勝率有關；" + \
                        ("後半成立：" if top3 >= len(chs) / 2 else "後半不成立：") + \
                        f"{len(chs)} 位冠軍有 {top3} 位方程式排當季前 3。"
                    insight(where=chk_slot, check=eq_check, lines=[
                        f"{len(chs)} 位冠軍裡，有 <b>{top3}</b> 位的方程式分數在當季前 3 名"
                        f"（對照：例行賽勝率前 3 名的有 {top3_win} 位）。",
                        "<b>注意：這是描述，不是預測。</b>權重和分數用同一批資料算，所以冠軍排得前面是「事後看得出來」，"
                        "不代表能在季前猜中冠軍。",
                        f"全部球隊的方程式分數和勝率相關 {r_all:+.2f}。",
                        "讀法：方程式排名越前面，代表「把最重要的戰術打好」這件事，冠軍做得比別人好。"
                        "如果某位冠軍方程式排名很後面，他就是靠別的東西奪冠（季後賽表現、健康、球星），值得單獨研究。",
                        "讀法：要真正驗證，可以只用前幾季算權重，再看後幾季的冠軍排第幾。",
                    ])

                # ---- 單一戰術：效率 vs 勝率散點圖 ----
                section("3-4　單一戰術：效率越好，勝率越高嗎？",
                        "每個點是一支球隊的一個球季（例行賽）；灰色是其他球隊，彩色是冠軍", level=2)
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


# ---------- 上場陣容：冠軍的核心五人是誰？ ----------
LU_MIN = {"Regular Season": 50, "Playoffs": 15}   # 同時在場少於這個分鐘數的陣容，樣本太小不列入比較


@st.cache_data(ttl=3600, show_spinner="讀取陣容數據中…")
def load_lineups():
    """八支冠軍隊每季的 5 人陣容。只讀「同時在場至少 10 分鐘」的組合（太短的組合是雜訊，也讓讀取快很多）"""
    client = get_client()
    cols = ("season,season_type,team_id,group_id,group_name,gp,w,l,min,plus_minus,"
            "off_rating,def_rating,net_rating,poss")
    rows, start, page = [], 0, 1000
    try:
        while True:
            part = (client.table("lineups").select(cols).gte("min", 10)
                    .order("season").order("season_type").order("team_id").order("group_id")
                    .range(start, start + page - 1).execute().data)
            rows += part
            if len(part) < page:
                break
            start += page
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def prep_lineups(lu, team_tbl, league_tbl):
    """整理陣容資料：加上球隊代號、全隊總分鐘（場數 × 48）、全隊整季淨效率、這組陣容佔全隊時間的比例"""
    lu = lu.copy()
    for c in ["gp", "w", "l", "min", "plus_minus", "off_rating", "def_rating", "net_rating", "poss"]:
        lu[c] = pd.to_numeric(lu[c], errors="coerce")
    lu["team_id"] = pd.to_numeric(lu["team_id"], errors="coerce")
    tm = team_tbl[["team_id", "abbreviation", "season", "season_type", "games"]].copy()
    tm["team_id"] = pd.to_numeric(tm["team_id"], errors="coerce")
    tm["team_min"] = pd.to_numeric(tm["games"], errors="coerce") * 48     # 不算延長賽，所以是「約」
    lu = lu.merge(tm.drop(columns="games"), on=["team_id", "season", "season_type"], how="inner")
    if not league_tbl.empty and "net_rating" in league_tbl:
        tn = league_tbl[["team_id", "season", "season_type", "net_rating"]].copy()
        tn["team_id"] = pd.to_numeric(tn["team_id"], errors="coerce")
        tn = tn.rename(columns={"net_rating": "team_net"})
        tn["team_net"] = pd.to_numeric(tn["team_net"], errors="coerce")
        lu = lu.merge(tn, on=["team_id", "season", "season_type"], how="left")
    else:
        lu["team_net"] = float("nan")
    lu["share"] = lu["min"] / lu["team_min"].where(lu["team_min"] > 0)
    # 名字 "S. Curry - K. Thompson - …" → "S. Curry、K. Thompson、…"
    lu["names"] = lu["group_name"].fillna("").map(lambda s: "、".join(x.strip() for x in s.split(" - ") if x.strip()))
    keys = ["season", "season_type", "team_id"]
    lu["rk_min"] = lu.groupby(keys)["min"].rank(ascending=False, method="first")   # 第 1 名＝在場最久
    return lu.sort_values(keys + ["rk_min"]).reset_index(drop=True)


def core_by_season(lu):
    """每隊每季：在場最久的那組（核心陣容），以及前 5 組合計佔全隊多少時間（陣容集中度）"""
    keys = ["abbreviation", "season", "season_type"]
    core = lu[lu["rk_min"] == 1].set_index(keys)
    top5 = lu[lu["rk_min"] <= 5].groupby(keys)["share"].sum().rename("top5_share")
    out = core.join(top5).reset_index()
    out["diff"] = out["net_rating"] - out["team_net"]          # 核心陣容比全隊好多少
    out["champion"] = [(s, a) in CHAMP_SET for s, a in zip(out["season"], out["abbreviation"])]
    return out


if PAGE == "上場陣容":
    hypothesis("冠軍隊是靠「一組固定的核心五人」打出優勢，還是靠很多組陣容輪流上場？",
               "冠軍會有一組核心五人：同時在場的時間明顯比其他組合多，而且這組的淨效率比全隊平均高；"
               "奪冠那季，這組用得比該隊其他球季更多。")
    st.caption("對照組是「同一隊的全隊整季」，不是其他球隊（其他 22 隊沒有陣容數據）。")
    lu_status = table_status("lineups")
    lu_raw = load_lineups() if lu_status == "ok" else pd.DataFrame()
    if lu_raw.empty:
        st.info("尚未載入資料，請執行 python load_extra.py --only lineups"
                + ("（資料表還不存在：請先到 Supabase SQL Editor 執行 schema_extra.sql）"
                   if lu_status == "missing" else ""))
    else:
        LU = prep_lineups(lu_raw, team_raw, league)
        CORE = core_by_season(LU)
        lu_type_zh = seg("比賽類型（整頁）", ["例行賽", "季後賽"], "lu_type")
        lu_type = TYPE_OPTIONS[lu_type_zh]
        thr = LU_MIN[lu_type]
        # ===== 1 八位冠軍的核心五人（先回答假設，不用選球隊；1102-1）=====
        CC = CORE[CORE["champion"] & (CORE["season_type"] == lu_type)].sort_values("season")
        slot3 = section(f"1　八位冠軍的核心五人（{lu_type_zh}）",
                        "灰點＝全隊整季淨效率，彩色點＝核心五人（在場最久的那組）的淨效率；線越長、差距越大")
        if CC.empty:
            st.info("目前的陣容數據裡沒有冠軍球季。")
        else:
            labels = [f"{s} {ALL_ZH.get(a, a)}" for s, a in zip(CC["season"], CC["abbreviation"])]
            fig = go.Figure()
            for lab, (_, r) in zip(labels, CC.iterrows()):
                if pd.notna(r["team_net"]) and pd.notna(r["net_rating"]):
                    fig.add_trace(go.Scatter(x=[r["team_net"], r["net_rating"]], y=[lab, lab], mode="lines",
                                             line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=CC["team_net"], y=labels, mode="markers", name="全隊整季",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>全隊整季淨效率 %{x:+.1f}<extra></extra>"))
            fig.add_trace(go.Scatter(
                x=CC["net_rating"], y=labels, mode="markers", name="核心五人",
                marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in CC["abbreviation"]],
                            line=dict(width=1.5, color=SURFACE)),
                customdata=CC[["names", "min", "share"]].values,
                hovertemplate="%{y}<br>核心五人：%{customdata[0]}<br>"
                              "同時在場 %{customdata[1]:.0f} 分鐘（約佔全隊 %{customdata[2]:.0%}）<br>"
                              "淨效率 %{x:+.1f}<extra></extra>"))
            fig.add_vline(x=0, line=dict(color="#d9d3e6", width=1))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="淨效率（每 100 回合淨勝分）", showgrid=True, gridcolor=GRID)
            st.plotly_chart(style(fig, 90 + 44 * len(CC)), width="stretch", config={"displayModeBar": False})
            ok = CC.dropna(subset=["diff"])
            lines = []
            if len(ok):
                k = int((ok["diff"] > 0).sum())
                lines.append(f"<b>核心比全隊好：</b>{len(ok)} 個冠軍球季裡，有 {k} 個的核心五人淨效率高於全隊整季"
                             f"（平均差 {ok['diff'].mean():+.1f} 分，正數＝核心比較好）。")
            if CC["share"].notna().any():
                lo_ = CC.loc[CC["share"].idxmin()]
                hi_ = CC.loc[CC["share"].idxmax()]
                lines.append(f"<b>用得多不多：</b>核心五人平均約佔全隊 {CC['share'].mean():.0%} 的時間；"
                             f"最依賴核心的是 {hi_['season']} {ALL_ZH.get(hi_['abbreviation'], '')}（{hi_['share']:.0%}），"
                             f"最分散的是 {lo_['season']} {ALL_ZH.get(lo_['abbreviation'], '')}（{lo_['share']:.0%}）。")
            if lines:
                chk = None
                if len(ok):
                    chk = (f"成立：{k} / {len(ok)} 個冠軍球季的核心五人比全隊整季好。" if k > len(ok) / 2 else
                           f"不成立：只有 {k} / {len(ok)} 個冠軍球季的核心五人比全隊整季好。")
                    chk += "（對照組是同一隊的全隊整季，不是其他球隊。）"
                insight(lines, where=slot3, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["核心五人", "同時在場分鐘", "佔全隊時間", "陣容集中度", "陣容戰績", "淨效率"],
                           first_note="表格裡的「戰績」只算這 5 人<b>有同時上場</b>的那些比賽，"
                                      "例如 8 勝 2 敗＝10 場比賽裡他們有一起上場過，不是打滿 10 場。")
            with st.expander("看每一位冠軍的核心五人名單"):
                nice_table(pd.DataFrame({
                    "球季": CC["season"], "冠軍": [ALL_ZH.get(a, a) for a in CC["abbreviation"]],
                    "_key": CC["abbreviation"], "核心五人": CC["names"],
                    "同時在場": [f"{v:.0f} 分" for v in CC["min"]],
                    "佔全隊": [fmt(v, ".0%") for v in CC["share"]],
                    "前 5 組合計": [fmt(v, ".0%") for v in CC["top5_share"]],
                    "核心淨效率": [fmt(v, "+.1f") for v in CC["net_rating"]],
                    "全隊淨效率": [fmt(v, "+.1f") for v in CC["team_net"]],
                    "差距": [fmt(v, "+.1f") for v in CC["diff"]],
                }), num_cols=("同時在場", "佔全隊", "前 5 組合計", "核心淨效率", "全隊淨效率", "差距"),
                    signed_cols=("差距",), dot_col="冠軍", colors=TEAM_COLORS)
        st.divider()

        # ===== 2 單一球隊深入看（球隊、球季條件只放在這一節）=====
        section("2　單一球隊深入看", "選一支球隊和一個球季，看它所有的 5 人陣容；底下 2-1 陣容地圖、2-2 在場最久的 10 組、2-3 逐季變化")
        lu_s = sorted(LU["season"].unique())
        lc, lo = split_teams(sorted(LU["abbreviation"].unique()), lu_s[0], lu_s[-1])
        lu_team = team_picker_one(lc, lo, "lu_team", f"奪冠球隊（{lu_s[0]}～{lu_s[-1]} 拿過冠軍）",
                                  "其他球隊（陣容數據只有八支冠軍隊）")
        c2, _c3 = st.columns(2)
        lu_seasons = sorted(LU[LU["abbreviation"] == lu_team]["season"].unique())[::-1] or lu_s[::-1]
        champ_lu = [s for s in lu_seasons if (s, lu_team) in CHAMP_SET]
        with c2:
            lu_season = st.selectbox(
                "球季", lu_seasons, key=f"lu_season_{lu_team}",
                index=lu_seasons.index(champ_lu[0]) if champ_lu else 0,
                format_func=lambda s: s + ("　★ 奪冠" if (s, lu_team) in CHAMP_SET else ""))
        color = TEAM_COLORS.get(lu_team, ACCENT)
        star = "★" if (lu_season, lu_team) in CHAMP_SET else ""
        who = f"{lu_season} {ALL_ZH.get(lu_team, lu_team)}{star}"

        cur = LU[(LU["abbreviation"] == lu_team) & (LU["season"] == lu_season) & (LU["season_type"] == lu_type)]
        if cur.empty:
            st.info(f"{team_label(lu_team)} {lu_season} {lu_type_zh}沒有陣容數據（可能那季沒打進季後賽，或還沒載入）。")
        else:
            core = cur.iloc[0]
            big = cur[cur["min"] >= thr]
            team_net = core["team_net"]

            # ===== 2-1 這一季的陣容地圖 =====
            slot1 = section(f"2-1　{who} 的陣容地圖（{lu_type_zh}）",
                            "每個圈是一組 5 人陣容。橫軸：同時在場幾分鐘；縱軸：淨效率（每 100 回合淨勝幾分，"
                            "正數＝這 5 人在場時贏對手）；虛線是全隊整季的淨效率", level=2)
            lines = [f"<b>核心五人：</b>{core['names']}，同時在場 {core['min']:.0f} 分鐘"
                     + (f"（約佔全隊 {core['share']:.0%} 的時間）" if pd.notna(core["share"]) else "") + "。"]
            if pd.notna(core["net_rating"]) and pd.notna(team_net):
                d = core["net_rating"] - team_net
                lines.append(f"<b>核心 vs 全隊：</b>這組淨效率 {core['net_rating']:+.1f}，全隊整季 {team_net:+.1f}，"
                             f"{'高' if d >= 0 else '低'} {abs(d):.1f} 分。")
            if len(big) > 1 and big["net_rating"].notna().any():
                best = big.loc[big["net_rating"].idxmax()]
                if best["group_id"] != core["group_id"]:
                    lines.append(f"<b>效率最高：</b>在場至少 {thr} 分鐘的 {len(big)} 組裡，是 {best['names']}"
                                 f"（{best['net_rating']:+.1f}，{best['min']:.0f} 分鐘）。")
                else:
                    lines.append(f"<b>效率最高：</b>在場至少 {thr} 分鐘的 {len(big)} 組裡，也是核心五人。")
            top5 = cur[cur["rk_min"] <= 5]["share"].sum()
            if pd.notna(top5) and top5 > 0:
                lines.append(f"<b>集中度：</b>在場最久的前 5 組合計約佔全隊 {top5:.0%} 的時間。")
            insight(lines, where=slot1)

            plot = (big if len(big) >= 3 else cur).head(25)
            fig = go.Figure()
            if pd.notna(team_net):
                fig.add_hline(y=team_net, line=dict(color=MUTED, width=1, dash="dash"),
                              annotation_text=f"全隊整季 {team_net:+.1f}", annotation_position="top left",
                              annotation_font=dict(size=11, color=INK_2))
            fig.add_hline(y=0, line=dict(color="#d9d3e6", width=1))
            size = 10 + 30 * (plot["poss"].fillna(0) / max(plot["poss"].max() or 1, 1)) ** 0.5
            fig.add_trace(go.Scatter(
                x=plot["min"], y=plot["net_rating"], mode="markers+text",
                text=[f"第 {int(r)} 組" if r <= 3 else "" for r in plot["rk_min"]],
                textposition="top center", textfont=dict(size=11, color=INK),
                marker=dict(size=size, color=color, opacity=0.75, line=dict(width=1.5, color=SURFACE)),
                customdata=plot[["names", "gp", "w", "l", "off_rating", "def_rating", "rk_min"]].values,
                hovertemplate="<b>第 %{customdata[6]:.0f} 組</b>　%{customdata[0]}<br>"
                              "同時在場 %{x:.0f} 分鐘、%{customdata[1]:.0f} 場（%{customdata[2]:.0f} 勝 %{customdata[3]:.0f} 敗）<br>"
                              "淨效率 %{y:+.1f}（進攻 %{customdata[4]:.1f}／防守 %{customdata[5]:.1f}）<extra></extra>"))
            fig.update_xaxes(title="同時在場分鐘", rangemode="tozero")
            fig.update_yaxes(title="淨效率（每 100 回合淨勝分）")
            fig.update_layout(showlegend=False)
            st.plotly_chart(style(fig, 420), width="stretch", config={"displayModeBar": False})
            if len(big) < 3:
                st.caption(f"在場至少 {thr} 分鐘的組合不到 3 組，所以把所有組合都畫出來；在場時間很短的組合，淨效率起伏很大，參考就好。")

            # ===== 2-2 在場最久的 10 組 =====
            section("2-2　在場最久的 10 組", "長條＝同時在場分鐘；淨效率＝進攻效率 − 防守效率（防守效率越低越好）", level=2)
            top = cur.head(10)
            mx = top["min"].max() or 1
            nice_table(pd.DataFrame({
                "排名": [f"第 {int(r)} 組" for r in top["rk_min"]],
                "5 人陣容": top["names"],
                "同時在場": [f"{v:.0f} 分" for v in top["min"]],
                "_bar": top["min"] / mx,
                "佔全隊": [fmt(v, ".0%") for v in top["share"]],
                "戰績": [f"{int(w)}-{int(l)}" if pd.notna(w) and pd.notna(l) else "-" for w, l in zip(top["w"], top["l"])],
                "進攻效率": [fmt(v, ".1f") for v in top["off_rating"]],
                "防守效率": [fmt(v, ".1f") for v in top["def_rating"]],
                "淨效率": [fmt(v, "+.1f") for v in top["net_rating"]],
            }), num_cols=("同時在場", "佔全隊", "戰績", "進攻效率", "防守效率", "淨效率"),
                signed_cols=("淨效率",), bars={"同時在場": "_bar"})
            st.caption("戰績是「這 5 人有同時上場的那些比賽」的勝負，不代表他們打滿全場。")

        # ===== 2-3 這支球隊逐季：奪冠那季的核心用得比較多嗎？ =====
        TS = CORE[(CORE["abbreviation"] == lu_team) & (CORE["season_type"] == lu_type)].sort_values("season")
        slot4 = section(f"2-3　{ALL_ZH.get(lu_team, lu_team)}逐季：核心五人用得多不多？（{lu_type_zh}）",
                        "長條＝在場最久那組佔全隊時間的比例（紫色＝奪冠球季），長條上的數字＝這組的淨效率；"
                        "折線＝前 5 組合計佔比，越高代表教練越固定用那幾組", level=2)
        if len(TS) < 2:
            st.info("這支球隊的陣容數據不到兩季，還不能看逐季變化。")
        else:
            xs = list(TS["season"])
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=xs, y=TS["share"] * 100, name="核心五人佔比",
                marker=dict(color=[ACCENT if c else "#cfc8de" for c in TS["champion"]]),
                text=[fmt(v, "+.1f") for v in TS["net_rating"]], textposition="outside",
                textfont=dict(size=11, color=INK_2),
                customdata=TS[["names", "min"]].values,
                hovertemplate="%{x}<br>核心五人：%{customdata[0]}<br>同時在場 %{customdata[1]:.0f} 分鐘，"
                              "約佔全隊 %{y:.1f}%<br>淨效率 %{text}<extra></extra>"))
            fig.add_trace(go.Scatter(x=xs, y=TS["top5_share"] * 100, name="前 5 組合計佔比", mode="lines+markers",
                                     line=dict(color=INK_2, width=1.8), marker=dict(size=6, color=INK_2),
                                     hovertemplate="%{x}<br>前 5 組合計約佔 %{y:.1f}%<extra></extra>"))
            rounded(fig)
            champion_bands(fig, xs, lu_team)
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=xs)
            fig.update_yaxes(title="佔全隊時間（%）", rangemode="tozero")
            st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})
            won, rest = TS[TS["champion"]], TS[~TS["champion"]]
            if len(won) and len(rest) and rest["share"].notna().any():
                a, b = won["share"].mean(), rest["share"].mean()
                insight([f"<b>奪冠季 vs 其他季：</b>奪冠那{'幾' if len(won) > 1 else ''}季，核心五人約佔全隊 {a:.0%} 的時間，"
                         f"其他 {len(rest)} 季平均 {b:.0%}。"
                         + ("奪冠時更依賴固定的核心，符合假設。" if a > b else "奪冠時反而沒有更依賴同一組人，假設不成立。")],
                        where=slot4)
            elif not len(won):
                insight([f"這段期間 {ALL_ZH.get(lu_team, lu_team)} 沒有奪冠球季，可以當作對照組來看。"], where=slot4)

        with st.expander("資料來源與方法"):
            st.markdown(
                f"- 資料：`lineups` 表（NBA 官方 5 人陣容數據，{lu_s[0]}～{lu_s[-1]}，只有八支冠軍隊），"
                "全隊淨效率來自 `league_team_seasons`。\n"
                "- 只讀取同時在場至少 10 分鐘的組合；比較「效率最高」時，例行賽至少 50 分鐘、季後賽至少 15 分鐘，"
                "因為在場時間很短的組合，幾個回合就能讓淨效率大起大落。\n"
                "- 佔全隊時間＝這組在場分鐘 ÷（場數 × 48 分鐘），沒有算延長賽，所以是約略值。\n"
                "- 「核心五人」的定義：同一季、同一種比賽裡，同時在場最久的那一組。")


# ---------- 籤運與傷兵：冠軍是不是靠運氣？ ----------
OLD_ABBR = {"NJN": "BKN", "SEA": "OKC", "NOH": "NOP", "NOK": "NOP", "CHH": "CHA", "VAN": "MEM"}   # 搬家、改名前的縮寫
ROUND_ZH = ["首輪", "次輪", "分區決賽", "總冠軍賽"]


@st.cache_data(ttl=3600, show_spinner="讀取季後賽賽程中…")
def load_playoff_games(team_id):
    """某隊所有季後賽比賽：哪一天、對手是誰（從 matchup 文字拆出來）、輸贏"""
    try:
        rows = (get_client().table("team_games")
                .select("game_id,matchup,wl,games!inner(game_date,season,season_type)")
                .eq("team_id", int(team_id)).eq("games.season_type", "Playoffs")
                .range(0, 999).execute().data)
    except Exception:
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.json_normalize(rows).rename(columns=lambda c: c.replace("games.", ""))
    df = df[df["season_type"] == "Playoffs"]
    # 「GSW vs. BOS」或「GSW @ BOS」：最後一段就是對手
    df["opp"] = df["matchup"].str.split().str[-1].map(lambda a: OLD_ABBR.get(a, a))
    return df


@st.cache_data(ttl=3600)
def load_regular_h2h(team_id, season):
    """某隊某季例行賽對每一隊的戰績：{對手: (勝, 敗)}"""
    try:
        rows = (get_client().table("team_games")
                .select("game_id,matchup,wl,games!inner(season,season_type)")
                .eq("team_id", int(team_id)).eq("games.season", season)
                .eq("games.season_type", "Regular Season").range(0, 999).execute().data)
    except Exception:
        return {}
    if not rows:
        return {}
    df = pd.json_normalize(rows).rename(columns=lambda c: c.replace("games.", ""))
    df = df[(df["season"] == season) & (df["season_type"] == "Regular Season")]
    df["opp"] = df["matchup"].str.split().str[-1].map(lambda x: OLD_ABBR.get(x, x))
    return {o: (int((g["wl"] == "W").sum()), int((g["wl"] == "L").sum())) for o, g in df.groupby("opp")}


def h2h_txt(rec):
    return "-" if not rec else f"{rec[0]} 勝 {rec[1]} 敗"


@st.cache_data(ttl=3600)
def load_game_players(game_ids, team_id):
    """這幾場比賽，某隊有上場的球員（有出賽紀錄＝有上場；沒有紀錄＝沒上場）"""
    if not game_ids:
        return pd.DataFrame()
    try:
        rows = (get_client().table("player_game_stats").select("game_id,player_id,min")
                .in_("game_id", list(game_ids)).eq("team_id", int(team_id))
                .range(0, 4999).execute().data)
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def core_players(abbr, season, n=3):
    """一支球隊當季例行賽的「主力」：出賽至少 20 場、場均得分最高的 n 人"""
    d = player_raw[(player_raw["abbreviation"] == abbr) & (player_raw["season"] == season)
                   & (player_raw["season_type"] == "Regular Season")].copy()
    if d.empty:
        return pd.DataFrame()
    for c in ["gp", "pts", "min"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["gp"] >= 20]
    d["ppg"] = d["pts"] / d["gp"]
    return d.sort_values("ppg", ascending=False).head(n)[["player_id", "player_name", "ppg", "gp"]]


def missing_core(abbr, team_id, season, game_ids):
    """主力缺陣：這幾場比賽中，主力「沒有出賽紀錄」的人次。回傳（缺陣人次, 可能人次, 缺陣名單）"""
    core = core_players(abbr, season)
    if core.empty:
        return None
    played = load_game_players(tuple(game_ids), team_id)
    if played.empty:
        return None
    miss, names = 0, []
    for _, p in core.iterrows():
        k = sum(1 for g in game_ids if not ((played["game_id"] == g) & (played["player_id"] == p["player_id"])).any())
        miss += k
        if k:
            names.append(f"{p['player_name']}（缺 {k} 場）")
    return miss, len(core) * len(game_ids), names


if PAGE == "籤運與傷兵":
    hypothesis("冠軍是不是「籤運比較好」（季後賽遇到的對手比較弱），或是對手主力受傷缺陣，才拿到冠軍？",
               "冠軍的季後賽對手，例行賽實力和其他季後賽球隊差不多；對手主力缺陣的比例也不會特別高。"
               "也就是說，冠軍主要靠實力，不是靠運氣。")
    if league.empty:
        st.info("需要全聯盟數據才能比較對手強弱，請先執行：python load_to_supabase.py --only league")
    else:
        L = league[league["season_type"] == "Regular Season"].copy()
        for c in ["net_rating", "w", "gp"]:
            L[c] = pd.to_numeric(L[c], errors="coerce")
        L["rk_net"] = L.groupby("season")["net_rating"].rank(ascending=False, method="min")
        Lk = L.set_index(["season", "abbreviation"])
        playoff_teams = league[league["season_type"] == "Playoffs"][["season", "abbreviation"]]
        abbr2tid = dict(zip(league["abbreviation"], league["team_id"]))

        # 每一位冠軍的季後賽路線
        loaded = set(team_raw["abbreviation"])
        series_rows = []
        for s_, a_ in sorted(CHAMP_SET):
            if a_ not in loaded or s_ not in set(L["season"]):
                continue
            pg = load_playoff_games(abbr2tid.get(a_, 0))
            if pg.empty:
                continue
            pg = pg[pg["season"] == s_]
            if pg.empty:
                continue
            first = pg.groupby("opp")["game_date"].min().sort_values()
            for rnd, (opp, _) in enumerate(first.items()):
                g = pg[pg["opp"] == opp]
                o = Lk.loc[(s_, opp)] if (s_, opp) in Lk.index else None
                series_rows.append({
                    "season": s_, "champ": a_, "round": rnd, "opp": opp,
                    "games": len(g), "w": int((g["wl"] == "W").sum()), "l": int((g["wl"] == "L").sum()),
                    "opp_net": None if o is None else float(o["net_rating"]),
                    "opp_rk": None if o is None else int(o["rk_net"]),
                    "game_ids": tuple(g["game_id"]),
                })
        S = pd.DataFrame(series_rows)
        if S.empty:
            st.info("資料庫裡還沒有冠軍隊的季後賽比賽，請先執行：python load_to_supabase.py --only players")
        else:
            # ===== 證據一：籤運（對手強不強）=====
            path = (S.groupby(["season", "champ"]).agg(opp_net=("opp_net", "mean"), n=("opp", "count"))
                    .reset_index())
            # 對照組：同一季所有季後賽球隊（不含冠軍）的平均淨效率＝「隨機抽一隊」的平均強度
            base = []
            for s_, a_ in zip(path["season"], path["champ"]):
                pt_ = playoff_teams[(playoff_teams["season"] == s_) & (playoff_teams["abbreviation"] != a_)]
                v = L[(L["season"] == s_) & L["abbreviation"].isin(pt_["abbreviation"])]["net_rating"].mean()
                base.append(v)
            path["base"] = base
            path["luck"] = path["opp_net"] - path["base"]   # 負的＝對手比一般季後賽球隊弱＝籤運好
            path["label"] = path["season"] + " " + path["champ"].map(team_label)
            path = path.sort_values("season")

            s1 = section("證據一：冠軍的季後賽對手，比一般季後賽球隊弱嗎？",
                         "每一條是一位冠軍：紫點＝他季後賽遇到的對手，例行賽淨效率平均；灰線＝同一季所有季後賽球隊的平均。"
                         "紫點在灰線左邊＝對手比較弱（籤運好）")
            easy = path[path["luck"] < -1.0]
            hard = path[path["luck"] > 1.0]
            insight(where=s1, lines=[
                f"{len(path)} 位冠軍中，<b>{len(easy)}</b> 位的對手明顯比一般季後賽球隊弱（淨效率低 1 分以上），"
                f"<b>{len(hard)}</b> 位的對手明顯比較強，其他 {len(path) - len(easy) - len(hard)} 位差不多。",
                (f"籤運最好：<b>{path.loc[path['luck'].idxmin(), 'label']}</b>"
                 f"（對手平均 {path['opp_net'].min():+.1f}，比一般季後賽球隊低 {abs(path['luck'].min()):.1f}）；"
                 f"最硬的路：<b>{path.loc[path['luck'].idxmax(), 'label']}</b>（高 {path['luck'].max():.1f}）。")
                if path["luck"].notna().any() else "對手資料不足。",
                "讀法：淨效率是「每 100 回合贏對手幾分」，+5 大約是強隊、0 是普通隊。"
                + ("大多數冠軍的對手和一般季後賽球隊差不多，「籤運好才奪冠」的說法站不太住。"
                   if len(easy) <= len(path) / 3 else "不少冠軍的對手確實偏弱，籤運可能有幫上忙。"),
            ])
            fig = go.Figure()
            ys = list(path["label"])
            for _, r in path.iterrows():
                fig.add_shape(type="line", x0=r["base"], x1=r["opp_net"], y0=r["label"], y1=r["label"],
                              line=dict(color="#d9d3e6", width=3))
            fig.add_trace(go.Scatter(x=path["base"], y=ys, mode="markers", name="同季季後賽球隊平均",
                                     marker=dict(symbol="line-ns", size=16, line=dict(width=3, color="#8f889f")),
                                     hovertemplate="%{y}<br>季後賽球隊平均 %{x:+.1f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=path["opp_net"], y=ys, mode="markers", name="冠軍遇到的對手平均",
                                     marker=dict(size=12, color=[TEAM_COLORS.get(a, ACCENT) for a in path["champ"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     customdata=path[["luck", "n"]].values,
                                     hovertemplate="%{y}<br>對手平均 %{x:+.1f}（差 %{customdata[0]:+.1f}，"
                                                   "共 %{customdata[1]} 輪）<extra></extra>"))
            fig = style(fig, 90 + 34 * len(path))
            fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
            fig.update_xaxes(title="例行賽淨效率（每 100 回合淨勝分）", showgrid=True, gridcolor=GRID,
                             tickformat="+.0f", zeroline=True, zerolinecolor="#d9d3e6")
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"))
            st.plotly_chart(fig, width="stretch")

            # ===== 證據二：遇到的是「剋得住」的對手，還是避開了剋星？=====
            st.write("")
            h_rows = []
            for _, r in path.iterrows():
                rec = load_regular_h2h(abbr2tid.get(r["champ"], 0), r["season"])
                if not rec:
                    continue
                met = set(S[(S["season"] == r["season"]) & (S["champ"] == r["champ"])]["opp"])
                pteams = set(playoff_teams[playoff_teams["season"] == r["season"]]["abbreviation"]) - {r["champ"]}
                def pct(teams):
                    w = sum(rec.get(t, (0, 0))[0] for t in teams)
                    l_ = sum(rec.get(t, (0, 0))[1] for t in teams)
                    return (w / (w + l_) if w + l_ else float("nan")), w, l_
                m_pct, mw, ml = pct(met)
                a_pct, aw, al = pct(pteams - met)
                nemesis = sorted(t for t in pteams if rec.get(t, (0, 0))[1] > rec.get(t, (0, 0))[0])
                h_rows.append({"label": r["label"], "champ": r["champ"], "season": r["season"],
                               "met": m_pct, "mw": mw, "ml": ml, "avoid": a_pct, "aw": aw, "al": al,
                               "nemesis": nemesis, "nem_met": [t for t in nemesis if t in met]})
            H = pd.DataFrame(h_rows)
            s3 = section("證據二：遇到的是「例行賽打得贏」的對手，還是剛好避開了剋星？",
                         "紫點＝冠軍例行賽對「季後賽有遇到的對手」的勝率；灰點＝對「其他季後賽球隊（沒遇到的）」的勝率。"
                         "紫點比灰點右邊很多＝遇到的剛好都是打得贏的隊")
            if H.empty:
                insight(where=s3, lines=["冠軍隊的例行賽對戰紀錄還沒載入，暫時算不出來。"])
            else:
                lucky = H[(H["met"] - H["avoid"]) > 0.10]
                dodge = H[H["nemesis"].map(len) > 0]
                dodged = dodge[dodge.apply(lambda r: len(r["nem_met"]) < len(r["nemesis"]), axis=1)]
                insight(where=s3, lines=[
                    f"{len(H)} 位冠軍中，<b>{len(lucky)}</b> 位對「季後賽遇到的對手」的例行賽勝率，"
                    f"比對「沒遇到的季後賽球隊」高 10 個百分點以上（＝季後賽遇到的，剛好是自己例行賽打得贏的隊）。",
                    f"有剋星（例行賽輸比贏多的季後賽球隊）的冠軍有 {len(dodge)} 位，其中 <b>{len(dodged)}</b> 位"
                    f"在季後賽沒碰到全部的剋星"
                    + (f"（例如 {dodged.iloc[0]['label']} 沒遇到 "
                       f"{'、'.join(t for t in dodged.iloc[0]['nemesis'] if t not in dodged.iloc[0]['nem_met'])}）。"
                       if len(dodged) else "。"),
                    "提醒：例行賽一隊只交手 2～4 場，樣本很小，勝率差一場就差 25% 以上，要搭配證據一的「對手整體實力」一起看。",
                ])
                fig = go.Figure()
                for _, r in H.iterrows():
                    fig.add_shape(type="line", x0=r["avoid"], x1=r["met"], y0=r["label"], y1=r["label"],
                                  line=dict(color="#d9d3e6", width=3))
                fig.add_trace(go.Scatter(x=H["avoid"], y=H["label"], mode="markers", name="對沒遇到的季後賽球隊",
                                         marker=dict(size=11, color="#b3adc2", line=dict(width=1.5, color=SURFACE)),
                                         customdata=H[["aw", "al"]].values,
                                         hovertemplate="%{y}<br>沒遇到的：%{customdata[0]} 勝 %{customdata[1]} 敗"
                                                       "（%{x:.0%}）<extra></extra>"))
                fig.add_trace(go.Scatter(x=H["met"], y=H["label"], mode="markers", name="對季後賽有遇到的對手",
                                         marker=dict(size=12, color=[TEAM_COLORS.get(a_, ACCENT) for a_ in H["champ"]],
                                                     line=dict(width=1.5, color=SURFACE)),
                                         customdata=H[["mw", "ml"]].values,
                                         hovertemplate="%{y}<br>有遇到的：%{customdata[0]} 勝 %{customdata[1]} 敗"
                                                       "（%{x:.0%}）<extra></extra>"))
                fig = style(fig, 90 + 34 * len(H))
                fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
                fig.update_xaxes(title="例行賽交手勝率", tickformat=".0%", range=[-0.05, 1.05], showgrid=True, gridcolor=GRID)
                fig.update_layout(legend=dict(orientation="h", y=1.04, x=0, yanchor="bottom"))
                st.plotly_chart(fig, width="stretch")

            # ===== 一位冠軍的季後賽路線（逐輪）=====
            st.write("")
            opts = list(path["label"])
            pick = st.selectbox("選一位冠軍，看他每一輪遇到誰", opts[::-1], key="luck_pick")
            ps, pc = pick.split()[0], pick.split()[1]
            one = S[(S["season"] == ps) & (S["champ"] == pc)].sort_values("round")
            s2 = section(f"{pick} 的季後賽路線",
                         "對手的例行賽淨效率與聯盟排名（1 = 最強）；主力缺陣＝對手例行賽得分前 3 名在這個系列賽沒上場的場次")
            rec_one = load_regular_h2h(abbr2tid.get(pc, 0), ps)
            rows, miss_tot, poss_tot, own_tot, own_poss = [], 0, 0, 0, 0
            for _, r in one.iterrows():
                m = missing_core(r["opp"], abbr2tid.get(r["opp"], 0), ps, r["game_ids"])
                mo = missing_core(pc, abbr2tid.get(pc, 0), ps, r["game_ids"])
                if m:
                    miss_tot += m[0]; poss_tot += m[1]
                if mo:
                    own_tot += mo[0]; own_poss += mo[1]
                rows.append({"輪次": ROUND_ZH[r["round"]] if r["round"] < 4 else f"第 {r['round'] + 1} 輪",
                             "對手": team_label(r["opp"]), "_key": r["opp"],
                             "系列賽": f"{r['w']} 勝 {r['l']} 敗",
                             "例行賽交手": h2h_txt(rec_one.get(r["opp"])),
                             "對手淨效率": "-" if pd.isna(r["opp_net"]) else f"{r['opp_net']:+.1f}",
                             "聯盟排名": "-" if pd.isna(r["opp_rk"]) else f"第 {int(r['opp_rk'])}",
                             "對手主力缺陣": "尚未載入對手資料" if m is None else
                                         ("無" if not m[0] else "、".join(m[2])),
                             "冠軍自己主力缺陣": "-" if mo is None else ("無" if not mo[0] else "、".join(mo[2]))})
            lines = []
            if poss_tot:
                lines.append(f"對手主力缺陣比例：<b>{miss_tot / poss_tot:.0%}</b>（{miss_tot} / {poss_tot} 人次）；"
                             f"冠軍自己：{(own_tot / own_poss if own_poss else 0):.0%}。"
                             + ("對手缺陣明顯比較多，傷兵可能幫了忙。" if own_poss and miss_tot / poss_tot > own_tot / own_poss + 0.10
                                else "兩邊差不多，看不出是靠對手傷兵。"))
            else:
                lines.append("對手的球員逐場數據還沒載入，暫時算不出主力缺陣（每天會自動加入 2 隊，載入後這裡就會出現）。")
            insight(lines, where=s2)
            nice_table(pd.DataFrame(rows), num_cols=("對手淨效率", "聯盟排名"), dot_col="對手", colors=TEAM_COLORS)

            # 當季所有季後賽球隊：有沒有遇到、例行賽打不打得贏（剋星標出來）
            pteams = sorted(set(playoff_teams[playoff_teams["season"] == ps]["abbreviation"]) - {pc})
            if pteams and rec_one:
                met_one = set(one["opp"])
                all_rows = []
                for t in pteams:
                    w_, l_ = rec_one.get(t, (0, 0))
                    o = Lk.loc[(ps, t)] if (ps, t) in Lk.index else None
                    all_rows.append({"_key": t, "季後賽球隊": team_label(t),
                                     "例行賽交手": h2h_txt((w_, l_)) if w_ + l_ else "-",
                                     "_diff": w_ - l_,
                                     "對手淨效率": "-" if o is None else f"{float(o['net_rating']):+.1f}",
                                     "季後賽有遇到嗎": "有遇到" if t in met_one else "沒遇到",
                                     "註記": "剋星（例行賽輸比贏多）" if l_ > w_ else ""})
                at = pd.DataFrame(all_rows).sort_values(["_diff", "季後賽球隊"])
                section(f"{pick} 對當季所有季後賽球隊的例行賽戰績",
                        "由「最打不贏」排到「最打得贏」；看看剋星有沒有在季後賽遇到")
                nice_table(at, num_cols=("例行賽交手", "對手淨效率"), dot_col="季後賽球隊", colors=TEAM_COLORS)

            with st.expander("資料來源與方法、限制"):
                st.markdown("""
- **對手強弱**：對手在同一季**例行賽**的淨效率（league_team_seasons）。對照組是同一季所有打進季後賽的球隊（不含冠軍）的平均，代表「隨便抽到一個季後賽對手」大概多強。
- **季後賽路線**：從冠軍隊的季後賽比賽（team_games 的 matchup，例如「GSW vs. BOS」）拆出對手，依第一場的日期排出第幾輪。
- **例行賽交手**：冠軍那季例行賽對每一隊的勝敗（team_games 的 matchup 與勝負），比較「季後賽有遇到的對手」和「其他季後賽球隊」；例行賽輸比贏多的季後賽球隊稱為「剋星」。
- **主力缺陣**：對手例行賽出賽至少 20 場、場均得分前 3 名的球員，在系列賽中「沒有出賽紀錄」的場次。
- **限制**：資料庫沒有傷病報告，所以「沒上場」可能是受傷、休息、禁賽或教練決定，**不一定是傷兵**；對手的球員數據要等該隊載入後才算得出來；季中交易來的球員算在新球隊。
""")


# ---------- 跑動距離：冠軍跑得比較多嗎？ ----------
def corr_word(r):
    a = abs(r)
    return "幾乎沒有關係" if a < 0.1 else "弱相關" if a < 0.3 else "中等相關" if a < 0.5 else "強相關"


if PAGE == "跑動距離":
    hypothesis("冠軍隊是不是跑得比較多、比較快？跑得多和贏球有沒有關係？",
               "跑動不是奪冠的關鍵：冠軍的跑動距離在聯盟多半排中段，「比同季聯盟多跑」和勝率只有弱相關（|r| < 0.3）。")
    status = table_status("tracking_speed")
    TR = prep_tracking(load_tracking("team"), league) if status == "ok" else pd.DataFrame()
    if TR.empty:
        st.info("尚未載入資料，請執行 python load_extra.py --only tracking"
                + ("（資料表還沒建立，請先在 Supabase SQL Editor 執行 schema_extra.sql）" if status == "missing" else ""))
    else:
        c1, _c2 = st.columns([2, 3])
        with c1:
            tr_type = seg("比賽類型", ["例行賽", "季後賽"], "tr_type")
        st_code = TYPE_OPTIONS[tr_type]
        T = TR[TR["season_type"] == st_code]
        tr_seasons = sorted(T["season"].unique())
        if not tr_seasons:
            st.info(f"還沒有{tr_type}的跑動數據。")
        else:
            # ===== 1 每一位冠軍排第幾（先回答假設；1103-1） =====
            slot2 = section("1　每一位冠軍的跑動排第幾？", "聯盟排名 1＝跑最多／最快；最後一欄是勝率排名，拿來對照")
            CHT = T[T["champion"]].sort_values("season")
            if CHT.empty:
                st.info("跑動數據的球季裡沒有已完成的冠軍球季。")
            else:
                tb = pd.DataFrame({
                    "球季": CHT["season"], "冠軍": [team_label(a) for a in CHT["abbreviation"]],
                    "每場公里": CHT["dist_km"].map(lambda v: f"{v:.1f}"),
                    "距離排名": CHT["rk_dist_km"].map(lambda v: f"第 {v:.0f}"),
                    "速度排名": CHT["rk_spd"].map(lambda v: f"第 {v:.0f}"),
                    "進攻速度排名": CHT["rk_spd_off"].map(lambda v: f"第 {v:.0f}"),
                    "防守速度排名": CHT["rk_spd_def"].map(lambda v: f"第 {v:.0f}"),
                    "勝率排名": CHT["rk_win"].map(lambda v: "-" if pd.isna(v) else f"第 {v:.0f}"),
                    "_key": CHT["abbreviation"],
                    "_bar": 1 - (CHT["rk_dist_km"] - 1) / 29,
                })
                nice_table(tb, num_cols=("每場公里", "距離排名", "速度排名", "進攻速度排名", "防守速度排名", "勝率排名"),
                           dot_col="冠軍", colors=TEAM_COLORS, bars={"距離排名": "_bar"})
                med = CHT["rk_dist_km"].median()
                mid = int(CHT["rk_dist_km"].between(8, 23).sum())
                top10 = int((CHT["rk_dist_km"] <= 10).sum())
                insight(where=slot2, label="發現", lines=[
                    f"{len(CHT)} 位冠軍的跑動距離排名中位數是第 {med:.0f} 名；排前 10 的只有 {top10} 位。",
                    f"排在中段（第 8～23 名）的有 {mid} 位；同一批冠軍的勝率排名中位數是第 {CHT['rk_win'].median():.0f} 名。",
                ], check=("成立：冠軍多半排中段，不是靠跑得多。" if 8 <= med <= 23 else
                          ("不成立：冠軍多半跑得比別人多。" if med < 8 else "不成立：冠軍反而多半跑得比較少。")))
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["每場跑動距離", "平均速度", "進攻速度／防守速度", "比同季聯盟平均多多少", "每 36 分鐘跑動", "相關係數 r"],
                           first_note="平均速度只有 7 公里／小時左右，是因為它把走路、站著等罰球的時間都算進去，"
                                      "不是球員衝刺的速度。")

            st.divider()
            # ===== 2 跑得多和贏球有關嗎 =====
            slot3 = section("2　跑得多和贏球有關嗎？",
                            "每個點是一隊一季：橫軸是「比同季聯盟平均多多少」（排除年代差異），縱軸是勝率；★ 是冠軍")
            tr_m = pills("指標", list(TRACK_OPTS), "tr_metric", default="每場跑動距離")
            col, unit = TRACK_OPTS[tr_m]
            A = T.dropna(subset=[f"d_{col}", "win_pct"])
            if len(A) < 10:
                st.info("資料不足，無法計算相關係數。")
            else:
                r = A[f"d_{col}"].corr(A["win_pct"])
                fig = go.Figure()
                o = A[~A["champion"]]
                fig.add_trace(go.Scatter(x=o[f"d_{col}"], y=o["win_pct"], mode="markers", name="其他球隊季",
                                         marker=dict(size=7, color="#c9c3d6", opacity=0.75, line=dict(width=0.5, color=SURFACE)),
                                         text=[f"{s_} {team_label(a_)}" for s_, a_ in zip(o["season"], o["abbreviation"])],
                                         hovertemplate="%{text}<br>比聯盟 %{x:+.2f} " + unit + "<br>勝率 %{y:.1%}<extra></extra>"))
                c = A[A["champion"]]
                fig.add_trace(go.Scatter(x=c[f"d_{col}"], y=c["win_pct"], mode="markers+text", name="冠軍",
                                         text=[f"{s_[2:4]}{s_[5:]} {a_}" for s_, a_ in zip(c["season"], c["abbreviation"])],
                                         textposition="top center", textfont=dict(size=10, color=INK_2),
                                         marker=dict(symbol="star", size=15, color=ACCENT, line=dict(width=1, color=SURFACE)),
                                         hovertemplate="★ %{text}<br>比聯盟 %{x:+.2f} " + unit + "<br>勝率 %{y:.1%}<extra></extra>"))
                fig.add_vline(x=0, line=dict(color=MUTED, dash="dot", width=1))
                fig.update_xaxes(title=f"{tr_m}：比同季聯盟平均多多少（{unit}）")
                fig.update_yaxes(title="勝率", tickformat=".0%")
                st.plotly_chart(style(fig, 420), width="stretch")
                insight(where=slot3, label="發現", lines=[
                    f"{tr_m}和勝率的相關係數 r = {r:+.2f}（{corr_word(r)}），共 {len(A)} 個球隊季。",
                    f"冠軍的★ 有 {int((c[f'd_{col}'] > 0).sum())} / {len(c)} 個在虛線右邊（比同季聯盟平均{'多' if col == 'dist_km' else '快'}）。",
                    "讀法：點如果像一團雲，就是沒什麼關係；如果排成從左下到右上的斜線，就是「跑越多越會贏」。"
                    "相關係數 0.1 以下幾乎沒關係、0.3 以上算中等。",
                ], check=("成立：|r| < 0.3，跑得多和勝率只有弱相關。" if abs(r) < 0.3 else
                          f"不成立：|r| = {abs(r):.2f}，跑動和勝率有明顯關係。"))

            # ===== 3 單一球季深入看（球季條件只放在這一節；1103-1）=====
            st.divider()
            section("3　單一球季深入看", "選一個球季，看 30 隊的跑動地圖和隊上誰跑最多；底下 3-1 各隊跑動地圖、3-2 隊上誰跑最多")
            _sc, _ = st.columns([2, 3])
            with _sc:
                tr_season = st.selectbox("球季", tr_seasons[::-1], key="tr_season",
                                         format_func=lambda x: x + ("　★" if any(s_ == x for s_, _ in CHAMP_SET) else ""))

            # ===== 3-1 各隊跑動地圖 =====
            slot1 = section(f"3-1　{tr_season} 各隊跑動地圖",
                            "每個點是一支球隊：橫軸每場跑幾公里、縱軸平均速度；虛線是聯盟平均，★ 是當季冠軍；"
                            "只標出冠軍、跑最多、跑最少三隊，其他球隊把滑鼠移上去看", level=2)
            cur = T[T["season"] == tr_season].dropna(subset=["dist_km"])
            fig = go.Figure()
            others = cur[~cur["champion"]]
            fig.add_trace(go.Scatter(
                x=others["dist_km"], y=others["spd"], mode="markers", text=[team_label(a_) for a_ in others["abbreviation"]],
                name="其他球隊",
                marker=dict(size=10, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                hovertemplate="%{text}<br>每場 %{x:.2f} 公里<br>平均 %{y:.2f} 公里／小時<extra></extra>"))
            chs = cur[cur["champion"]]
            if len(chs):
                fig.add_trace(go.Scatter(
                    x=chs["dist_km"], y=chs["spd"], mode="markers+text",
                    text=[f"★ {ALL_ZH.get(a_, a_)}" for a_ in chs["abbreviation"]],
                    textposition="top center", textfont=dict(size=11, color=INK), name="冠軍",
                    marker=dict(symbol="star", size=18, color=[TEAM_COLORS.get(a, ACCENT) for a in chs["abbreviation"]],
                                line=dict(width=1.2, color=SURFACE)),
                    hovertemplate="冠軍 %{text}<br>每場 %{x:.2f} 公里<br>平均 %{y:.2f} 公里／小時<extra></extra>"))
            # 只標跑最多、跑最少兩隊（冠軍已經有★ 和隊名），其他滑鼠移上去看（1103-3）
            if len(cur) >= 2:
                for r_, txt_ in [(cur.loc[cur["dist_km"].idxmax()], "跑最多"), (cur.loc[cur["dist_km"].idxmin()], "跑最少")]:
                    if not r_["champion"]:
                        fig.add_annotation(x=r_["dist_km"], y=r_["spd"], text=f"{ALL_ZH.get(r_['abbreviation'], r_['abbreviation'])}（{txt_}）",
                                           showarrow=True, arrowhead=0, arrowcolor=MUTED, ax=0, ay=-26,
                                           font=dict(size=11, color=INK_2))
            fig.add_vline(x=cur["dist_km"].mean(), line=dict(color=MUTED, dash="dot", width=1))
            fig.add_hline(y=cur["spd"].mean(), line=dict(color=MUTED, dash="dot", width=1))
            fig.update_xaxes(title="每場跑動距離（公里，越右跑越多）")
            fig.update_yaxes(title="平均速度（公里／小時）")
            fig.update_layout(showlegend=False)
            st.plotly_chart(style(fig, 440), width="stretch")
            lines = []
            if len(chs):
                r0 = chs.iloc[0]
                lines.append(f"{tr_season} 冠軍 <b>{team_label(r0['abbreviation'])}</b> 每場跑 {r0['dist_km']:.1f} 公里，"
                             f"聯盟第 {r0['rk_dist_km']:.0f} 名；平均速度第 {r0['rk_spd']:.0f} 名。")
            top = cur.sort_values("dist_km", ascending=False).iloc[0]
            lines.append(f"這季跑最多的是 {team_label(top['abbreviation'])}（{top['dist_km']:.1f} 公里，勝率聯盟第 {top['rk_win']:.0f} 名）；"
                         f"最多和最少只差 {cur['dist_km'].max() - cur['dist_km'].min():.1f} 公里。")
            insight(lines, where=slot1, label="發現")

            st.divider()
            # ===== 3-2 隊上誰跑最多 =====
            slot4 = section(f"3-2　{tr_season} 隊上誰跑最多？", "每 36 分鐘跑動＝把上場時間換算成同樣 36 分鐘，替補和先發才能公平比較", level=2)
            champs_, others_ = split_teams([a for a in cur["abbreviation"].dropna().unique()], tr_season, tr_season)
            others_ = sorted(others_)
            tr_team = team_picker_one(champs_, others_, "tr_team", "當季冠軍", "其他球隊")
            P = load_tracking("player")
            if P.empty:
                st.info("尚未載入資料，請執行 python load_extra.py --only tracking")
            else:
                P = P[(P["season"] == tr_season) & (P["season_type"] == st_code)].copy()
                tid = cur.loc[cur["abbreviation"] == tr_team, "id"]
                P["team_id"] = pd.to_numeric(P["team_id"], errors="coerce")
                P = P[P["team_id"].isin(tid)] if len(tid) else P.iloc[0:0]
                for c_ in ["gp", "min", "dist_miles", "avg_speed"]:
                    P[c_] = pd.to_numeric(P[c_], errors="coerce")
                P = P[(P["gp"] >= 5) & (P["min"] > 0)]
                if P.empty:
                    st.info("這隊這季沒有球員跑動數據（出賽至少 5 場）。")
                else:
                    P["km"] = P["dist_miles"] * KM
                    P["km36"] = P["km"] / P["min"] * 36
                    P = P.sort_values("km", ascending=False).head(10)
                    nice_table(pd.DataFrame({
                        "球員": P["name"], "出賽": P["gp"].map(lambda v: f"{v:.0f}"),
                        "場均分鐘": P["min"].map(lambda v: f"{v:.1f}"), "每場公里": P["km"].map(lambda v: f"{v:.2f}"),
                        "每 36 分鐘公里": P["km36"].map(lambda v: f"{v:.2f}"),
                        "平均速度": (P["avg_speed"] * KM).map(lambda v: f"{v:.2f}"),
                        "_b": P["km"] / P["km"].max()}),
                        num_cols=("出賽", "場均分鐘", "每場公里", "每 36 分鐘公里", "平均速度"), bars={"每場公里": "_b"})
                    t1, t36 = P.iloc[0], P.sort_values("km36", ascending=False).iloc[0]
                    insight(where=slot4, to_summary=False, lines=[
                        f"{team_label(tr_team)} 每場跑最多的是 <b>{t1['name']}</b>（{t1['km']:.2f} 公里）；"
                        f"換算每 36 分鐘最多的是 <b>{t36['name']}</b>（{t36['km36']:.2f} 公里）。"])


# ---------- 賽程與休息：背靠背會不會輸比較多？ ----------
REST_CATS = ["背靠背", "休息 1 天", "休息 2 天", "休息 3 天以上"]


def rest_cat(n):
    return REST_CATS[min(int(n), 3)]


def prep_rest(d):
    """同一隊同一季、和前一場差幾天 − 1 ＝休息天數（0 ＝背靠背）"""
    d = d[d["season_type"] == "Regular Season"].dropna(subset=["game_date"]).sort_values(["team_id", "season", "game_date"]).copy()
    gap = d.groupby(["team_id", "season"])["game_date"].diff().dt.days
    d["rest_days"] = gap - 1
    d = d.dropna(subset=["rest_days"])
    d = d[d["rest_days"] >= 0]
    d["cat"] = d["rest_days"].map(rest_cat)
    return d


TERMS.update({
    "背靠背": ("連續兩天都有比賽；這頁看的是第二天那一場", "和前一場只差 1 天＝休息 0 天"),
    "休息天數": ("兩場比賽中間空了幾天；10/1 打、10/2 又打是休息 0 天（背靠背），10/1 打、10/3 打是休息 1 天", "和前一場相差的天數 − 1"),
    "百分點": ("兩個百分比直接相減的單位；勝率 60% → 55% 是少 5 個百分點（不是少 5%）", "百分比 − 百分比"),
})


if PAGE == "賽程與休息":
    hypothesis("背靠背（連兩天出賽）的第二場，球隊會不會比較常輸？冠軍是不是比較不怕累？",
               "所有球隊在背靠背第二場的勝率，都比休息 1 天以上低；但奪冠那季的冠軍，背靠背勝率掉得比其他球隊少。")
    TG = team_games_with_abbr()
    if TG.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球隊逐場比賽還沒有寫進資料庫）")
    else:
        R = prep_rest(TG)
        n_teams = R["abbreviation"].nunique()
        st.caption(f"目前用資料庫已載入比賽的 {n_teams} 隊、{R['season'].nunique()} 季例行賽計算（每天自動增加 2 隊）。")

        # ===== 1. 背靠背掉多少？（1105-1：直接畫「掉多少」，加「其他強隊」對照）=====
        R["season_win"] = R.groupby(["team_id", "season"])["win"].transform("mean")
        R["grp"] = "其他球隊"
        R.loc[(~R["champion"]) & (R["season_win"] >= 0.6), "grp"] = "其他強隊"
        R.loc[R["champion"], "grp"] = "冠軍"
        slot1 = section("1　背靠背的第二場，勝率掉多少？",
                        "一列一組：冠軍、其他強隊（整季勝率六成以上、沒奪冠）、其他球隊；長條＝有休息的勝率 − 背靠背的勝率，越長＝越怕累")
        view1 = seg("看哪一種", ["看掉多少", "看勝率"], key="rest_view")
        rows1 = []
        for g_ in ["冠軍", "其他強隊", "其他球隊"]:
            x_ = R[R["grp"] == g_]
            b_, r_ = x_[x_["rest_days"] == 0], x_[x_["rest_days"] >= 1]
            if len(b_) and len(r_):
                rows1.append({"grp": g_, "b2b": b_["win"].mean(), "rest": r_["win"].mean(), "n_b": len(b_),
                              "n_t": x_[["team_id", "season"]].drop_duplicates().shape[0]})
        D1 = pd.DataFrame(rows1)
        lines, check = [], None
        if D1.empty:
            st.info("背靠背的比賽還不夠，無法計算。")
        else:
            D1["drop"] = (D1["rest"] - D1["b2b"]) * 100
            if view1 == "看掉多少":
                labs1 = [f"{g_}（{t_} 個隊季、{n_} 場背靠背）" for g_, t_, n_ in zip(D1["grp"], D1["n_t"], D1["n_b"])]
                fig = go.Figure(go.Bar(x=D1["drop"], y=labs1, orientation="h",
                                       marker_color=[{"冠軍": ACCENT, "其他強隊": "#8f889f"}.get(g_, "#c9c3d6") for g_ in D1["grp"]],
                                       text=[f"{v:+.1f} 個百分點" for v in D1["drop"]], textposition="outside",
                                       hovertemplate="%{y}<br>有休息 − 背靠背：%{x:+.1f} 個百分點<extra></extra>"))
                rounded(fig)
                fig.add_vline(x=0, line_color=MUTED, line_width=1)
                fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
                fig.update_xaxes(title="有休息的勝率 − 背靠背的勝率（百分點）")
                st.plotly_chart(style(fig, 260), width="stretch", config={"displayModeBar": False})
            else:
                g = R.groupby(["cat", "grp"]).agg(win=("win", "mean"), n=("win", "size")).reset_index()
                fig = go.Figure()
                for grp_, colr in [("其他球隊", "#c9c3d6"), ("其他強隊", "#8f889f"), ("冠軍", ACCENT)]:
                    sub = g[g["grp"] == grp_].set_index("cat").reindex(REST_CATS)
                    fig.add_trace(go.Bar(x=REST_CATS, y=sub["win"], name=grp_, marker_color=colr,
                                         text=[f"{v:.0%}" if pd.notna(v) else "" for v in sub["win"]], textposition="outside",
                                         customdata=sub["n"].fillna(0).astype(int),
                                         hovertemplate=grp_ + "<br>%{x}：勝率 %{y:.1%}（%{customdata} 場）<extra></extra>"))
                rounded(fig)
                fig.add_hline(y=0.5, line=dict(color=MUTED, dash="dot", width=1))
                fig.update_xaxes(type="category")
                fig.update_yaxes(title="勝率", tickformat=".0%", range=[0, 1])
                fig.update_layout(barmode="group")
                st.plotly_chart(style(fig, 380), width="stretch")
            dd = D1.set_index("grp")["drop"]
            if "冠軍" in dd:
                lines.append(f"<b>冠軍背靠背的第二場，勝率比有休息時{'低' if dd['冠軍'] >= 0 else '高'} {abs(dd['冠軍']):.1f} 個百分點。</b>")
            lines.append("其他組：" + "、".join(f"{g_} {dd[g_]:+.1f}" for g_ in ["其他強隊", "其他球隊"] if g_ in dd) + " 個百分點。")
            lines.append("讀法：冠軍本來就比較會贏，所以不能直接比勝率高低；要比的是「從有休息到背靠背，掉了多少」。"
                         "冠軍要和其他強隊比才公平，因為弱隊勝率本來就低、能掉的空間比較小。")
            if "冠軍" in dd and "其他強隊" in dd:
                all_drop = (R[R["rest_days"] >= 1]["win"].mean() - R[R["rest_days"] == 0]["win"].mean()) * 100
                check = (("前段成立" if all_drop >= 2 else "前段不成立") + f"：所有球隊背靠背勝率低 {all_drop:.1f} 個百分點；"
                         + ("後段成立" if dd["冠軍"] < dd["其他強隊"] else "後段不成立")
                         + f"：冠軍掉 {dd['冠軍']:+.1f}、其他強隊掉 {dd['其他強隊']:+.1f} 個百分點。")
        insight(lines, where=slot1, label="發現", check=check)
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["背靠背", "休息天數", "其他強隊", "百分點"],
                       first_note="這頁只知道<b>自己</b>休息幾天，不知道對手是不是也在背靠背。30 隊都已載入，之後可以補上「兩隊都背靠背」的比較。")

        # ===== 2. 每一位冠軍：背靠背 vs 有休息 =====
        st.divider()
        slot2 = section("2　每一位冠軍：背靠背 vs 有休息", "灰點＝休息 1 天以上的勝率，彩色點＝背靠背的勝率；括號是背靠背場數")
        C = R[R["champion"]]
        if C.empty:
            st.info("資料庫裡還沒有冠軍球季的逐場比賽。")
        else:
            rows = []
            for (s_, a_), gg in C.groupby(["season", "abbreviation"]):
                b2b = gg[gg["rest_days"] == 0]
                rows.append({"season": s_, "abbr": a_, "b2b": b2b["win"].mean() if len(b2b) else float("nan"),
                             "n": len(b2b), "rest": gg[gg["rest_days"] >= 1]["win"].mean()})
            D = pd.DataFrame(rows).sort_values("season")
            labels = [f"{s_} {team_label(a_)}（{n}）" for s_, a_, n in zip(D["season"], D["abbr"], D["n"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, D.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["rest"], r_["b2b"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d6d2df", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=D["rest"], y=labels, mode="markers", name="有休息",
                                     marker=dict(size=12, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>有休息：%{x:.1%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=D["b2b"], y=labels, mode="markers", name="背靠背",
                                     marker=dict(size=13, color=[TEAM_COLORS.get(a, ACCENT) for a in D["abbr"]],
                                                 line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>背靠背：%{x:.1%}<extra></extra>"))
            fig.update_xaxes(title="勝率", tickformat=".0%")
            fig.update_yaxes(autorange="reversed", showgrid=False, type="category")
            st.plotly_chart(style(fig, 90 + 30 * len(D)), width="stretch")
            worse = int((D["b2b"] < D["rest"]).sum())
            insight(where=slot2, label="發現", lines=[
                f"{len(D)} 個冠軍球季中，有 {worse} 個背靠背的勝率比有休息時低（彩色點在灰點左邊）。",
                f"冠軍每季平均 {D['n'].mean():.0f} 場背靠背；場數少，單一球季的差距要保守解讀。",
            ])

        # ===== 3. 聯盟賽程：背靠背一年比一年少嗎？ =====
        st.divider()
        slot3 = section("3　背景：背靠背一年比一年少",
                        "為什麼要看：背靠背越少，「累不累」對跨年代比較的影響越小，所以老球季的差距比較有意義；"
                        "每季平均每隊幾場背靠背，縮短的球季（2011-12、2019-20、2020-21）場數本來就不同")
        per = (R.assign(b=R["rest_days"] == 0).groupby(["season", "abbreviation"])["b"].sum()
               .groupby("season").mean())
        per = per[per.index.isin(sorted(R["season"].unique()))]
        fig = go.Figure(go.Scatter(x=per.index, y=per.values, mode="lines+markers", line=dict(color=ACCENT, width=2.4),
                                   marker=dict(size=7, color=ACCENT, line=dict(width=1.5, color=SURFACE)),
                                   hovertemplate="%{x}：平均每隊 %{y:.1f} 場背靠背<extra></extra>"))
        fig.update_xaxes(type="category")
        fig.update_yaxes(title="平均每隊背靠背場數", rangemode="tozero")
        st.plotly_chart(style(fig, 320), width="stretch")
        if len(per) > 1:
            insight(where=slot3, label="發現", lines=[
                f"平均每隊背靠背從 {per.index[0]} 的 {per.iloc[0]:.1f} 場，變成 {per.index[-1]} 的 {per.iloc[-1]:.1f} 場"
                + ("（最新一季還沒打完，場數會再增加）。" if per.index[-1] == ALL_SEASONS[-1] else "。"),
                "背靠背越少，「累不累」對跨年代比較的影響就越小。"])
        st.button("客場常常也是背靠背 → 看「主場與客場」", key="rest_to_home", on_click=goto, args=("主場與客場",))


# ---------- 主場與客場：冠軍的主場優勢比較大嗎？ ----------
NO_CROWD = {"2019-20": "復賽在泡泡園區，沒有真正的主場", "2020-21": "多數場館限制或不開放觀眾"}


def home_away(d):
    """每隊每季：主場勝率、客場勝率、主場優勢（百分點）"""
    g = d.groupby(["season", "abbreviation", "is_home"])["win"].agg(["mean", "size"]).unstack("is_home")
    out = pd.DataFrame({"home": g[("mean", True)], "away": g[("mean", False)],
                        "n_home": g[("size", True)], "n_away": g[("size", False)]}).reset_index()
    out["adv"] = (out["home"] - out["away"]) * 100
    out["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(out["season"], out["abbreviation"])]
    return out.dropna(subset=["home", "away"])


TERMS.update({
    "頭號球星": ("這一季例行賽場均得分隊內第 1 名（出賽至少 40 場）", "依例行賽場均得分排名"),
    "季末輪休": ("已經確定季後賽名次的球隊，最後幾場讓主力休息；季末勝率下滑不一定是「打不好」", "例行賽最後 10 場左右"),
    "主場優勢": ("主場勝率 − 客場勝率；+10 代表在主場比在客場多贏一成", "主場勝率 − 客場勝率（百分點）"),
    "天花板": ("勝率很高時（例如主場已經贏 85%），主場能再多贏的空間很小，主場優勢自然比較小；所以冠軍要和其他強隊比", "主場勝率接近 100% 時"),
    "泡泡園區／限制觀眾": ("2019-20 復賽在奧蘭多泡泡園區打，沒有真正的主場；2020-21 多數場館限制觀眾，所以這兩季要分開看", "第 2 節淡紫色的兩季"),
})


if PAGE == "主場與客場":
    hypothesis("冠軍是不是特別靠主場？主場優勢（主場勝率 − 客場勝率）有沒有比其他球隊大？",
               "冠軍強在「客場也能贏」：奪冠季的主場優勢比其他球隊季小；而且全聯盟的主場優勢一年比一年小。")
    TG = team_games_with_abbr()
    if TG.empty or "is_home" not in TG:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球隊逐場比賽還沒有寫進資料庫）")
    else:
        TG = TG.dropna(subset=["is_home"]).copy()
        TG["is_home"] = TG["is_home"].astype(bool)
        REG = TG[TG["season_type"] == "Regular Season"]
        HA = home_away(REG)
        st.caption(f"目前用資料庫已載入比賽的 {HA['abbreviation'].nunique()} 隊、{HA['season'].nunique()} 季計算（每天自動增加 2 隊）。"
                   "對照組是同一批球隊的其他球季。")

        # ===== 1. 冠軍 vs 其他強隊 vs 其他球隊（1106-1）=====
        sw_ = REG.groupby(["season", "abbreviation"])["win"].mean().rename("season_win").reset_index()
        HA = HA.merge(sw_, on=["season", "abbreviation"], how="left")
        HA["grp"] = "其他球隊"
        HA.loc[(~HA["champion"]) & (HA["season_win"] >= 0.6), "grp"] = "其他強隊"
        HA.loc[HA["champion"], "grp"] = "冠軍"
        slot1 = section("1　冠軍的主場優勢比較大嗎？",
                        "主場優勢＝主場勝率 − 客場勝率；冠軍要和其他強隊（勝率六成以上、沒奪冠）比才公平，可以切換看每一隊一季的散點圖")
        view_ = seg("看哪一種", ["看各組平均", "看每一隊一季"], key="home_view")
        G1 = HA.groupby("grp").agg(adv=("adv", "mean"), home=("home", "mean"), n=("adv", "size")).reindex(["冠軍", "其他強隊", "其他球隊"]).dropna()
        if view_ == "看各組平均":
            labs_ = [f"{g_}（{int(r_.n)} 個隊季，主場勝率 {r_.home:.0%}）" for g_, r_ in G1.iterrows()]
            fig = go.Figure(go.Bar(x=G1["adv"], y=labs_, orientation="h",
                                   marker_color=[{"冠軍": ACCENT, "其他強隊": "#8f889f"}.get(g_, "#c9c3d6") for g_ in G1.index],
                                   text=[f"{v:+.1f} 個百分點" for v in G1["adv"]], textposition="outside",
                                   hovertemplate="%{y}<br>主場優勢 %{x:+.1f} 個百分點<extra></extra>"))
            rounded(fig)
            fig.add_vline(x=0, line_color=MUTED, line_width=1)
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="主場勝率 − 客場勝率（百分點）")
            st.plotly_chart(style(fig, 250), width="stretch", config={"displayModeBar": False})
        else:
            fig = go.Figure()
            o = HA[~HA["champion"]]
            fig.add_trace(go.Scatter(x=o["away"], y=o["home"], mode="markers", name="其他球隊季",
                                     marker=dict(size=7, color="#c9c3d6", opacity=0.8, line=dict(width=0.5, color=SURFACE)),
                                     text=[f"{s_} {team_label(a_)}" for s_, a_ in zip(o["season"], o["abbreviation"])],
                                     hovertemplate="%{text}<br>客場 %{x:.1%}　主場 %{y:.1%}<extra></extra>"))
            c = HA[HA["champion"]]
            fig.add_trace(go.Scatter(x=c["away"], y=c["home"], mode="markers+text", name="冠軍",
                                     text=[f"{s_[2:4]}{s_[5:]} {a_}" for s_, a_ in zip(c["season"], c["abbreviation"])],
                                     textposition="top center", textfont=dict(size=10, color=INK_2),
                                     marker=dict(symbol="star", size=15, color=ACCENT, line=dict(width=1, color=SURFACE)),
                                     hovertemplate="★ %{text}<br>客場 %{x:.1%}　主場 %{y:.1%}<extra></extra>"))
            fig.add_shape(type="line", x0=0, y0=0, x1=1, y1=1, line=dict(color=MUTED, dash="dot", width=1))
            fig.update_xaxes(title="客場勝率", tickformat=".0%", range=[0, 1])
            fig.update_yaxes(title="主場勝率", tickformat=".0%", range=[0, 1])
            st.plotly_chart(style(fig, 460), width="stretch")
        ga = G1["adv"]
        lines, chk_ = [], None
        if "冠軍" in ga:
            lines.append(f"<b>冠軍的主場勝率平均比客場高 {ga['冠軍']:.1f} 個百分點</b>（{int(G1.loc['冠軍', 'n'])} 個冠軍球季）。")
            lines.append("其他組：" + "、".join(f"{g_} {ga[g_]:+.1f}" for g_ in ["其他強隊", "其他球隊"] if g_ in ga) + " 個百分點。")
            c_ = HA[HA["champion"]]
            lines.append(f"冠軍的客場勝率平均 {c_['away'].mean():.0%}，主場 {c_['home'].mean():.0%}。")
            lines.append("讀法：冠軍主場常常已經贏八成以上，主場勝率「沒有空間再高」，主場優勢自然比較小（天花板）；"
                         "所以要和同樣強的其他強隊比，不是和所有球隊比。")
            if "其他強隊" in ga:
                chk_ = ("前段成立" if ga["冠軍"] < ga["其他強隊"] - 1 else "前段不成立") + \
                       f"：冠軍 {ga['冠軍']:+.1f}、其他強隊 {ga['其他強隊']:+.1f} 個百分點（要小 1 個百分點以上才算）。"
        insight(lines, where=slot1, label="發現", check=chk_)
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["主場優勢", "百分點", "其他強隊", "天花板", "泡泡園區／限制觀眾"],
                       first_note="這頁<b>只比勝率，不比得分差</b>（team_games 沒有每場得分）。")

        # ===== 2. 主場優勢一年比一年小嗎？ =====
        st.divider()
        slot2 = section("2　主場優勢一年比一年小嗎？", "每季所有已載入球隊的平均主場優勢（主場勝率 − 客場勝率）；淡紫色直條是沒有正常觀眾的球季")
        per = HA.groupby("season")["adv"].mean()
        seas = list(per.index)
        fig = go.Figure()
        for s_ in NO_CROWD:
            if s_ in seas:
                i = seas.index(s_)
                fig.add_vrect(x0=i - 0.5, x1=i + 0.5, fillcolor="rgba(167,139,250,0.12)", line_width=0, layer="below")
        fig.add_trace(go.Scatter(x=seas, y=per.values, mode="lines+markers", line=dict(color=ACCENT, width=2.4),
                                 marker=dict(size=7, color=ACCENT, line=dict(width=1.5, color=SURFACE)),
                                 customdata=[NO_CROWD.get(s_, "") for s_ in seas],
                                 hovertemplate="%{x}：主場優勢 %{y:+.1f} 個百分點<br>%{customdata}<extra></extra>"))
        fig.add_hline(y=0, line=dict(color=INK_2, width=1))
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=seas)
        fig.update_yaxes(title="主場勝率 − 客場勝率（百分點）")
        st.plotly_chart(style(fig, 340), width="stretch")
        if len(per) >= 6:
            normal = per[~per.index.isin(list(NO_CROWD))]
            early, late = normal.iloc[:5].mean(), normal.iloc[-5:].mean()
            nc = per[per.index.isin(list(NO_CROWD))]
            lines = [f"前 5 季平均主場優勢 {early:+.1f} 個百分點，最近 5 季 {late:+.1f}（不算沒有觀眾的球季）。"]
            if len(nc):
                lines.append("沒有正常觀眾的球季：" + "、".join(f"{s_} {v:+.1f}" for s_, v in nc.items()) + "。")
            insight(lines, where=slot2, label="發現",
                    check=("成立：主場優勢變小了。" if late < early - 1 else
                           "不成立：前後差不到 1 個百分點，主場優勢沒有明顯變小。" if late <= early + 1 else
                           "不成立：主場優勢反而變大了。"))

        # ===== 3. 冠軍在季後賽的客場 =====
        st.divider()
        slot3 = section("3　冠軍在季後賽的主場與客場",
                        "季後賽的主場優勢更重要（第 1、2、5、7 場在戰績好的一方主場），冠軍客場也能贏，就是假設說的「不靠主場」；"
                        "表格是奪冠那季的季後賽主場、客場各打幾勝幾敗，最下面一列是所有季後賽球隊的平均")
        PO = TG[(TG["season_type"] == "Playoffs") & TG["champion"]]
        if PO.empty:
            st.info("資料庫裡還沒有冠軍的季後賽逐場比賽。")
        else:
            rows = []
            for (s_, a_), gg in PO.groupby(["season", "abbreviation"]):
                h, w_ = gg[gg["is_home"]], gg[~gg["is_home"]]
                rows.append({"球季": s_, "冠軍": team_label(a_), "_key": a_,
                             "主場": f"{int(h['win'].sum())} 勝 {len(h) - int(h['win'].sum())} 敗",
                             "客場": f"{int(w_['win'].sum())} 勝 {len(w_) - int(w_['win'].sum())} 敗",
                             "主場勝率": f"{h['win'].mean():.0%}" if len(h) else "-",
                             "客場勝率": f"{w_['win'].mean():.0%}" if len(w_) else "-",
                             "_aw": w_["win"].mean() if len(w_) else float("nan")})
            PT = pd.DataFrame(rows).sort_values("球季")
            ALLPO = TG[TG["season_type"] == "Playoffs"]
            all_h = ALLPO[ALLPO["is_home"]]["win"].mean()
            all_a = ALLPO[~ALLPO["is_home"]]["win"].mean()
            avg_row = pd.DataFrame([{"球季": "", "冠軍": '<span style="color:#8f889f">所有季後賽球隊平均</span>', "_key": "",
                                     "主場": "", "客場": "", "主場勝率": f'<span style="color:#8f889f">{all_h:.0%}</span>',
                                     "客場勝率": f'<span style="color:#8f889f">{all_a:.0%}</span>', "_aw": float("nan")}])
            nice_table(pd.concat([PT, avg_row], ignore_index=True), num_cols=("主場", "客場", "主場勝率", "客場勝率"), dot_col="冠軍", colors=TEAM_COLORS,
                       bars={"客場勝率": "_aw"})
            tot_h = PO[PO["is_home"]]["win"].mean()
            tot_a = PO[~PO["is_home"]]["win"].mean()
            best = PT.loc[PT["_aw"].idxmax()] if PT["_aw"].notna().any() else None
            insight(where=slot3, label="發現", lines=[
                f"合計 {len(PT)} 位冠軍在季後賽：主場勝率 {tot_h:.0%}、客場勝率 {tot_a:.0%}。",
                (f"客場最強的是 {best['球季']} {best['冠軍']}（客場 {best['客場']}）。" if best is not None else ""),
                f"有 {int((PT['_aw'] >= 0.5).sum())} 位冠軍的季後賽客場勝率在五成以上。",
                f"所有季後賽球隊的客場勝率平均 {all_a:.0%}，冠軍比平均{'高' if tot_a >= all_a else '低'} {abs(tot_a - all_a) * 100:.0f} 個百分點。",
            ])


# ---------- 例行賽與季後賽：球星進季後賽，表現上升還是下滑？（2026-11-03）----------
RP_METRICS = {   # 顯示名稱 → (欄位, 單位, 格式, 越高越好?)
    "真實命中率": ("ts", "%", ".1%", True),
    "場均得分": ("ppg", "分", ".1f", True),
    "場均上場分鐘": ("mpg", "分鐘", ".1f", True),
    "每 36 分鐘得分": ("p36", "分", ".1f", True),
}


def playoff_stars(players, n_star=3, min_reg=40, min_po=4):
    """每隊每季例行賽場均得分前 n_star 名（出賽至少 min_reg 場）＝球星；配上他同一隊同一季的季後賽數據
    回傳一列一位球星：例行賽與季後賽的場均得分、上場分鐘、真實命中率、每 36 分鐘得分，以及兩者的差"""
    d = players[players["season_type"].isin(["Regular Season", "Playoffs"])].copy()
    for c in ["gp", "min", "pts", "fga", "fta"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["gp"] > 0]
    d["ppg"] = d["pts"] / d["gp"]
    d["mpg"] = d["min"] / d["gp"]
    d["ts"] = d["pts"] / (2 * (d["fga"] + 0.44 * d["fta"])).where(lambda x: x > 0)
    d["p36"] = d["pts"] / d["min"].where(d["min"] > 0) * 36
    keys = ["season", "team_id", "abbreviation", "player_id", "player_name"]
    reg = d[(d["season_type"] == "Regular Season") & (d["gp"] >= min_reg)].copy()
    reg["rk"] = reg.groupby(["season", "team_id"])["ppg"].rank(ascending=False, method="first")
    reg = reg[reg["rk"] <= n_star]
    po = d[(d["season_type"] == "Playoffs") & (d["gp"] >= min_po)]
    cols = ["gp", "ppg", "mpg", "ts", "p36"]
    m = reg[keys + ["rk"] + cols].merge(po[keys + cols], on=keys, suffixes=("_r", "_p"))
    for c in ["ppg", "mpg", "ts", "p36"]:
        m[f"d_{c}"] = m[f"{c}_p"] - m[f"{c}_r"]
    m["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(m["season"], m["abbreviation"])]
    return m.sort_values(["season", "abbreviation", "rk"])


def fmt_d(v, f):
    """差值的格式：百分比用「百分點」，其他直接帶正負號"""
    if pd.isna(v):
        return "-"
    return f"{v * 100:+.1f} 百分點" if f.endswith("%") else f"{v:+.1f}"


if PAGE == "例行賽與季後賽":
    hypothesis("球星進了季後賽，表現是上升還是下滑？冠軍的球星是不是特別「越打越好」？",
               "季後賽對手比較強，所以大多數球星的真實命中率會下降；但冠軍的頭號球星下降得比其他季後賽球隊的球星少，"
               "而且場均得分會上升（因為上場時間變多）。")
    if player_raw.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球員逐場數據還沒有寫進資料庫）")
    else:
        RP = playoff_stars(player_raw)
        n_teams = RP["abbreviation"].nunique()
        st.caption(f"目前用資料庫已載入球員逐場數據的 {n_teams} 隊計算（每天自動增加 2 隊）；"
                   "球星＝當季例行賽場均得分隊內前 3 名、出賽至少 40 場，而且季後賽至少打 4 場。")
        if RP.empty or not RP["champion"].any():
            st.info("資料不足：還沒有同時有例行賽和季後賽數據的冠軍球星。")
        else:
            rp_m = seg("看哪一項", list(RP_METRICS), "rp_metric")
            col, unit, f_, _ = RP_METRICS[rp_m]

            # ===== 1. 冠軍的球星 vs 其他季後賽球隊的球星（1109-1：先回答假設）=====
            slot2 = section("1　冠軍的球星 vs 其他季後賽球隊的球星：平均變化多少？",
                            "長條＝季後賽 − 例行賽的平均變化（0 以上＝季後賽比較好）；分頭號球星、第 2～3 號球星兩組；"
                            "對照組是資料庫已載入、也打進季後賽但沒有奪冠的球隊")
            RP["grp"] = RP["champion"].map({True: "冠軍", False: "其他季後賽球隊"})
            RP["star"] = (RP["rk"] == 1).map({True: "頭號球星", False: "第 2～3 號球星"})
            G = RP.dropna(subset=[f"d_{col}"]).groupby(["star", "grp"])[f"d_{col}"].agg(["mean", "size"]).reset_index()
            fig = go.Figure()
            for grp, c_ in [("其他季後賽球隊", "#c9c3d6"), ("冠軍", ACCENT)]:
                g_ = G[G["grp"] == grp].set_index("star").reindex(["頭號球星", "第 2～3 號球星"])
                yv = g_["mean"] * (100 if f_.endswith("%") else 1)
                fig.add_trace(go.Bar(x=list(g_.index), y=yv, name=grp, marker_color=c_,
                                     text=[("-" if pd.isna(n) else f"{int(n)} 人") for n in g_["size"]],
                                     textposition="outside", cliponaxis=False, textfont=dict(color=INK_2),
                                     hovertemplate="%{x}（" + grp + "）<br>平均變化 %{y:+.1f}" +
                                                   (" 百分點" if f_.endswith("%") else f" {unit}") + "<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1))
            rounded(fig)
            fig.update_layout(barmode="group", bargap=0.35, legend=dict(orientation="h", y=1.08, x=0))
            fig.update_yaxes(title="季後賽 − 例行賽（" + ("百分點" if f_.endswith("%") else unit) + "）",
                             zeroline=False, tickformat="+.1f")
            st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})

            def gmean(star, grp):
                x = G[(G["star"] == star) & (G["grp"] == grp)]
                return (x["mean"].iloc[0], int(x["size"].iloc[0])) if len(x) else (float("nan"), 0)
            (c_m, c_n), (o_m, o_n) = gmean("頭號球星", "冠軍"), gmean("頭號球星", "其他季後賽球隊")
            lines = [f"頭號球星的{rp_m}，冠軍平均 {fmt_d(c_m, f_)}（{c_n} 人），"
                     f"其他季後賽球隊 {fmt_d(o_m, f_)}（{o_n} 人）。"]
            if o_n < 10:
                lines.append(f"對照組只有 {o_n} 人（資料庫還沒載入全部 30 隊的球員數據），先不要下結論；約 11/8 補完後會更可靠。")
            check = None
            ts_c = RP[RP["champion"] & (RP["rk"] == 1)]["d_ts"].mean()
            ts_o = RP[~RP["champion"] & (RP["rk"] == 1)]["d_ts"].mean()
            pp_c = RP[RP["champion"] & (RP["rk"] == 1)]["d_ppg"].mean()
            ts_all = RP["d_ts"].mean()
            if pd.notna(ts_c) and pd.notna(ts_o) and pd.notna(pp_c):
                check = (("第一句成立" if ts_all < 0 else "第一句不成立") + f"：所有球星的真實命中率平均 {fmt_d(ts_all, '.1%')}；"
                         + ("第二句成立" if ts_c > ts_o else "第二句不成立") + f"：冠軍頭號球星 {fmt_d(ts_c, '.1%')}、"
                         f"其他 {fmt_d(ts_o, '.1%')}；" + ("第三句成立" if pp_c > 0 else "第三句不成立")
                         + f"：冠軍頭號球星場均得分 {pp_c:+.1f} 分")
            # 1109-2：得分增加是靠上場時間，還是每分鐘更會得分
            CT = RP[RP["champion"] & (RP["rk"] == 1)].dropna(subset=["ppg_r", "ppg_p", "mpg_r", "mpg_p"])
            CT = CT[(CT["mpg_r"] > 0) & (CT["mpg_p"] > 0)]
            if len(CT):
                d_pp = (CT["ppg_p"] - CT["ppg_r"]).mean()
                d_mp = (CT["mpg_p"] - CT["mpg_r"]).mean()
                d_36 = (CT["ppg_p"] / CT["mpg_p"] * 36 - CT["ppg_r"] / CT["mpg_r"] * 36).mean()
                why = ("得分增加主要來自上場時間變長（每分鐘並沒有更會得分）" if d_pp > 0 and d_36 <= 0.3 else
                       "每分鐘也更會得分，不只是打得比較久" if d_pp > 0 else "場均得分沒有增加")
                lines.append(f"<b>拆開來看：</b>冠軍頭號球星場均得分 {d_pp:+.1f} 分；上場時間 {d_mp:+.1f} 分鐘；"
                             f"每 36 分鐘得分 {d_36:+.1f} 分 → {why}。")
                if check:
                    check += ("；第四句（括號裡的原因）" + ("成立" if d_mp > 0 and d_36 <= 0.3 else "不成立")
                              + f"：上場時間 {d_mp:+.1f} 分鐘、每 36 分鐘得分 {d_36:+.1f} 分。")
            elif check:
                check += "。"
            insight(lines, where=slot2, check=check)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["球星（本頁）", "頭號球星", "百分點", "真實命中率", "每 36 分鐘得分", "季後賽 − 例行賽"],
                           first_note="季後賽的對手都是強隊、防守也更專心，所以命中率「本來就會」下降一點；"
                                      "要看的是冠軍的球星有沒有掉得比別人少。")

            # ===== 2. 每一位冠軍的頭號球星：例行賽 → 季後賽（細節）=====
            st.divider()
            C1 = RP[RP["champion"] & (RP["rk"] == 1)].sort_values("season").dropna(subset=[f"{col}_r", f"{col}_p"])
            slot1 = section(f"2　每一位冠軍的頭號球星：例行賽 → 季後賽（{rp_m}）",
                            "灰點＝例行賽、彩色點＝季後賽；彩色點在右邊＝季後賽比較好。頭號球星＝例行賽場均得分隊內第 1")
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}　{p_}" for s_, a_, p_ in zip(C1["season"], C1["abbreviation"], C1["player_name"])]
            fig = go.Figure()
            for lab, (_, r) in zip(labels, C1.iterrows()):
                fig.add_trace(go.Scatter(x=[r[f"{col}_r"], r[f"{col}_p"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C1[f"{col}_r"], y=labels, mode="markers", name="例行賽",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     customdata=C1[["gp_r"]].values,
                                     hovertemplate="%{y}<br>例行賽 %{x:" + f_ + "}（%{customdata[0]:.0f} 場）<extra></extra>"))
            fig.add_trace(go.Scatter(x=C1[f"{col}_p"], y=labels, mode="markers", name="季後賽",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in C1["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     customdata=C1[["gp_p"]].values,
                                     hovertemplate="%{y}<br>季後賽 %{x:" + f_ + "}（%{customdata[0]:.0f} 場）<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title=f"{rp_m}（{unit}）", tickformat=".0%" if f_.endswith("%") else None,
                             showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 40 * len(C1)), width="stretch", config={"displayModeBar": False})
            up = int((C1[f"d_{col}"] > 0).sum())
            lines = [f"{len(C1)} 位冠軍頭號球星裡，有 <b>{up}</b> 位的{rp_m}在季後賽比例行賽高"
                     f"（平均變化 {fmt_d(C1[f'd_{col}'].mean(), f_)}）。"]
            if len(C1):
                b_ = C1.loc[C1[f"d_{col}"].idxmax()]
                w_ = C1.loc[C1[f"d_{col}"].idxmin()]
                lines.append(f"<b>進步最多：</b>{b_['season']} {b_['player_name']}（{fmt_d(b_[f'd_{col}'], f_)}）；"
                             f"<b>掉最多：</b>{w_['season']} {w_['player_name']}（{fmt_d(w_[f'd_{col}'], f_)}）。")
            insight(lines, where=slot1)

            # ===== 3. 明細表 =====
            st.divider()
            section("3　冠軍球星明細", "每一位冠軍的前 3 號球星；差＝季後賽 − 例行賽")
            C3 = RP[RP["champion"]].sort_values(["season", "rk"])
            nice_table(pd.DataFrame({
                "球季": C3["season"], "冠軍": [ALL_ZH.get(a, a) for a in C3["abbreviation"]], "_key": C3["abbreviation"],
                "球員": C3["player_name"], "隊內": [f"第 {int(r)}" for r in C3["rk"]],
                "場均得分": [f"{a:.1f} → {b:.1f}" for a, b in zip(C3["ppg_r"], C3["ppg_p"])],
                "上場分鐘": [f"{a:.1f} → {b:.1f}" for a, b in zip(C3["mpg_r"], C3["mpg_p"])],
                "真實命中率": [f"{fmt(a, '.1%')} → {fmt(b, '.1%')}" for a, b in zip(C3["ts_r"], C3["ts_p"])],
                "命中率差": [fmt_d(v, ".1%").replace(" 百分點", "") for v in C3["d_ts"]],
            }), num_cols=("場均得分", "上場分鐘", "真實命中率", "命中率差"), signed_cols=("命中率差",),
                dot_col="冠軍", colors=TEAM_COLORS)


# ---------- 得分穩定度：冠軍球星比較不會爆冷嗎？（2026-11-04 提出，11-05 重做）----------
@st.cache_data(ttl=3600, show_spinner="讀取得分起伏彙總表中…")
def _read_spread():
    """讀 player_scoring_spread_mv（一位球員一隊一季一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("player_scoring_spread_mv", ["team_id", "season", "season_type", "player_id"])


def load_spread():
    try:
        df = _read_spread()
        return df if not df.empty else None
    except Exception as e:
        VIEW_ERRORS["player_scoring_spread_mv"] = f"{type(e).__name__}: {e}"[:300]
        return None


def scoring_spread(sp, players, season_type, n_star=3, min_reg=40, min_po=4):
    """球星（例行賽場均得分隊內前 3、出賽至少 40 場）在指定比賽類型的每場得分起伏
    cv＝標準差 ÷ 場均（起伏）；cv_fit＝同得分水準的平均起伏（直線）；cv_res＝實際 − 同水準，負數＝比較穩定"""
    d = players[players["season_type"] == "Regular Season"].copy()
    for c in ["gp", "pts"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["gp"] >= min_reg]
    d["ppg"] = d["pts"] / d["gp"]
    d["rk"] = d.groupby(["season", "team_id"])["ppg"].rank(ascending=False, method="first")
    stars = d[d["rk"] <= n_star][["season", "team_id", "player_id", "rk"]]
    s = sp.copy()
    for c in ["team_id", "player_id", "gp", "ppg", "sd_pts", "low_games", "high_games", "min_pts", "max_pts"]:
        if c in s.columns:
            s[c] = pd.to_numeric(s[c], errors="coerce")
    for c in ["team_id", "player_id"]:
        stars[c] = pd.to_numeric(stars[c], errors="coerce")
    if "abbreviation" not in s.columns:
        s = s.merge(team_raw[["team_id", "abbreviation"]].drop_duplicates(), on="team_id", how="left")
    s = s[(s["season_type"] == season_type) & (s["gp"] >= (min_reg if season_type == "Regular Season" else min_po))]
    s = s.merge(stars, on=["season", "team_id", "player_id"])
    s = s[s["ppg"] > 0]
    s["cv"] = s["sd_pts"] / s["ppg"]
    s["low_rate"] = s["low_games"] / s["gp"]
    s["high_rate"] = s["high_games"] / s["gp"] if "high_games" in s.columns else float("nan")
    ok = s.dropna(subset=["cv", "ppg"])
    if len(ok) >= 3:
        x, y = ok["ppg"].astype(float), ok["cv"].astype(float)
        b = ((x - x.mean()) * (y - y.mean())).sum() / (((x - x.mean()) ** 2).sum() or 1)
        a = y.mean() - b * x.mean()
    else:
        a, b = float("nan"), 0.0
    s["cv_fit"] = a + b * s["ppg"]
    s["cv_res"] = s["cv"] - s["cv_fit"]
    s["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(s["season"], s["abbreviation"])]
    s.attrs["line"] = (a, b)
    return s


if PAGE == "得分穩定度":
    hypothesis("冠軍的球星是不是比較不會「爆冷」？每場得分的起伏，冠軍和其他球隊的球星差多少？",
               "冠軍的頭號球星得分比較穩定：在同樣的場均得分下，每場得分的起伏比其他球隊的頭號球星小，"
               "「低迷場」（得分不到自己平均的六成）也比較少。")
    SP = load_spread()
    if SP is None:
        st.info("這一頁需要一張預先算好的彙總表（要看每一場的得分才能算起伏，網站一頁一頁讀幾十萬筆太慢）。"
                "請到 Supabase SQL Editor 執行 docs/sql/2026-11-05_得分穩定度.sql，執行後按左側「重新讀取最新資料」。")
        if "player_scoring_spread_mv" in VIEW_ERRORS:
            st.caption(f"錯誤訊息（截圖給助教看）：{VIEW_ERRORS['player_scoring_spread_mv']}")
    else:
        sd_type_zh = seg("比賽類型（整頁）", ["例行賽", "季後賽"], "sd_type")
        S = scoring_spread(SP, player_raw, TYPE_OPTIONS[sd_type_zh])
        st.caption(f"目前用資料庫已載入球員逐場數據的 {S['abbreviation'].nunique()} 隊計算（每天自動增加 2 隊）；"
                   "球星＝當季例行賽場均得分隊內前 3 名、出賽至少 40 場"
                   + ("；季後賽至少打 4 場。" if sd_type_zh == "季後賽" else "。"))
        S1 = S[S["rk"] == 1]
        if S1.empty or not S1["champion"].any():
            st.info("資料不足：還沒有冠軍頭號球星的得分起伏資料。")
        else:
            # ===== 1 冠軍頭號球星 vs 同得分水準 =====
            slot1 = section(f"1　冠軍的頭號球星比同得分水準穩定嗎？（{sd_type_zh}）",
                            "每個點是一位頭號球星的一季：灰點＝其他球隊、彩色星星＝冠軍，虛線＝同得分水準的平均起伏；"
                            "在虛線下面＝比同水準穩定")
            o_, c_ = S1[~S1["champion"]], S1[S1["champion"]]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=o_["ppg"], y=o_["cv"], mode="markers", name="其他球隊的頭號球星",
                                     marker=dict(size=7, color=DIM, opacity=0.8),
                                     customdata=o_[["season", "abbreviation", "player_name"]].values,
                                     hovertemplate="%{customdata[0]} %{customdata[1]} %{customdata[2]}<br>"
                                                   "場均 %{x:.1f} 分｜起伏 %{y:.0%}<extra></extra>"))
            a_, b_ = S.attrs.get("line", (float("nan"), 0))
            xs = [float(S1["ppg"].min()), float(S1["ppg"].max())]
            if pd.notna(a_):
                fig.add_trace(go.Scatter(x=xs, y=[a_ + b_ * v for v in xs], mode="lines", name="同得分水準的平均",
                                         line=dict(color=MUTED, width=1.6, dash="dash"), hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=c_["ppg"], y=c_["cv"], mode="markers+text", name="冠軍的頭號球星",
                                     marker=dict(size=15, symbol="star", line=dict(width=1, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in c_["abbreviation"]]),
                                     text=[f"{s[2:]} {p}" for s, p in zip(c_["season"], c_["player_name"])],
                                     textposition="top center", textfont=dict(size=10.5, color=INK_2),
                                     customdata=c_[["season", "abbreviation", "player_name", "cv_res"]].values,
                                     hovertemplate="★ %{customdata[0]} %{customdata[1]} %{customdata[2]}<br>"
                                                   "場均 %{x:.1f} 分｜起伏 %{y:.0%}（比同水準 %{customdata[3]:+.0%}）<extra></extra>"))
            fig.update_xaxes(title="場均得分")
            fig.update_yaxes(title="每場得分起伏（標準差 ÷ 場均）", tickformat=".0%")
            fig.update_layout(legend=dict(orientation="h", y=1.06, x=0))
            st.plotly_chart(style(fig, 440), width="stretch")
            k1 = int((c_["cv_res"] < 0).sum())
            a1 = k1 > len(c_) / 2
            steady = c_.sort_values("cv_res").iloc[0]
            lines = [f"<b>比同水準穩定：</b>{len(c_)} 位冠軍頭號球星裡，有 {k1} 位在虛線下面"
                     f"（平均比同水準 {c_['cv_res'].mean() * 100:+.1f} 個百分點；其他球隊的頭號球星 {o_['cv_res'].mean() * 100:+.1f}）。",
                     f"最穩定的是 {steady['season']} {steady['player_name']}（起伏 {steady['cv']:.0%}，"
                     f"比同水準 {steady['cv_res'] * 100:+.1f}）。",
                     "讀法：得分越多的人，起伏「自然」越小（場均 30 分差 6 分只是兩成），所以不能直接比高低，"
                     "要看每個點在虛線的上面還是下面。"]
            chk1 = ("前半成立" if a1 else "前半不成立") + f"：{k1} / {len(c_)} 位比同得分水準穩定。"
            insight(lines, where=slot1, check=chk1)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["球星（本頁）", "得分起伏", "同得分水準", "低迷場", "爆發場"],
                           first_note="起伏是用<b>每一場</b>的得分算的，所以只有球員逐場數據已載入的球隊才算得出來；"
                                      "低迷場不知道是不是因為受傷或犯規提早退場。")

            # ===== 2 低迷場：冠軍 vs 其他球隊 =====
            st.divider()
            slot2 = section(f"2　低迷場比較少嗎？（{sd_type_zh}）",
                            "長條＝平均每 100 場有幾場是「低迷場」（得分不到自己平均的六成）；分頭號球星、第 2～3 號球星兩組；"
                            "長條上是人數")
            S["grp"] = S["champion"].map({True: "冠軍", False: "其他球隊"})
            S["star"] = (S["rk"] == 1).map({True: "頭號球星", False: "第 2～3 號球星"})
            G = S.dropna(subset=["low_rate"]).groupby(["star", "grp"])["low_rate"].agg(["mean", "size"]).reset_index()
            fig = go.Figure()
            for grp, colr in [("其他球隊", "#c9c3d6"), ("冠軍", ACCENT)]:
                g_ = G[G["grp"] == grp].set_index("star").reindex(["頭號球星", "第 2～3 號球星"])
                fig.add_trace(go.Bar(x=list(g_.index), y=g_["mean"], name=grp, marker_color=colr,
                                     text=[("-" if pd.isna(v) else f"{v:.0%}（{int(n)} 人）") for v, n in zip(g_["mean"], g_["size"])],
                                     textposition="outside", cliponaxis=False, textfont=dict(color=INK_2),
                                     hovertemplate="%{x}（" + grp + "）<br>低迷場 %{y:.1%}<extra></extra>"))
            rounded(fig)
            fig.update_layout(barmode="group", bargap=0.35, legend=dict(orientation="h", y=1.08, x=0))
            fig.update_yaxes(title="低迷場佔出賽場數", tickformat=".0%", rangemode="tozero")
            st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
            lc = S1[S1["champion"]]["low_rate"].mean()
            lo = S1[~S1["champion"]]["low_rate"].mean()
            lines = [f"頭號球星的低迷場：冠軍平均每 100 場 {lc * 100:.1f} 場，其他球隊 {lo * 100:.1f} 場。"]
            if len(o_) < 30:
                lines.append(f"對照組只有 {len(o_)} 人（還沒載入全部 30 隊），先不要下結論；約 11/8 補完後會更可靠。")
            chk2 = (("後半成立" if lc < lo else "後半不成立") + f"：冠軍頭號球星低迷場 {lc:.1%}、其他 {lo:.1%}。"
                    if pd.notna(lc) and pd.notna(lo) else None)
            insight(lines, where=slot2, check=chk2)

            # ===== 3 明細 =====
            st.divider()
            section("3　冠軍頭號球星明細", "起伏＝標準差 ÷ 場均；比同水準＝起伏 − 同得分水準的平均（負數＝比較穩定）")
            T = c_.sort_values("season")
            nice_table(pd.DataFrame({
                "球季": T["season"], "冠軍": [ALL_ZH.get(a, a) for a in T["abbreviation"]], "_key": T["abbreviation"],
                "球員": T["player_name"], "場數": [f"{v:.0f}" for v in T["gp"]],
                "場均": [f"{v:.1f}" for v in T["ppg"]], "標準差": [f"{v:.1f}" for v in T["sd_pts"]],
                "起伏": [f"{v:.0%}" for v in T["cv"]], "比同水準": [f"{v * 100:+.1f}" for v in T["cv_res"]],
                "低迷場": [f"{v:.0%}" for v in T["low_rate"]],
                "爆發場": [fmt(v, ".0%") for v in T["high_rate"]],
                "單場最低～最高": [f"{fmt(a, '.0f')}～{fmt(b, '.0f')}" for a, b in zip(T.get("min_pts", T["gp"] * float("nan")),
                                                                      T.get("max_pts", T["gp"] * float("nan")))],
            }), num_cols=("場數", "場均", "標準差", "起伏", "比同水準", "低迷場", "爆發場", "單場最低～最高"),
                signed_cols=("比同水準",), dot_col="冠軍", colors=TEAM_COLORS)


# ---------- 月份趨勢：冠軍是不是越打越好？（2026-11-05）----------
MONTH_ORDER = ["10–11 月", "12 月", "1 月", "2 月", "3 月", "4 月起"]


def month_cat(m):
    """把月份併成 6 段：開季的 10、11 月合併；4 月以後（含 2019-20 復賽的 7、8 月）合併"""
    if m in (10, 11):
        return "10–11 月"
    if m in (12, 1, 2, 3):
        return f"{m} 月"
    return "4 月起"


def prep_month(d, strong=0.6):
    """例行賽每一場：月份段、這一季的第幾場（前半季／後半季），以及這一隊這一季的整季勝率、是不是「其他強隊」"""
    d = d[d["season_type"] == "Regular Season"].dropna(subset=["game_date"]).sort_values(["team_id", "season", "game_date"]).copy()
    d["mcat"] = d["game_date"].dt.month.map(month_cat)
    d["n"] = d.groupby(["team_id", "season"]).cumcount() + 1
    d["n_all"] = d.groupby(["team_id", "season"])["n"].transform("max")
    d["half"] = (d["n"] > d["n_all"] / 2).map({False: "前半季", True: "後半季"})
    d["season_win"] = d.groupby(["team_id", "season"])["win"].transform("mean")
    d["grp"] = "其他球隊"
    d.loc[(~d["champion"]) & (d["season_win"] >= strong), "grp"] = "其他強隊"
    d.loc[d["champion"], "grp"] = "冠軍"
    return d[d["season"] != ALL_SEASONS[-1]]     # 本季還沒打完，前後半季比不了，先不列入


if PAGE == "月份趨勢":
    hypothesis("冠軍是不是「越打越好」？開季和季末的勝率差多少？",
               "冠軍的後半季勝率比前半季高（季末衝刺、陣容磨合好了）；同樣強的其他球隊（整季勝率六成以上、沒奪冠）"
               "沒有這種上升，甚至會下滑。")
    TG = team_games_with_abbr()
    if TG.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球隊逐場比賽還沒有寫進資料庫）")
    else:
        MO = prep_month(TG)
        st.caption(f"目前用資料庫已載入比賽的 {MO['abbreviation'].nunique()} 隊、{MO['season'].nunique()} 季例行賽計算"
                   "（每天自動增加 2 隊；本季還沒打完，先不列入）。")
        # ===== 1 每個月的勝率 =====
        slot1 = section("1　每個月的勝率：冠軍 vs 其他強隊",
                        "紫線＝奪冠球季的冠軍、灰線＝其他強隊（整季勝率六成以上、沒奪冠）、虛線＝其他球隊；點旁是勝率")
        g = MO.groupby(["grp", "mcat"]).agg(win=("win", "mean"), n=("win", "size")).reset_index()
        fig = go.Figure()
        for grp, colr, dash, w in [("其他球隊", "#c9c3d6", "dot", 1.8), ("其他強隊", "#8f889f", "solid", 2.4),
                                   ("冠軍", ACCENT, "solid", 3.2)]:
            sub = g[g["grp"] == grp].set_index("mcat").reindex(MONTH_ORDER)
            fig.add_trace(go.Scatter(x=MONTH_ORDER, y=sub["win"], name=grp, mode="lines+markers+text" if grp != "其他球隊" else "lines+markers",
                                     line=dict(color=colr, width=w, dash=dash), marker=dict(size=7, color=colr),
                                     text=[fmt(v, ".0%") for v in sub["win"]], textposition="top center",
                                     textfont=dict(size=10.5, color=INK_2),
                                     customdata=sub["n"].fillna(0).astype(int),
                                     hovertemplate=grp + "<br>%{x}：勝率 %{y:.1%}（%{customdata} 場）<extra></extra>"))
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=MONTH_ORDER)
        fig.update_yaxes(title="勝率", tickformat=".0%")
        fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
        st.plotly_chart(style(fig, 380), width="stretch")
        piv = g.pivot(index="grp", columns="mcat", values="win").reindex(columns=MONTH_ORDER)
        lines, chk1 = [], None
        if "冠軍" in piv.index and pd.notna(piv.loc["冠軍", "4 月起"]) and pd.notna(piv.loc["冠軍", "10–11 月"]):
            cd_ = (piv.loc["冠軍", "4 月起"] - piv.loc["冠軍", "10–11 月"]) * 100
            od_ = ((piv.loc["其他強隊", "4 月起"] - piv.loc["其他強隊", "10–11 月"]) * 100) if "其他強隊" in piv.index else float("nan")
            lines.append(f"<b>冠軍 4 月起的勝率比 10–11 月{'高' if cd_ >= 0 else '低'} {abs(cd_):.1f} 個百分點</b>"
                         + (f"；其他強隊是 {od_:+.1f} 個百分點。" if pd.notna(od_) else "。"))
            chk1 = (("成立" if cd_ > 0 else "不成立") + f"：冠軍季末比開季 {cd_:+.1f} 個百分點"
                    + (f"，其他強隊 {od_:+.1f}" if pd.notna(od_) else "") + "（第 2 節用前後半季再比一次）。")
        if "冠軍" in piv.index:
            cm = piv.loc["冠軍"].dropna()
            lines.append(f"<b>冠軍最強的月份：</b>{cm.idxmax()}（{cm.max():.0%}），最弱是 {cm.idxmin()}（{cm.min():.0%}）。")
        if "其他強隊" in piv.index:
            om = piv.loc["其他強隊"].dropna()
            lines.append(f"其他強隊最強是 {om.idxmax()}（{om.max():.0%}）、最弱是 {om.idxmin()}（{om.min():.0%}）。")
        lines.append("讀法：看紫線是不是越往右越高（越打越好），灰線是不是平的或往下。"
                     "2011-12（停擺，12 月底才開季）、2019-20（3 月停賽、7 月泡泡復賽）、2020-21（12 月底開季）的月份和一般球季不同，"
                     "所以第 2 節改用「這一季的前一半場次 vs 後一半場次」來比，比較公平。")
        insight(lines, where=slot1, check=chk1)
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["季末輪休", "前半季／後半季", "其他強隊", "勝率變化（百分點）"],
                       first_note="<b>季末輪休</b>：已經確定季後賽名次的球隊，最後幾場常讓主力休息，季末勝率可能因此變低；"
                                  "第 2 節可以切換「不算最後 10 場」看看結論有沒有變（主力有沒有真的休息，看「季末輪休」頁）。"
                                  "前後半季是用這一季自己的場次切一半，不是用日期，所以縮短的球季也能比。")

        # ===== 2 每一位冠軍：前半季 vs 後半季 =====
        st.divider()
        slot2 = section("2　每一位冠軍：前半季 → 後半季",
                        "灰點＝前半季勝率、彩色點＝後半季勝率；彩色點在右邊＝越打越好；括號是後半季 − 前半季")
        cut_ = seg("比賽範圍", ["全部場次", "不算最後 10 場"], key="month_cut")
        MO2 = MO[MO["n"] <= MO["n_all"] - 10].copy() if cut_ == "不算最後 10 場" else MO
        if cut_ == "不算最後 10 場":
            MO2["half"] = (MO2["n"] > (MO2["n_all"] - 10) / 2).map({False: "前半季", True: "後半季"})
        H = (MO2.groupby(["season", "abbreviation", "grp", "half"])["win"].mean().unstack("half").reset_index())
        H["d"] = (H["後半季"] - H["前半季"]) * 100
        C = H[H["grp"] == "冠軍"].sort_values("season")
        if C.empty:
            st.info("資料庫裡還沒有冠軍球季的逐場比賽。")
        else:
            O_ = H[H["grp"] == "其他強隊"].dropna(subset=["d"])
            if len(O_):
                C = pd.concat([C, pd.DataFrame([{"season": "", "abbreviation": "_OTHER", "grp": "其他強隊",
                                                 "前半季": O_["前半季"].mean(), "後半季": O_["後半季"].mean(),
                                                 "d": O_["d"].mean()}])], ignore_index=True)
            labels = [(f"其他強隊平均（{len(O_)} 個隊季）（{d_:+.0f}）" if a_ == "_OTHER" else f"{s_} {ALL_ZH.get(a_, a_)}（{d_:+.0f}）")
                      for s_, a_, d_ in zip(C["season"], C["abbreviation"], C["d"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, C.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["前半季"], r_["後半季"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C["前半季"], y=labels, mode="markers", name="前半季",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>前半季 %{x:.1%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=C["後半季"], y=labels, mode="markers", name="後半季",
                                     marker=dict(size=14, color=["#8f889f" if a == "_OTHER" else TEAM_COLORS.get(a, ACCENT) for a in C["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>後半季 %{x:.1%}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="勝率", tickformat=".0%", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 36 * len(C)), width="stretch", config={"displayModeBar": False})
            O = H[H["grp"] == "其他強隊"].dropna(subset=["d"])
            C = C[C["abbreviation"] != "_OTHER"]
            k_up = int((C["d"] > 0).sum())
            c_mean, o_mean = C["d"].mean(), O["d"].mean() if len(O) else float("nan")
            lines = [f"<b>越打越好：</b>{len(C)} 位冠軍裡，有 {k_up} 位的後半季勝率比前半季高"
                     f"（平均 {c_mean:+.1f} 個百分點）。",
                     (f"其他強隊（{len(O)} 個隊季）平均 {o_mean:+.1f} 個百分點，"
                      + ("冠軍上升得比較多。" if c_mean > o_mean else "冠軍並沒有上升得比較多。"))
                     if len(O) else "還沒有足夠的其他強隊可以比較。"]
            if len(O) < 15:
                lines.append(f"其他強隊只有 {len(O)} 個隊季（還沒載入全部 30 隊），先不要下結論；約 11/8 補完後會更可靠。")
            chk = None
            if len(O):
                chk = (("前半成立" if k_up > len(C) / 2 else "前半不成立") + f"：{k_up} / {len(C)} 位冠軍後半季比較好；"
                       + ("後半成立" if c_mean > o_mean and o_mean <= 1 else "後半不成立")
                       + f"：其他強隊平均 {o_mean:+.1f}、冠軍 {c_mean:+.1f} 個百分點。")
            insight(lines, where=slot2, check=chk)
            with st.expander("看每一位冠軍的逐月勝率"):
                M2 = MO[MO["grp"] == "冠軍"].groupby(["season", "abbreviation", "mcat"])["win"].mean().unstack("mcat")
                M2 = M2.reindex(columns=MONTH_ORDER).reset_index().sort_values("season")
                tb = pd.DataFrame({"球季": M2["season"], "冠軍": [ALL_ZH.get(a, a) for a in M2["abbreviation"]],
                                   "_key": M2["abbreviation"]})
                for m_ in MONTH_ORDER:
                    tb[m_] = [fmt(v, ".0%") for v in M2[m_]]
                nice_table(tb, num_cols=tuple(MONTH_ORDER), dot_col="冠軍", colors=TEAM_COLORS)
                st.caption("「-」＝那個月沒有比賽（例如縮短的球季）。")



# ---------- 節奏與勝率：打得快的隊比較會贏嗎？（2026-11-10）----------
def prep_pace(lg):
    """全聯盟 30 隊每季：節奏、勝率、同季排名、和同季平均的差；只留已經有冠軍的球季（本季還沒打完）"""
    if lg is None or lg.empty or "pace" not in lg.columns:
        return pd.DataFrame()
    d = lg[lg["season_type"].isin(["Regular Season", "Playoffs"])].copy()
    for c in ["pace", "w", "gp", "net_rating"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d["gp"] > 0) & d["pace"].notna()]
    d["win_pct"] = d["w"] / d["gp"]
    keys = ["season", "season_type"]
    d["lg_pace"] = d.groupby(keys)["pace"].transform("mean")
    d["d_pace"] = d["pace"] - d["lg_pace"]                                    # 比同季平均快幾個回合
    d["rk_pace"] = d.groupby(keys)["pace"].rank(ascending=False, method="min")  # 1＝最快
    champ_ids = set(zip(champs["season"], champs["team_id"]))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    return d[d["season"].isin(set(champs["season"]))]


def corr_r(x, y):
    """相關係數 r（點太少或沒有變化時回傳空值）"""
    ok = x.notna() & y.notna()
    if ok.sum() < 5:
        return float("nan")
    return float(x[ok].corr(y[ok]))


if PAGE == "節奏與勝率":
    hypothesis("打得快的隊比較會贏嗎？冠軍是打得快，還是打得慢？進了季後賽會不會變慢？",
               "節奏和勝率幾乎沒有關係（同一季裡相關係數 |r| < 0.2）；冠軍有快有慢，節奏排名的中位數在聯盟中段（第 10～20 名）；"
               "進了季後賽幾乎每一隊都會變慢，冠軍也一樣。")
    PC = prep_pace(league)
    if PC.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py --only league（全聯盟每季數據還沒有寫進資料庫）")
    else:
        RS = PC[PC["season_type"] == "Regular Season"]
        st.caption(f"用全聯盟 30 隊每季數據（{RS['season'].min()}～{RS['season'].max()}，共 {RS['season'].nunique()} 季）計算；"
                   "本季還沒打完，先不列入。節奏＝每 48 分鐘打幾個回合。")
        # ===== 1 每一位冠軍排第幾 =====
        slot1 = section("1　每一位冠軍的節奏排第幾（例行賽）",
                        "一列一季：灰點＝當季其他球隊、彩色點＝冠軍；橫軸＝比同季聯盟平均快（右）或慢（左）幾個回合；"
                        "括號是在 30 隊裡第幾快")
        C1 = RS[RS["champion"]].sort_values("season")
        if C1.empty:
            st.info("資料庫裡還沒有冠軍球季的全聯盟數據。")
        else:
            lab = {s_: f"{s_} {ALL_ZH.get(a_, a_)}（第 {r_:.0f} 快）"
                   for s_, a_, r_ in zip(C1["season"], C1["abbreviation"], C1["rk_pace"])}
            O1 = RS[(~RS["champion"]) & RS["season"].isin(lab)]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=O1["d_pace"], y=[lab[s_] for s_ in O1["season"]], mode="markers",
                                     name="當季其他球隊", marker=dict(size=7, color=DIM),
                                     customdata=O1[["abbreviation", "pace"]].values,
                                     hovertemplate="%{customdata[0]}：節奏 %{customdata[1]:.1f}（%{x:+.1f}）<extra></extra>"))
            fig.add_trace(go.Scatter(x=C1["d_pace"], y=[lab[s_] for s_ in C1["season"]], mode="markers", name="冠軍",
                                     marker=dict(size=14, symbol="diamond", line=dict(width=1.2, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in C1["abbreviation"]]),
                                     customdata=C1[["abbreviation", "pace"]].values,
                                     hovertemplate="★ %{customdata[0]}：節奏 %{customdata[1]:.1f}（%{x:+.1f}）<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dash"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="比同季聯盟平均快幾個回合（每 48 分鐘）", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 100 + 30 * len(C1)), width="stretch", config={"displayModeBar": False})
            med = float(C1["rk_pace"].median())
            n_fast = int((C1["rk_pace"] <= 10).sum())
            n_slow = int((C1["rk_pace"] >= 21).sum())
            n_mid = len(C1) - n_fast - n_slow
            fast1 = C1.sort_values("rk_pace").iloc[0]
            slow1 = C1.sort_values("rk_pace").iloc[-1]
            lines = [f"<b>冠軍有快有慢：</b>{len(C1)} 位冠軍裡，{n_fast} 位排前 10 快、{n_mid} 位在中段、{n_slow} 位排後 10 名；"
                     f"排名中位數是第 {med:.0f} 快。",
                     f"最快的是 {fast1['season']} {ALL_ZH.get(fast1['abbreviation'], fast1['abbreviation'])}（第 {fast1['rk_pace']:.0f} 快），"
                     f"最慢的是 {slow1['season']} {ALL_ZH.get(slow1['abbreviation'], slow1['abbreviation'])}（第 {slow1['rk_pace']:.0f} 快）。",
                     "讀法：彩色點在虛線右邊＝那一季比聯盟平均打得快。看彩色點是不是左右都有——"
                     "如果都擠在同一邊，才代表冠軍有固定的節奏。"]
            ok_mid = 10 <= med <= 20 and n_fast > 0 and n_slow > 0
            chk1 = (("第二句成立" if ok_mid else "第二句不成立")
                    + f"：排名中位數第 {med:.0f}，快（前 10）{n_fast} 位、慢（後 10）{n_slow} 位。")
            insight(lines, where=slot1, check=chk1)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["節奏", "回合", "比同季聯盟平均多多少", "相關係數 r", "季後賽節奏變化"],
                           first_note="節奏只說明<b>打得多快</b>，不是打得多好；"
                                      "用每 100 回合算的進攻、防守效率（冠軍密碼頁）已經把節奏的影響扣掉了。")

        # ===== 2 打得快比較會贏嗎 =====
        st.divider()
        slot2 = section("2　打得快比較會贏嗎？（全聯盟，例行賽）",
                        "每個點是一隊一季；橫軸＝比同季平均快幾個回合、縱軸＝勝率，★ 是冠軍；"
                        "也可以切換成「每一季的 r」，看是不是每一年都一樣")
        view2 = seg("看哪一種", ["全部的點", "每一季的 r"], "pace_view2")
        r_all = corr_r(RS["d_pace"], RS["win_pct"])
        by_s = pd.DataFrame([{"season": s_, "r": corr_r(g_["d_pace"], g_["win_pct"])} for s_, g_ in RS.groupby("season")])
        if view2 == "全部的點":
            o2, c2 = RS[~RS["champion"]], RS[RS["champion"]]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=o2["d_pace"], y=o2["win_pct"], mode="markers", name="其他球隊",
                                     marker=dict(size=7, color=DIM, opacity=0.85),
                                     customdata=o2[["season", "abbreviation"]].values,
                                     hovertemplate="%{customdata[0]} %{customdata[1]}<br>快 %{x:+.1f} 回合｜勝率 %{y:.0%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=c2["d_pace"], y=c2["win_pct"], mode="markers", name="冠軍",
                                     marker=dict(size=14, symbol="star", line=dict(width=1, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in c2["abbreviation"]]),
                                     customdata=c2[["season", "abbreviation"]].values,
                                     hovertemplate="★ %{customdata[0]} %{customdata[1]}<br>快 %{x:+.1f} 回合｜勝率 %{y:.0%}<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dash"))
            fig.update_xaxes(title="比同季聯盟平均快幾個回合")
            fig.update_yaxes(title="例行賽勝率", tickformat=".0%")
            fig.update_layout(legend=dict(orientation="h", y=1.06, x=0))
            st.plotly_chart(style(fig, 420), width="stretch")
        else:
            fig = go.Figure(go.Bar(x=by_s["season"], y=by_s["r"],
                                   marker_color=[ACCENT if abs(v) >= 0.3 else "#c9c3d6" for v in by_s["r"].fillna(0)],
                                   text=[fmt(v, "+.2f") for v in by_s["r"]], textposition="outside", cliponaxis=False,
                                   textfont=dict(size=10, color=INK_2),
                                   hovertemplate="%{x}：r = %{y:+.2f}<extra></extra>"))
            rounded(fig)
            for y_ in (0.3, -0.3):
                fig.add_hline(y=y_, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_xaxes(type="category", title="球季")
            fig.update_yaxes(title="節奏和勝率的相關係數 r", range=[-1, 1])
            st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
        n_strong = int((by_s["r"].abs() >= 0.3).sum())
        n_pos = int((by_s["r"] > 0).sum())
        strength = ("幾乎沒有關係" if abs(r_all) < 0.1 else "弱" if abs(r_all) < 0.3 else "中等" if abs(r_all) < 0.5 else "強")
        lines = [f"<b>節奏和勝率{strength}：</b>全部 {len(RS)} 個隊季放在一起，r = {r_all:+.2f}"
                 + ("（打得快的隊稍微比較會贏）。" if r_all >= 0.1 else "（打得快的隊稍微比較會輸）。" if r_all <= -0.1 else "。"),
                 f"{len(by_s)} 季裡，有 {n_pos} 季是正的（快的隊贏比較多）、{len(by_s) - n_pos} 季是負的；"
                 f"|r| 到 0.3（中等）的只有 {n_strong} 季。",
                 "讀法：r 正負一直換、大多在 ±0.3 的虛線之間，代表「快」本身不會讓球隊比較會贏；"
                 "第 1 節冠軍有快有慢，也是同一件事。"]
        chk2 = (("第一句成立" if abs(r_all) < 0.2 else "第一句不成立") + f"：全部隊季 r = {r_all:+.2f}"
                + f"，{n_strong} / {len(by_s)} 季 |r| ≥ 0.3。") if pd.notna(r_all) else None
        insight(lines, where=slot2, check=chk2)

        # ===== 3 進季後賽會變慢嗎 =====
        st.divider()
        slot3 = section("3　進了季後賽會變慢嗎？",
                        "一列一位冠軍：灰點＝例行賽節奏、彩色點＝季後賽節奏；括號是季後賽 − 例行賽（負數＝變慢）；"
                        "發現框再和所有季後賽球隊比")
        PO = PC[PC["season_type"] == "Playoffs"][["season", "team_id", "pace"]].rename(columns={"pace": "po_pace"})
        RP = RS[["season", "team_id", "abbreviation", "pace", "champion"]].merge(PO, on=["season", "team_id"], how="inner")
        RP["dlt"] = RP["po_pace"] - RP["pace"]
        C3 = RP[RP["champion"]].sort_values("season")
        if C3.empty:
            st.info("資料庫裡還沒有冠軍的季後賽全聯盟數據（load_to_supabase.py --only league 會一起抓季後賽）。")
        else:
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}（{d_:+.1f}）" for s_, a_, d_ in zip(C3["season"], C3["abbreviation"], C3["dlt"])]
            fig = go.Figure()
            for lab_, (_, r_) in zip(labels, C3.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["pace"], r_["po_pace"]], y=[lab_, lab_], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C3["pace"], y=labels, mode="markers", name="例行賽",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>例行賽節奏 %{x:.1f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=C3["po_pace"], y=labels, mode="markers", name="季後賽",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in C3["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>季後賽節奏 %{x:.1f}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="節奏（每 48 分鐘回合數）", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 100 + 32 * len(C3)), width="stretch", config={"displayModeBar": False})
            O3 = RP[~RP["champion"]]
            k_slow_c = int((C3["dlt"] < 0).sum())
            share_all = float((RP["dlt"] < 0).mean())
            c_m, o_m = C3["dlt"].mean(), O3["dlt"].mean() if len(O3) else float("nan")
            lines = [f"<b>季後賽變慢：</b>{len(C3)} 位冠軍裡有 {k_slow_c} 位季後賽比例行賽慢（平均 {c_m:+.1f} 個回合）。",
                     (f"所有打進季後賽的球隊（{len(RP)} 個隊季）有 {share_all:.0%} 變慢；"
                      f"其他季後賽球隊平均 {o_m:+.1f}，冠軍" + ("變慢得比較多。" if c_m < o_m else "變慢得比較少。"))
                     if len(O3) else "還沒有其他季後賽球隊可以比較。",
                     "讀法：季後賽對手固定、防守更認真、暫停和罰球比較多，整體比賽會變慢；"
                     "所以要看冠軍是「跟大家一樣變慢」，還是特別快或特別慢。"]
            ok3 = share_all >= 0.7 and k_slow_c > len(C3) / 2
            chk3 = (("第三句成立" if ok3 else "第三句不成立")
                    + f"：{share_all:.0%} 的季後賽球隊變慢，冠軍 {k_slow_c} / {len(C3)} 位變慢。")
            insight(lines, where=slot3, check=chk3)

        # ===== 4 背景：聯盟一年比一年快 =====
        st.divider()
        slot4 = section("4　背景：聯盟一年比一年快",
                        "灰線＝聯盟平均節奏、彩色點＝當季冠軍；這一節不是在驗證假設，"
                        "而是說明為什麼前面都用「和同季平均比」：不同年代的快慢差很多，直接比數字不公平")
        LGm = RS.groupby("season")["pace"].mean().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=LGm["season"], y=LGm["pace"], mode="lines+markers", name="聯盟平均",
                                 line=dict(color=MUTED, width=2.4), marker=dict(size=6, color=MUTED),
                                 hovertemplate="%{x} 聯盟平均 %{y:.1f}<extra></extra>"))
        if len(C1):
            fig.add_trace(go.Scatter(x=C1["season"], y=C1["pace"], mode="markers", name="冠軍",
                                     marker=dict(size=11, symbol="diamond", line=dict(width=1, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in C1["abbreviation"]]),
                                     customdata=C1["abbreviation"],
                                     hovertemplate="%{x} ★ %{customdata}：%{y:.1f}<extra></extra>"))
        fig.update_xaxes(type="category", title="球季")
        fig.update_yaxes(title="節奏（每 48 分鐘回合數）")
        fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
        st.plotly_chart(style(fig, 340), width="stretch", config={"displayModeBar": False})
        if len(LGm) >= 2:
            lo_ = LGm.sort_values("pace").iloc[0]
            insight([f"聯盟平均節奏從 {LGm['season'].iloc[0]} 的 {LGm['pace'].iloc[0]:.1f} 變成 "
                     f"{LGm['season'].iloc[-1]} 的 {LGm['pace'].iloc[-1]:.1f} 個回合；最慢是 {lo_['season']}（{lo_['pace']:.1f}）。"],
                    where=slot4, to_summary=False)
        with st.expander("看每一位冠軍的節奏數字"):
            T = C1.merge(RP[["season", "team_id", "po_pace", "dlt"]], on=["season", "team_id"], how="left") if len(C1) else C1
            if len(T):
                nice_table(pd.DataFrame({
                    "球季": T["season"], "冠軍": [ALL_ZH.get(a, a) for a in T["abbreviation"]], "_key": T["abbreviation"],
                    "例行賽節奏": [f"{v:.1f}" for v in T["pace"]], "聯盟平均": [f"{v:.1f}" for v in T["lg_pace"]],
                    "比聯盟": [f"{v:+.1f}" for v in T["d_pace"]], "第幾快": [f"{v:.0f}" for v in T["rk_pace"]],
                    "例行賽勝率": [f"{v:.0%}" for v in T["win_pct"]],
                    "季後賽節奏": [fmt(v, ".1f") for v in T["po_pace"]], "季後賽變化": [fmt(v, "+.1f") for v in T["dlt"]],
                }), num_cols=("例行賽節奏", "聯盟平均", "比聯盟", "第幾快", "例行賽勝率", "季後賽節奏", "季後賽變化"),
                    signed_cols=("比聯盟", "季後賽變化"), dot_col="冠軍", colors=TEAM_COLORS)


# ---------- 奪冠前一季（2026-11-11 新增）：冠軍是突然變強的嗎？哪一項進步最多？ ----------
# 指標：名稱 →（欄位, 越高越好嗎）
PRIOR_ITEMS = {"勝率": ("win_pct", True), "淨效率": ("net_rating", True), "進攻效率": ("off_rating", True),
               "防守效率": ("def_rating", False), "真實命中率": ("ts_pct", True), "失誤率": ("tm_tov_pct", False),
               "進攻籃板率": ("oreb_pct", True), "防守籃板率": ("dreb_pct", True), "助攻失誤比": ("ast_to", True)}
TERMS.setdefault("前一季", ("奪冠那一季的上一季，例如 2022-23 金塊的前一季是 2021-22", "同一隊（球隊編號相同，搬家改名也算同一隊）"))
TERMS.setdefault("排名進步", ("前一季在聯盟排第幾 − 奪冠季排第幾；正數＝名次往前（變好）", "例：第 9 名 → 第 2 名＝進步 7 名"))
TERMS.setdefault("比同季平均（每 100 回合）",
                 ("這隊減掉同一季 30 隊的平均，單位是「每 100 個回合幾分」；聯盟進攻一年比一年好，所以要和同季比",
                  "防守效率越低越好，所以已經反過來：正數＝比聯盟守得好"))


def prev_season(s):
    """'2022-23' → '2021-22'"""
    try:
        y = int(str(s)[:4]) - 1
        return f"{y}-{str(y + 1)[2:]}"
    except ValueError:
        return None


def prep_prior(lg, champs_, strong=0.6):
    """全聯盟每隊每季（例行賽）：每一項的同季排名、和同季平均的差，再和同一隊的前一季並排"""
    d = lg[lg["season_type"] == "Regular Season"].copy()
    for c in ["gp", "w"] + [v[0] for k, v in PRIOR_ITEMS.items() if k != "勝率"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["win_pct"] = d["w"] / d["gp"].where(d["gp"] > 0)
    keep = ["team_id", "season", "abbreviation", "win_pct"]
    for name, (c, hb) in PRIOR_ITEMS.items():
        d[f"rk_{c}"] = d.groupby("season")[c].rank(ascending=not hb, method="min")
        d[f"g_{c}"] = (d[c] - d.groupby("season")[c].transform("mean")) * (1 if hb else -1)
        keep += [f"rk_{c}", f"g_{c}"]
    d = d[keep]
    d["prev"] = d["season"].map(prev_season)
    p = d.drop(columns=["abbreviation", "prev"]).rename(columns={"season": "prev"})
    m = d.merge(p, on=["team_id", "prev"], suffixes=("", "_p"), how="inner")
    for name, (c, _) in PRIOR_ITEMS.items():
        m[f"up_{c}"] = m[f"rk_{c}_p"] - m[f"rk_{c}"]          # 名次進步（正數＝變好）
        m[f"dg_{c}"] = m[f"g_{c}"] - m[f"g_{c}_p"]            # 比同季平均的進步（正數＝變好）
    champ_ids = set(zip(champs_["season"], pd.to_numeric(champs_["team_id"], errors="coerce")))
    m["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(m["season"], pd.to_numeric(m["team_id"], errors="coerce"))]
    m["grp"] = "其他球隊"
    m.loc[(~m["champion"]) & (m["win_pct"] >= strong), "grp"] = "其他強隊"
    m.loc[m["champion"], "grp"] = "冠軍"
    return m[m["season"].isin(set(champs_["season"]))]


if PAGE == "奪冠前一季":
    hypothesis("冠軍是「突然變強」的嗎？奪冠那一季，比前一季進步在哪裡？",
               "冠軍多半不是突然變強：前一季的淨效率就已經在聯盟前 5 名；奪冠季的進步主要來自防守"
               "（和同季平均比，防守效率進步得比進攻多），而且這種「防守進步」是同樣強的其他球隊沒有的。")
    if league.empty or "net_rating" not in league.columns:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（全聯盟每季數據 league_team_seasons 還沒有寫進資料庫）")
    else:
        PR = prep_prior(league, champs)
        C = PR[PR["champion"]].sort_values("season")
        O = PR[PR["grp"] == "其他強隊"]
        st.caption(f"用全聯盟 30 隊的例行賽計算；資料從 2006-07 開始，所以 2006-07 的冠軍沒有前一季可以比，"
                   f"共 {len(C)} 位冠軍；對照組「其他強隊」＝同一季勝率六成以上、沒奪冠，共 {len(O)} 個隊季。")
        if C.empty:
            st.info("資料庫裡還沒有可以比較的冠軍球季（需要奪冠季和前一季的全聯盟數據）。")
        else:
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}" for s_, a_ in zip(C["season"], C["abbreviation"])]
            # ===== 1 前一季就很強了嗎？ =====
            slot1 = section("1　前一季就很強了嗎？",
                            "灰點＝前一季的淨效率排名、彩色點＝奪冠季的排名；越右邊名次越前面（第 1 名在最右邊）。"
                            "灰點已經在右邊＝前一季就是強隊；兩點離很遠＝那一年突然跳上來")
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, C.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["rk_net_rating_p"], r_["rk_net_rating"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C["rk_net_rating_p"], y=labels, mode="markers+text", name="前一季",
                                     text=[f"第 {v:.0f}" for v in C["rk_net_rating_p"]], textposition="middle left",
                                     textfont=dict(size=10.5, color=INK_2),
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>前一季淨效率：聯盟第 %{x:.0f} 名<extra></extra>"))
            fig.add_trace(go.Scatter(x=C["rk_net_rating"], y=labels, mode="markers", name="奪冠季",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in C["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>奪冠季淨效率：聯盟第 %{x:.0f} 名<extra></extra>"))
            fig.add_vrect(x0=0.5, x1=5.5, fillcolor="rgba(167,139,250,0.10)", line_width=0, layer="below")
            fig.update_xaxes(title="淨效率排名（淡紫底＝前 5 名）", range=[30.5, 0.5], dtick=5, showgrid=True, gridcolor=GRID)
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 32 * len(C)), width="stretch", config={"displayModeBar": False})
            k5 = int((C["rk_net_rating_p"] <= 5).sum())
            med_p = C["rk_net_rating_p"].median()
            jump = C.loc[C["up_net_rating"].idxmax()]
            lines = [f"<b>{len(C)} 位冠軍裡，有 {k5} 位前一季就是聯盟淨效率前 5 名</b>（前一季排名的中位數是第 {med_p:.0f} 名）。",
                     f"跳最多的是 {jump['season']} {ALL_ZH.get(jump['abbreviation'], jump['abbreviation'])}："
                     f"前一季第 {jump['rk_net_rating_p']:.0f} 名 → 奪冠季第 {jump['rk_net_rating']:.0f} 名。",
                     f"奪冠季本身：{int((C['rk_net_rating'] <= 3).sum())} 位是淨效率前 3 名。"]
            chk = (("前半成立" if k5 > len(C) / 2 else "前半不成立")
                   + f"：{k5} / {len(C)} 位冠軍前一季已經是前 5 名" + ("，大多不是突然變強。" if k5 > len(C) / 2 else "，不少冠軍是那一年才跳上來。"))
            insight(lines, where=slot1, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["前一季", "淨效率", "排名進步", "比同季平均（每 100 回合）", "其他強隊"],
                           first_note="排名都是和<b>同一季 30 隊</b>比，只看例行賽；「前一季」是同一支球隊的上一季，"
                                      "中間如果換了球星或教練，這頁看不出來（可以到「球員」頁看陣容變化）。")

            # ===== 2 進步來自進攻還是防守？ =====
            st.divider()
            slot2 = section("2　進步來自進攻還是防守？",
                            "長條＝奪冠季比前一季進步多少（和同季平均比，每 100 回合幾分）；紫＝進攻、灰＝防守。"
                            "淨效率的進步剛好等於進攻進步＋防守進步，所以看哪一條比較長，就知道進步主要來自哪一邊")
            view2 = seg("看哪一種", ["看各組平均", "看每一位冠軍"], "prior_view2")
            G = (PR[PR["grp"].isin(["冠軍", "其他強隊"])].groupby("grp")[["dg_off_rating", "dg_def_rating"]]
                 .mean().reindex(["冠軍", "其他強隊"]))
            n_grp = PR["grp"].value_counts()
            if view2 == "看各組平均":
                xs = [f"{g_}（{int(n_grp.get(g_, 0))}）" for g_ in G.index]
                fig = go.Figure()
                for col_, nm, colr in [("dg_off_rating", "進攻進步", ACCENT), ("dg_def_rating", "防守進步", "#8f889f")]:
                    fig.add_trace(go.Bar(x=xs, y=G[col_], name=nm, marker_color=colr,
                                         text=[fmt(v, "+.1f") for v in G[col_]], textposition="outside",
                                         hovertemplate="%{x}<br>" + nm + "：%{y:+.1f} 分／100 回合<extra></extra>"))
                fig.update_layout(barmode="group")
                fig.update_xaxes(type="category")
                fig.update_yaxes(title="比前一季進步（分／100 回合）", zeroline=True, zerolinecolor=MUTED)
                rounded(fig)
                st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
            else:
                fig = go.Figure()
                for col_, nm, colr in [("dg_off_rating", "進攻進步", ACCENT), ("dg_def_rating", "防守進步", "#8f889f")]:
                    fig.add_trace(go.Bar(y=labels, x=C[col_], name=nm, orientation="h", marker_color=colr,
                                         hovertemplate="%{y}<br>" + nm + "：%{x:+.1f} 分／100 回合<extra></extra>"))
                fig.add_trace(go.Scatter(y=labels, x=C["dg_net_rating"], mode="markers", name="淨效率進步（合計）",
                                         marker=dict(symbol="diamond", size=10, color=INK, line=dict(width=1, color=SURFACE)),
                                         hovertemplate="%{y}<br>合計：%{x:+.1f} 分／100 回合<extra></extra>"))
                fig.update_layout(barmode="relative", legend=dict(orientation="h", y=1.04, x=0))
                fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
                fig.update_xaxes(title="比前一季進步（分／100 回合；負數＝退步）", zeroline=True, zerolinecolor=MUTED,
                                 showgrid=True, gridcolor=GRID)
                st.plotly_chart(style(fig, 90 + 32 * len(C)), width="stretch", config={"displayModeBar": False})
            c_off, c_def = G.loc["冠軍", "dg_off_rating"], G.loc["冠軍", "dg_def_rating"]
            o_off, o_def = (G.loc["其他強隊", "dg_off_rating"], G.loc["其他強隊", "dg_def_rating"]) if len(O) else (float("nan"),) * 2
            k_def = int((C["dg_def_rating"] > C["dg_off_rating"]).sum())
            main_side = "防守" if c_def > c_off else "進攻"
            lines = [f"<b>冠軍的進步主要來自{main_side}：</b>平均進攻 {c_off:+.1f}、防守 {c_def:+.1f} 分／100 回合"
                     f"（{k_def} / {len(C)} 位冠軍防守進步比進攻多）。",
                     (f"其他強隊平均進攻 {o_off:+.1f}、防守 {o_def:+.1f}。" if len(O) else "還沒有其他強隊可以比較。"),
                     "讀法：正數＝比前一季進步（防守已經反過來，正數＝守得更好）；"
                     "「其他強隊」也是挑「這一季很強」的隊，所以平均也會是進步的，要比的是冠軍和它們差在哪一邊。"]
            chk = (("後半成立" if c_def > c_off and (not len(O) or c_def - o_def > c_off - o_off) else "後半不成立")
                   + f"：冠軍防守 {c_def:+.1f}、進攻 {c_off:+.1f}"
                   + (f"；和其他強隊比，防守多 {c_def - o_def:+.1f}、進攻多 {c_off - o_off:+.1f}。" if len(O) else "。"))
            insight(lines, where=slot2, check=chk)

            # ===== 3 哪一項排名進步最多？ =====
            st.divider()
            slot3 = section("3　哪一項排名進步最多？",
                            "一列一位冠軍、一欄一項數據，格子＝排名進步幾名（前一季名次 − 奪冠季名次）；越深＝進步越多，"
                            "負數（白底）＝退步。最下面一列是同樣強的其他球隊的中位數")
            names = list(PRIOR_ITEMS)
            Z = C[[f"up_{PRIOR_ITEMS[n][0]}" for n in names]].to_numpy(dtype=float)
            med_c = C[[f"up_{PRIOR_ITEMS[n][0]}" for n in names]].median()
            med_o = O[[f"up_{PRIOR_ITEMS[n][0]}" for n in names]].median() if len(O) else med_c * float("nan")
            ylab = labels + ["冠軍中位數", "其他強隊中位數"]
            Zall = list(Z) + [med_c.to_numpy(dtype=float), med_o.to_numpy(dtype=float)]
            fig = go.Figure(go.Heatmap(
                z=Zall, x=names, y=ylab, zmin=0, zmax=15,
                colorscale=[[i / (len(PURPLE_RAMP) - 1), c] for i, c in enumerate(PURPLE_RAMP)],
                xgap=3, ygap=3, showscale=False,
                hovertemplate="%{y}<br>%{x}：進步 %{z:+.0f} 名<extra></extra>"))
            for i, lab in enumerate(ylab):
                for j, n in enumerate(names):
                    v = Zall[i][j]
                    if pd.isna(v):
                        continue
                    fig.add_annotation(x=n, y=lab, showarrow=False, text=f"{v:+.0f}",
                                       font=dict(size=11, color="#ffffff" if v >= 9 else INK))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(type="category", side="top")
            st.plotly_chart(style(fig, 120 + 30 * len(ylab)), width="stretch", config={"displayModeBar": False})
            items = [n for n in names if n not in ("勝率", "淨效率")]     # 勝率、淨效率是總成績，不算「單項」
            best = max(items, key=lambda n: med_c[f"up_{PRIOR_ITEMS[n][0]}"])
            bv = med_c[f"up_{PRIOR_ITEMS[best][0]}"]
            ov = med_o[f"up_{PRIOR_ITEMS[best][0]}"]
            k_up = int((C[f"up_{PRIOR_ITEMS[best][0]}"] > 0).sum())
            lines = [f"<b>冠軍進步最多的單項是「{best}」</b>：排名進步的中位數 {bv:+.0f} 名，{k_up} / {len(C)} 位冠軍這一項有進步。",
                     (f"同一項，其他強隊的中位數是 {ov:+.0f} 名。" if pd.notna(ov) else ""),
                     f"勝率排名的中位數進步 {med_c['up_win_pct']:+.0f} 名、淨效率 {med_c['up_net_rating']:+.0f} 名。"]
            insight(lines, where=slot3)
            with st.expander("看每一位冠軍的實際數字"):
                tb = pd.DataFrame({
                    "球季": C["season"], "冠軍": [ALL_ZH.get(a, a) for a in C["abbreviation"]], "_key": C["abbreviation"],
                    "勝率（前一季 → 奪冠季）": [f"{p_:.0%} → {w_:.0%}" for p_, w_ in zip(C["win_pct_p"], C["win_pct"])],
                    "淨效率排名": [f"第 {p_:.0f} → 第 {w_:.0f}" for p_, w_ in zip(C["rk_net_rating_p"], C["rk_net_rating"])],
                    "進攻進步": [fmt(v, "+.1f") for v in C["dg_off_rating"]],
                    "防守進步": [fmt(v, "+.1f") for v in C["dg_def_rating"]],
                })
                nice_table(tb, num_cols=("進攻進步", "防守進步"), signed_cols=("進攻進步", "防守進步"),
                           dot_col="冠軍", colors=TEAM_COLORS)
                st.caption("進攻、防守進步的單位是「每 100 回合幾分」，已經和同季平均比過；防守正數＝守得更好。")



# ---------- 陣容深度：冠軍的得分靠幾個人？（2026-11-12 新增）----------
TERMS.update({
    "得分佔比": ("這位球員整季的得分，佔全隊總得分的比例", "球員整季得分 ÷ 全隊所有球員得分合計"),
    "前 3 人得分佔比": ("隊上得分最多的 3 個人加起來佔全隊幾成；越高＝越靠少數人得分", "第 1～3 名的得分佔比相加"),
    "有效得分人數": ("把得分的分散程度換成「等於幾個人平分」：5 人各得兩成＝5 人，1 人包辦＝1 人；越大越分散",
                "1 ÷ Σ（每位球員得分佔比²）"),
    "頭號得分手": ("這一季在這一隊得分最多的球員（看總得分，不是場均）", "隊內總得分第 1 名"),
})
DEPTH_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
DEPTH_PARTS = [("s1", "頭號得分手", ACCENT), ("s2", "第 2 名", "#a78bfa"), ("s3", "第 3 名", "#c4b5fd"),
               ("rest", "其他人", "#e4e0ec")]


def _num(s):
    return pd.to_numeric(s, errors="coerce")


def prep_depth(players, lg, champs_, team_tbl, strong=0.6):
    """一隊一季一種比賽一列：頭號、第 2、第 3 得分手和其他人各佔全隊得分幾成、有效得分人數、勝率、分組"""
    d = players[players["season_type"].isin(["Regular Season", "Playoffs"])].copy()
    if d.empty:
        return pd.DataFrame()
    d["pts"], d["team_id"] = _num(d["pts"]), _num(d["team_id"])
    d = d[d["pts"].notna() & d["team_id"].notna()]
    keys = ["season", "season_type", "team_id"]
    d["team_pts"] = d.groupby(keys)["pts"].transform("sum")
    d = d[d["team_pts"] > 0]
    d["share"] = d["pts"] / d["team_pts"]
    d["rk"] = d.groupby(keys)["pts"].rank(ascending=False, method="first")
    g = d.groupby(keys).agg(team_pts=("team_pts", "first"),
                            eff_n=("share", lambda s: 1 / (s ** 2).sum()),
                            abbreviation=("abbreviation", "first"))
    top = d[d["rk"] <= 3].pivot_table(index=keys, columns="rk", values="share", aggfunc="sum")
    top.columns = [f"s{int(c)}" for c in top.columns]
    g = g.join(top)
    for c in ["s1", "s2", "s3"]:
        g[c] = g[c].fillna(0) if c in g.columns else 0.0
    g["top3"] = g["s1"] + g["s2"] + g["s3"]
    g["rest"] = (1 - g["top3"]).clip(lower=0)
    g = g.join(d[d["rk"] == 1].set_index(keys)["player_name"].rename("star"))
    g = g.reset_index()
    # 例行賽勝率（分組用）：優先用 league_team_seasons，沒有就用網站自己加總的球隊數據
    if lg is not None and not lg.empty and {"w", "gp"} <= set(lg.columns):
        w = lg[lg["season_type"] == "Regular Season"][["season", "team_id", "w", "gp"]].copy()
        w["win_pct"] = _num(w["w"]) / _num(w["gp"]).where(_num(w["gp"]) > 0)
    else:
        w = team_tbl[team_tbl["season_type"] == "Regular Season"][["season", "team_id", "wins", "games"]].copy()
        w["win_pct"] = _num(w["wins"]) / _num(w["games"]).where(_num(w["games"]) > 0)
    w["team_id"] = _num(w["team_id"])
    g = g.merge(w[["season", "team_id", "win_pct"]], on=["season", "team_id"], how="left")
    cid = set(zip(champs_["season"], _num(champs_["team_id"])))
    g["champion"] = [(s_, t_) in cid for s_, t_ in zip(g["season"], g["team_id"])]
    g["grp"] = "其他球隊"
    g.loc[(~g["champion"]) & (g["win_pct"] >= strong), "grp"] = "其他強隊"
    g.loc[g["champion"], "grp"] = "冠軍"
    return g[g["season"].isin(set(champs_["season"]))]   # 本季還沒有冠軍，先不列入


def depth_bars(T, labels, height):
    """橫向 100% 疊長條：頭號、第 2、第 3、其他人；右邊寫有效得分人數"""
    fig = go.Figure()
    for c, name, colr in DEPTH_PARTS:
        fig.add_trace(go.Bar(y=labels, x=T[c], name=name, orientation="h", marker_color=colr,
                             text=[f"{v:.0%}" if v >= 0.06 else "" for v in T[c]], textposition="inside",
                             insidetextanchor="middle",
                             textfont=dict(size=11, color="#ffffff" if c in ("s1", "s2") else INK),
                             hovertemplate="%{y}<br>" + name + "：%{x:.1%}<extra></extra>"))
    for lab, v in zip(labels, T["eff_n"]):
        fig.add_annotation(x=1.0, y=lab, text=f"{v:.1f} 人", showarrow=False, xanchor="left", xshift=8,
                           font=dict(size=11, color=INK_2))
    fig.update_layout(barmode="stack", legend=dict(orientation="h", y=1.08, x=0), bargap=0.3)
    fig.update_xaxes(range=[0, 1.12], tickformat=".0%", tickvals=[0, 0.25, 0.5, 0.75, 1],
                     title="佔全隊得分（右邊數字＝有效得分人數）")
    fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
    st.plotly_chart(style(fig, height), width="stretch", config={"displayModeBar": False})


if PAGE == "陣容深度":
    hypothesis("冠軍的得分是靠一兩位球星，還是分散在很多人身上？進了季後賽，會不會更依賴球星？",
               "冠軍的得分沒有比其他強隊更集中（前 3 人得分佔比相差在 3 個百分點以內）；放到全聯盟，"
               "得分越分散的隊不一定越會贏（|r| < 0.3）；進了季後賽，冠軍和其他球隊都更依賴前 3 人（佔比上升）。")
    DP = prep_depth(player_raw, league, champs, team_raw) if not player_raw.empty else pd.DataFrame()
    if DP.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球員逐場數據還沒有寫進資料庫）")
    else:
        dp_type_zh = seg("比賽類型（第 1 節）", ["例行賽", "季後賽"], "dp_type")
        R = DP[DP["season_type"] == TYPE_OPTIONS[dp_type_zh]]
        st.caption(f"用資料庫已載入球員逐場數據的 {DP['abbreviation'].nunique()} 隊、{DP['season'].nunique()} 季計算"
                   "（本季還沒打完，先不列入）；只算得分，不算助攻和防守。")

        # ===== 1 冠軍 vs 其他強隊 =====
        slot1 = section(f"1　冠軍 vs 其他強隊：得分靠幾個人？（{dp_type_zh}）",
                        "長條由左到右＝頭號得分手、第 2 名、第 3 名、其他人各佔全隊得分幾成；右邊是有效得分人數（越大越分散）")
        view1 = seg("看哪一種", ["看各組平均", "看每一位冠軍"], "dp_view1")
        G = R.groupby("grp").agg(s1=("s1", "mean"), s2=("s2", "mean"), s3=("s3", "mean"), rest=("rest", "mean"),
                                 top3=("top3", "mean"), eff_n=("eff_n", "mean"), n=("s1", "size")).reindex(DEPTH_GROUPS).dropna(subset=["n"])
        C = R[R["champion"]].sort_values("season")
        if C.empty:
            st.info("資料不足：還沒有冠軍球季的球員得分資料。")
        else:
            if view1 == "看各組平均":
                depth_bars(G, [f"{g_}（{int(n_)} 個隊季）" for g_, n_ in zip(G.index, G["n"])], 260)
            else:
                labels = [f"{s_} {ALL_ZH.get(a_, a_)}　{p_}" for s_, a_, p_ in zip(C["season"], C["abbreviation"], C["star"])]
                depth_bars(C, labels, 110 + 30 * len(C))
            c3 = G.loc["冠軍", "top3"]
            lines = [f"<b>前 3 人得分佔比：</b>冠軍平均 {c3:.1%}"]
            chk1 = None
            if "其他強隊" in G.index:
                o3 = G.loc["其他強隊", "top3"]
                dd = (c3 - o3) * 100
                lines[0] += f"、其他強隊 {o3:.1%}，冠軍{'比較集中' if dd > 0 else '比較分散'} {abs(dd):.1f} 個百分點。"
                chk1 = ("前半成立" if abs(dd) <= 3 else "前半不成立") + f"：相差 {dd:+.1f} 個百分點（假設是 3 個百分點以內）。"
            else:
                lines[0] += "；還沒有足夠的其他強隊可以比較。"
            hi, lo = C.sort_values("eff_n").iloc[0], C.sort_values("eff_n").iloc[-1]
            lines.append(f"最靠少數人的冠軍：{hi['season']} {ALL_ZH.get(hi['abbreviation'], hi['abbreviation'])}"
                         f"（{hi['star']} 一人佔 {hi['s1']:.0%}，有效得分人數 {hi['eff_n']:.1f}）；"
                         f"最分散：{lo['season']} {ALL_ZH.get(lo['abbreviation'], lo['abbreviation'])}"
                         f"（有效得分人數 {lo['eff_n']:.1f}）。")
            lines.append("讀法：紫色越深的那一段越長＝越靠頭號得分手；淺灰「其他人」越長＝板凳和角色球員分到越多得分。"
                         "有效得分人數 5 人，代表得分分散的程度「像 5 個人平分」。")
            insight(lines, where=slot1, check=chk1)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["得分佔比", "頭號得分手", "前 3 人得分佔比", "有效得分人數", "其他強隊", "相關係數 r"],
                           first_note="只算<b>得分</b>，不算助攻、籃板和防守；季中被交易的球員，只算他在這一隊的得分。")

        # ===== 2 放到全聯盟：得分越分散，越會贏嗎？ =====
        st.divider()
        slot2 = section("2　放到全聯盟：得分越分散，越會贏嗎？（例行賽）",
                        "每個點是一隊一季：橫軸＝有效得分人數比同季平均多幾人（越右越分散）、縱軸＝勝率，★ 是冠軍")
        RS = DP[(DP["season_type"] == "Regular Season") & DP["win_pct"].notna()].copy()
        RS["d_eff"] = RS["eff_n"] - RS.groupby("season")["eff_n"].transform("mean")
        if len(RS) < 30:
            st.info("資料不足：已載入的球隊太少，還不能看全聯盟的關係。")
        else:
            o_, c_ = RS[~RS["champion"]], RS[RS["champion"]]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=o_["d_eff"], y=o_["win_pct"], mode="markers", name="其他隊季",
                                     marker=dict(size=7, color=DIM, opacity=0.85),
                                     customdata=o_[["season", "abbreviation", "eff_n"]].values,
                                     hovertemplate="%{customdata[0]} %{customdata[1]}<br>有效得分人數 %{customdata[2]:.1f}"
                                                   "（比同季 %{x:+.1f}）｜勝率 %{y:.1%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=c_["d_eff"], y=c_["win_pct"], mode="markers", name="冠軍",
                                     marker=dict(size=15, symbol="star", line=dict(width=1, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in c_["abbreviation"]]),
                                     customdata=c_[["season", "abbreviation", "eff_n"]].values,
                                     hovertemplate="★ %{customdata[0]} %{customdata[1]}<br>有效得分人數 %{customdata[2]:.1f}"
                                                   "（比同季 %{x:+.1f}）｜勝率 %{y:.1%}<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_xaxes(title="有效得分人數 − 同季平均（右＝比較分散）", showgrid=True, gridcolor=GRID)
            fig.update_yaxes(title="例行賽勝率", tickformat=".0%")
            fig.update_layout(legend=dict(orientation="h", y=1.06, x=0))
            st.plotly_chart(style(fig, 420), width="stretch")
            r_all = RS["d_eff"].corr(RS["win_pct"])
            k_right = int((c_["d_eff"] > 0).sum())
            strength = "幾乎沒有關係" if abs(r_all) < 0.1 else ("弱相關" if abs(r_all) < 0.3 else ("中等相關" if abs(r_all) < 0.5 else "強相關"))
            lines = [f"<b>得分分散和勝率：</b>r ＝ {r_all:+.2f}（{strength}；{len(RS)} 個隊季）。",
                     f"{len(c_)} 位冠軍裡，有 {k_right} 位在虛線右邊（得分比同季平均分散）。",
                     "讀法：點如果由左下往右上排，才代表「越分散越會贏」；一團散開＝沒什麼關係。"
                     "用「比同季平均」是因為近年三分球多、輪替變化，整個聯盟的分散程度一直在變。"]
            chk2 = ("中段成立" if abs(r_all) < 0.3 else "中段不成立") + f"：r ＝ {r_all:+.2f}（假設是 |r| < 0.3）。"
            insight(lines, where=slot2, check=chk2)

        # ===== 3 進了季後賽，更依賴前 3 人嗎？ =====
        st.divider()
        slot3 = section("3　進了季後賽，更依賴前 3 人嗎？",
                        "灰點＝例行賽、彩色點＝季後賽的前 3 人得分佔比；彩色點在右邊＝季後賽更靠前 3 人；括號是差幾個百分點")
        k_ = ["season", "team_id", "abbreviation"]
        RP = (DP[DP["season_type"] == "Regular Season"][k_ + ["top3", "champion", "star"]]
              .merge(DP[DP["season_type"] == "Playoffs"][k_ + ["top3"]], on=k_, suffixes=("_r", "_p"), how="inner"))
        RP["dlt"] = (RP["top3_p"] - RP["top3_r"]) * 100
        CP = RP[RP["champion"]].sort_values("season")
        OP = RP[~RP["champion"]]
        if CP.empty:
            st.info("資料不足：還沒有冠軍的季後賽球員得分資料。")
        else:
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}（{d_:+.0f}）" for s_, a_, d_ in zip(CP["season"], CP["abbreviation"], CP["dlt"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, CP.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["top3_r"], r_["top3_p"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=CP["top3_r"], y=labels, mode="markers", name="例行賽",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>例行賽前 3 人 %{x:.1%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=CP["top3_p"], y=labels, mode="markers", name="季後賽",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in CP["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>季後賽前 3 人 %{x:.1%}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="前 3 人得分佔比", tickformat=".0%", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 32 * len(CP)), width="stretch", config={"displayModeBar": False})
            k_up = int((CP["dlt"] > 0).sum())
            c_m = CP["dlt"].mean()
            o_m = OP["dlt"].mean() if len(OP) else float("nan")
            lines = [f"<b>季後賽更靠前 3 人：</b>{len(CP)} 位冠軍裡有 {k_up} 位（平均 {c_m:+.1f} 個百分點）。",
                     (f"其他季後賽球隊（{len(OP)} 個隊季）平均 {o_m:+.1f} 個百分點。" if len(OP) else
                      "還沒有其他季後賽球隊可以比較。"),
                     "讀法：季後賽輪替縮短、主力打比較久，前 3 人的佔比本來就容易上升；"
                     "要和其他季後賽球隊比，才知道冠軍是不是特別依賴球星。"]
            chk3 = None
            if len(OP):
                chk3 = ("後半成立" if c_m > 0 and o_m > 0 else "後半不成立") + \
                       f"：冠軍 {c_m:+.1f}、其他季後賽球隊 {o_m:+.1f} 個百分點（假設是兩組都上升）。"
            insight(lines, where=slot3, check=chk3)
            with st.expander("看每一位冠軍的數字"):
                tb = pd.DataFrame({"球季": CP["season"], "冠軍": [ALL_ZH.get(a, a) for a in CP["abbreviation"]],
                                   "_key": CP["abbreviation"], "頭號得分手（例行賽）": CP["star"],
                                   "例行賽前 3 人": [fmt(v, ".1%") for v in CP["top3_r"]],
                                   "季後賽前 3 人": [fmt(v, ".1%") for v in CP["top3_p"]],
                                   "變化（百分點）": [f"{v:+.1f}" for v in CP["dlt"]]})
                nice_table(tb, num_cols=("例行賽前 3 人", "季後賽前 3 人", "變化（百分點）"),
                           signed_cols=("變化（百分點）",), dot_col="冠軍", colors=TEAM_COLORS)


# ---------- 季後賽輪次：冠軍哪一輪打得最辛苦？（2026-11-13 新增） ----------
TERMS.update({
    "系列賽": ("季後賽每一輪兩隊連續打好幾場，先贏 4 場的晉級（七戰四勝）", "同一季連續對同一隊的比賽＝一個系列賽"),
    "輪次": ("首輪 → 次輪 → 分區決賽 → 總冠軍賽，一共 4 輪", "這一隊這一季的第幾個系列賽"),
    "打到第 7 戰": ("兩隊各贏 3 場，靠最後一場決定誰晉級，是最辛苦的系列賽", "這個系列賽打了 7 場"),
    "系列賽曾經落後": ("系列賽中途有一刻輸的場數比贏的多（例如 0 比 1、1 比 2），最後逆轉晉級", "逐場累計勝負，有一場之後敗場 > 勝場"),
    "其他晉級球隊": ("同一輪也贏下系列賽、但最後沒有奪冠的球隊；和冠軍一樣「贏了這一輪」，比較才公平", "同一季、同一輪、贏 4 場、不是冠軍"),
    "對手例行賽淨效率": ("這一輪對手在例行賽的整體實力；數字越大對手越強", "對手例行賽的進攻效率 − 防守效率"),
})
ROUND_ORDER = ["首輪", "次輪", "分區決賽", "總冠軍賽"]


def playoff_series(tg, lg):
    """把每一隊的季後賽比賽切成系列賽：同一季、連續對同一個對手＝一個系列賽；第幾個系列賽＝第幾輪"""
    d = tg[tg["season_type"] == "Playoffs"].dropna(subset=["game_date", "abbreviation"]).copy()
    if d.empty:
        return pd.DataFrame()
    d["opp"] = d["matchup"].str.split().str[-1].map(lambda a: OLD_ABBR.get(a, a))
    d = d.sort_values(["team_id", "season", "game_date"])
    keys = ["team_id", "season"]
    d["new"] = d["opp"] != d.groupby(keys)["opp"].shift()        # 對手換了＝新的一輪
    d["rnd"] = d.groupby(keys)["new"].cumsum() - 1                 # 0＝首輪、1＝次輪…
    d["lose"] = 1 - d["win"]
    k3 = keys + ["rnd"]
    d["behind"] = d.groupby(k3)["lose"].cumsum() > d.groupby(k3)["win"].cumsum()   # 這一場打完，系列賽是落後的
    s = (d.groupby(["season", "team_id", "abbreviation", "rnd", "opp"])
         .agg(w=("win", "sum"), l=("lose", "sum"), behind=("behind", "any"),
              home1=("is_home", "first"), champion=("champion", "first"))
         .reset_index())
    s = s[(s["rnd"] < 4) & (s["w"] == 4)].copy()                    # 只看贏下來的系列賽（七戰四勝）
    s["n"] = s["w"] + s["l"]
    s["round"] = s["rnd"].map(lambda r: ROUND_ORDER[int(r)])
    s["g7"] = s["n"] == 7
    s["grp"] = s["champion"].map({True: "冠軍", False: "其他晉級球隊"})
    if not lg.empty and "net_rating" in lg.columns:
        r = lg[lg["season_type"] == "Regular Season"][["season", "abbreviation", "net_rating"]].copy()
        r["net_rating"] = pd.to_numeric(r["net_rating"], errors="coerce")
        r["opp_rank"] = r.groupby("season")["net_rating"].rank(ascending=False, method="min")
        s = s.merge(r.rename(columns={"abbreviation": "opp", "net_rating": "opp_net"}), on=["season", "opp"], how="left")
    else:
        s["opp_net"], s["opp_rank"] = float("nan"), float("nan")
    return s[s["season"].isin(set(champs["season"]))]


if PAGE == "季後賽輪次":
    hypothesis("冠軍在季後賽的四輪（首輪、次輪、分區決賽、總冠軍賽），哪一輪打得最辛苦？",
               "冠軍越往後打得越辛苦：平均場數一輪比一輪多，因為對手一輪比一輪強；"
               "但和同一輪也晉級的其他球隊比，冠軍每一輪都打得比較輕鬆（場數比較少、比較少被逼到第 7 戰）。")
    TG = team_games_with_abbr()
    if TG.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球隊逐場比賽還沒有寫進資料庫）")
    else:
        SR = playoff_series(TG, league)
        if SR.empty or not (SR["grp"] == "冠軍").any():
            st.info("尚未載入資料：資料庫裡還沒有冠軍的季後賽比賽，請執行 python load_to_supabase.py")
        else:
            st.caption(f"用資料庫已載入比賽的 {TG['abbreviation'].nunique()} 隊計算，{SR['season'].nunique()} 個季後賽、"
                       f"{len(SR)} 個贏下來的系列賽。team_games 沒有每場得分，所以只看場數與勝負，不看分差。")
            # ===== 1 哪一輪最辛苦 =====
            slot1 = section("1　哪一輪最辛苦：冠軍 vs 同一輪的其他晉級球隊",
                            "紫色＝冠軍、灰色＝同一輪也贏下系列賽的其他球隊；長條上是平均或比例")
            R_OPTS = {"平均打幾場": ("n", "mean", ".1f", "場"), "打到第 7 戰的比例": ("g7", "mean", ".0%", ""),
                      "系列賽曾經落後的比例": ("behind", "mean", ".0%", ""), "對手例行賽淨效率": ("opp_net", "mean", "+.1f", "")}
            r_pick = seg("看哪一項", list(R_OPTS), "rnd_metric")
            col, how, f, unit = R_OPTS[r_pick]
            G = SR.groupby(["grp", "round"])[col].agg([how, "size"]).reset_index()
            fig = go.Figure()
            for grp, colr in [("其他晉級球隊", "#8f889f"), ("冠軍", ACCENT)]:
                sub = G[G["grp"] == grp].set_index("round").reindex(ROUND_ORDER)
                fig.add_trace(go.Bar(x=ROUND_ORDER, y=sub[how], name=grp, marker_color=colr,
                                     text=[fmt(v, f) + unit for v in sub[how]], textposition="outside",
                                     textfont=dict(size=11, color=INK_2),
                                     customdata=sub["size"].fillna(0).astype(int),
                                     hovertemplate=grp + "<br>%{x}：%{text}（%{customdata} 個系列賽）<extra></extra>"))
            rounded(fig)
            fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=ROUND_ORDER)
            fig.update_yaxes(title=r_pick, tickformat=".0%" if "%" in f else None,
                             range=[0, 7.6] if col == "n" else None, rangemode="tozero")
            st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})

            P = SR.groupby(["grp", "round"])["n"].mean().unstack("round").reindex(columns=ROUND_ORDER)
            cn = P.loc["冠軍"] if "冠軍" in P.index else pd.Series(dtype=float)
            on = P.loc["其他晉級球隊"] if "其他晉級球隊" in P.index else pd.Series(dtype=float)
            lines, chk = [], None
            if cn.notna().any():
                hard = cn.idxmax()
                lines.append(f"<b>冠軍最辛苦的一輪是{hard}：</b>平均打 {cn[hard]:.1f} 場；"
                             f"最輕鬆的是{cn.idxmin()}（{cn.min():.1f} 場）。")
                g7 = SR[SR["grp"] == "冠軍"].groupby("round")["g7"].sum().reindex(ROUND_ORDER).fillna(0).astype(int)
                lines.append("被逼到第 7 戰的次數：" + "、".join(f"{k} {v} 次" for k, v in g7.items()) + "。")
                both = [r_ for r_ in ROUND_ORDER if pd.notna(cn.get(r_)) and pd.notna(on.get(r_))]
                easier = [r_ for r_ in both if cn[r_] < on[r_]]
                if both:
                    lines.append(f"和同一輪的其他晉級球隊比，冠軍在 {len(easier)} / {len(both)} 輪打得比較少場"
                                 + (f"（{'、'.join(easier)}）" if easier else "")
                                 + "；總冠軍賽的贏家一定是冠軍，所以這一輪沒有對照組。")
                c_ok = cn.dropna()
                up = c_ok.is_monotonic_increasing and len(c_ok) >= 3
                late = c_ok.get("分區決賽", float("nan")), c_ok.get("總冠軍賽", float("nan"))
                early = c_ok.get("首輪", float("nan")), c_ok.get("次輪", float("nan"))
                half_up = pd.Series(late).mean() > pd.Series(early).mean()
                chk = (("前半成立" if up else ("前半部分成立：後兩輪平均比前兩輪多場，但不是一輪比一輪多" if half_up
                                              else "前半不成立：後面的輪次沒有打得比較多場"))
                       + "；" + (f"後半成立：{len(easier)} / {len(both)} 輪比其他晉級球隊少場" if both and len(easier) > len(both) / 2
                                else f"後半不成立：只有 {len(easier)} / {len(both)} 輪比其他晉級球隊少場") + "。")
            lines.append("讀法：先看紫色長條是不是由左往右越來越高（越後面越辛苦），再看每一輪紫色是不是比灰色矮（比其他晉級球隊輕鬆）。"
                         "切到「對手例行賽淨效率」可以看對手是不是一輪比一輪強。")
            insight(lines, where=slot1, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["系列賽", "輪次", "打到第 7 戰", "系列賽曾經落後", "其他晉級球隊", "對手例行賽淨效率", "淨效率"],
                           first_note="輪次是從比賽順序推出來的：同一季<b>連續對同一隊</b>就是同一個系列賽，第 1 個系列賽＝首輪。"
                                      "附加賽（Play-In）不算季後賽；資料只有勝負，沒有每場分差。")

            # ===== 2 每一位冠軍的季後賽路線 =====
            st.divider()
            slot2 = section("2　每一位冠軍的季後賽路線",
                            "一列一位冠軍、一欄一輪；格子寫「勝-敗」和對手，顏色越深＝打越多場；「逆」＝系列賽曾經落後、最後逆轉")
            C = SR[SR["grp"] == "冠軍"].copy()
            C["lab"] = [f"{s_} {ALL_ZH.get(a_, a_)}" for s_, a_ in zip(C["season"], C["abbreviation"])]
            rows_ = list(dict.fromkeys(C.sort_values("season")["lab"]))
            Z = C.pivot(index="lab", columns="round", values="n").reindex(index=rows_, columns=ROUND_ORDER)
            T = C.assign(t=[f"{w_}-{l_}　{ALL_ZH.get(o_, o_)}" + ("　逆" if b_ else "")
                            for w_, l_, o_, b_ in zip(C["w"], C["l"], C["opp"], C["behind"])]
                         ).pivot(index="lab", columns="round", values="t").reindex(index=rows_, columns=ROUND_ORDER)
            fig = go.Figure(go.Heatmap(
                z=Z.values.astype(float), x=ROUND_ORDER, y=rows_, zmin=4, zmax=7,
                colorscale=[[i / (len(PURPLE_RAMP) - 1), c] for i, c in enumerate(PURPLE_RAMP)],
                xgap=3, ygap=3, showscale=False, text=T.fillna("").values,
                hovertemplate="%{y}　%{x}<br>%{text}<br>打了 %{z:.0f} 場<extra></extra>"))
            for i, lab in enumerate(rows_):
                for j, rd in enumerate(ROUND_ORDER):
                    v, t = Z.iat[i, j], T.iat[i, j]
                    if pd.notna(v):
                        fig.add_annotation(x=rd, y=lab, text=t, showarrow=False,
                                           font=dict(size=11, color="#ffffff" if v >= 6 else INK))
            fig.update_xaxes(type="category", side="top", showgrid=False)
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            st.plotly_chart(style(fig, 90 + 34 * len(rows_)), width="stretch", config={"displayModeBar": False})
            tot = C.groupby("lab")["n"].sum().reindex(rows_)
            sweep1 = int(((C["round"] == "首輪") & (C["n"] == 4)).sum())
            n_c = len(rows_)
            lines = [f"<b>最辛苦的冠軍之路：</b>{tot.idxmax()}，四輪一共打了 {tot.max():.0f} 場；"
                     f"最輕鬆的是 {tot.idxmin()}（{tot.min():.0f} 場，最少可能是 16 場）。",
                     f"{n_c} 位冠軍裡，{sweep1} 位首輪 4 比 0 橫掃；"
                     f"{int(C.groupby('lab')['g7'].any().sum())} 位至少打過一次第 7 戰；"
                     f"{int(C.groupby('lab')['behind'].any().sum())} 位至少有一輪是落後後逆轉。"]
            insight(lines, where=slot2)

            # ===== 3 對手一輪比一輪強嗎？場數多是因為對手強嗎？ =====
            st.divider()
            slot3 = section("3　對手越強，系列賽就打越久嗎？",
                            "每個點是一個贏下來的系列賽；橫軸＝對手例行賽淨效率、縱軸＝打了幾場；★＝冠軍。"
                            "點有一點上下錯開，免得疊在一起")
            D = SR.dropna(subset=["opp_net"]).copy()
            if D.empty:
                st.info("尚未載入資料：需要全聯盟例行賽數據（league_team_seasons），請執行 python load_to_supabase.py --only league")
            else:
                jit = (D.index.to_series() % 5 - 2) * 0.06
                D["y"] = D["n"] + jit.values
                fig = go.Figure()
                O = D[D["grp"] == "其他晉級球隊"]
                fig.add_trace(go.Scatter(x=O["opp_net"], y=O["y"], mode="markers", name="其他晉級球隊",
                                         marker=dict(size=7, color="#c9c3d6", line=dict(width=0.5, color=SURFACE)),
                                         customdata=O[["season", "abbreviation", "opp", "round", "w", "l"]].values,
                                         hovertemplate="%{customdata[0]} %{customdata[1]} vs %{customdata[2]}（%{customdata[3]}）"
                                                       "<br>%{customdata[4]}-%{customdata[5]}；對手淨效率 %{x:+.1f}<extra></extra>"))
                CC = D[D["grp"] == "冠軍"]
                fig.add_trace(go.Scatter(x=CC["opp_net"], y=CC["y"], mode="markers", name="冠軍",
                                         marker=dict(symbol="star", size=13,
                                                     color=[TEAM_COLORS.get(a, ACCENT) for a in CC["abbreviation"]],
                                                     line=dict(width=1, color=SURFACE)),
                                         customdata=CC[["season", "abbreviation", "opp", "round", "w", "l"]].values,
                                         hovertemplate="★ %{customdata[0]} %{customdata[1]} vs %{customdata[2]}（%{customdata[3]}）"
                                                       "<br>%{customdata[4]}-%{customdata[5]}；對手淨效率 %{x:+.1f}<extra></extra>"))
                fig.update_xaxes(title="對手例行賽淨效率（越右越強）", zeroline=True, zerolinecolor=GRID)
                fig.update_yaxes(title="這個系列賽打了幾場", tickvals=[4, 5, 6, 7], range=[3.6, 7.4])
                fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
                st.plotly_chart(style(fig, 400), width="stretch", config={"displayModeBar": False})
                r_all = D["opp_net"].corr(D["n"])
                OPP = D[D["grp"] == "冠軍"].groupby("round")["opp_net"].mean().reindex(ROUND_ORDER)
                strength = "幾乎沒有關係" if abs(r_all) < 0.1 else ("有一點關係" if abs(r_all) < 0.3 else
                                                                 ("中等關係" if abs(r_all) < 0.5 else "很強的關係"))
                lines = [f"<b>對手越強、打越久：</b>所有贏下來的系列賽裡，對手淨效率和場數的相關係數 r = {r_all:+.2f}（{strength}）。",
                         "冠軍每一輪對手的例行賽淨效率平均："
                         + "、".join(f"{k} {fmt(v, '+.1f')}" for k, v in OPP.items()) + "。"]
                opp_up = OPP.dropna().is_monotonic_increasing and OPP.notna().sum() >= 3
                chk = ("對手一輪比一輪強：成立" if opp_up else "對手一輪比一輪強：不完全成立（有一輪的對手比前一輪弱）") + \
                      ("；而且對手越強系列賽越久，「越後面越辛苦」的原因說得通。" if r_all >= 0.1
                       else "；但對手強弱和場數關係很弱，場數多不一定是因為對手強（也可能是傷兵、主場順序）。")
                lines.append("讀法：點如果由左下往右上排，就代表對手越強、系列賽越久。"
                             "相關係數 r 介於 −1～+1，|r| 小於 0.1 幾乎沒關係、0.3 中等、0.5 以上很強。")
                insight(lines, where=slot3, check=chk)

            with st.expander("看每一位冠軍每一輪的數字"):
                tb = C.sort_values(["season", "rnd"])
                nice_table(pd.DataFrame({
                    "球季": tb["season"], "冠軍": [ALL_ZH.get(a, a) for a in tb["abbreviation"]], "_key": tb["abbreviation"],
                    "輪次": tb["round"], "對手": [ALL_ZH.get(o, o) for o in tb["opp"]],
                    "勝-敗": [f"{w_}-{l_}" for w_, l_ in zip(tb["w"], tb["l"])],
                    "曾經落後": ["是" if b_ else "" for b_ in tb["behind"]],
                    "主場優勢": ["有" if h_ else "沒有" for h_ in tb["home1"]],
                    "對手淨效率": [fmt(v, "+.1f") for v in tb["opp_net"]],
                    "對手排名": [fmt(v, ".0f") for v in tb["opp_rank"]],
                }), num_cols=("勝-敗", "對手淨效率", "對手排名"), signed_cols=("對手淨效率",), dot_col="冠軍", colors=TEAM_COLORS)
                st.caption("主場優勢＝第 1 戰在自己主場（七場裡有四場在主場）；對手排名＝對手例行賽淨效率在 30 隊裡排第幾。")


# ---------- 缺陣場的對手：少了頭號得分手的那幾場，對手比較弱嗎？（2026-11-16）----------
AO_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
AO_NUM = ["star_ppg", "team_win_pct", "with_g", "with_w", "with_opp_net", "without_g", "without_w",
          "without_opp_net", "without_last10", "with_g_weak", "with_w_weak", "with_g_strong", "with_w_strong",
          "without_g_weak", "without_w_weak", "without_g_strong", "without_w_strong"]
TERMS.update({
    "頭號得分手": ("這一季在這隊例行賽場均得分最高、至少上場 20 場的球員（和「頭號得分手缺陣」頁同一個人）", "依例行賽場均得分排名"),
    "缺陣場": ("球隊有比賽、但他沒有上場紀錄（或 0 分鐘）的比賽；不知道是受傷、輪休還是禁賽", "team_games 有這一場、player_game_stats 沒有他"),
    "對手淨效率": ("對手那一季例行賽「每 100 回合贏幾分」；正數＝比聯盟平均強、負數＝比較弱", "對手的進攻效率 − 防守效率"),
    "只和同樣強弱的對手比": ("把比賽分成「對手比聯盟平均弱」「比平均強」兩組，各自算有他／缺陣的勝率差，再依缺陣場數平均", "排除「缺陣剛好都打弱隊」的影響"),
    "最後 10 場": ("這一季自己的最後 10 場例行賽；已經確定季後賽名次的球隊，常在這時讓主力休息（季末輪休）", "依日期倒數 10 場"),
})


@st.cache_data(ttl=3600, show_spinner="讀取缺陣場對手彙總表中…")
def _read_abs_opp():
    """讀 star_absence_opp_mv（一隊一季一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("star_absence_opp_mv", ["season", "team_id"])


def load_abs_opp():
    try:
        df = _read_abs_opp()
        return df if not df.empty else None
    except Exception as e:
        VIEW_ERRORS["star_absence_opp_mv"] = f"{type(e).__name__}: {e}"[:300]
        return None


def prep_abs_opp(df, strong=0.6):
    """數字欄轉成數字、分組（冠軍／其他強隊／其他球隊）；本季還沒打完，不列入"""
    d = df.copy()
    for c in AO_NUM:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["season"].isin(set(champs["season"]))].copy()
    d["champ"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(d["season"], d["abbreviation"])]
    d["grp"] = "其他球隊"
    d.loc[(~d["champ"]) & (d["team_win_pct"] >= strong), "grp"] = "其他強隊"
    d.loc[d["champ"], "grp"] = "冠軍"
    return d


def abs_opp_groups(d):
    """各組「先加總、再除」（合併計算）：對手平均淨效率用場數加權；勝率差分兩種算法"""
    d = d.copy()
    d["w_net"] = d["with_opp_net"] * d["with_g"]
    d["wo_net"] = d["without_opp_net"].fillna(0) * d["without_g"]
    cols = ["with_g", "with_w", "w_net", "without_g", "without_w", "wo_net", "without_last10",
            "with_g_weak", "with_w_weak", "with_g_strong", "with_w_strong",
            "without_g_weak", "without_w_weak", "without_g_strong", "without_w_strong"]
    G = d.groupby("grp")[cols].sum().reindex(AO_GROUPS)
    G["n_team"] = d.groupby("grp").size().reindex(AO_GROUPS)
    pos = lambda s: s.where(s > 0)                       # 不除以 0
    G["with_net"] = G["w_net"] / pos(G["with_g"])
    G["without_net"] = G["wo_net"] / pos(G["without_g"])
    G["gap_net"] = G["without_net"] - G["with_net"]      # 負數＝缺陣場的對手比較弱
    G["raw_drop"] = (G["with_w"] / pos(G["with_g"]) - G["without_w"] / pos(G["without_g"])) * 100
    adj, wsum = 0, 0
    for b in ["weak", "strong"]:
        db = (G[f"with_w_{b}"] / pos(G[f"with_g_{b}"]) - G[f"without_w_{b}"] / pos(G[f"without_g_{b}"])) * 100
        wb = G[f"without_g_{b}"].where(db.notna(), 0)
        adj = adj + db.fillna(0) * wb
        wsum = wsum + wb
    G["adj_drop"] = adj / pos(wsum)                      # 只和同樣強弱的對手比
    G["last10"] = G["without_last10"] / pos(G["without_g"])
    G["base10"] = 10 / ((G["with_g"] + G["without_g"]) / G["n_team"]).where(lambda s: s > 0)
    return G


if PAGE == "缺陣場的對手":
    hypothesis("少了頭號得分手的那幾場，對手是不是剛好比較弱？",
               "缺陣場的對手平均比有他時弱（對手淨效率低 1 分以上），冠軍尤其明顯（季末輪休常排在打弱隊）；"
               "所以只看「有他 vs 缺陣」會低估少了他的影響——只和同樣強弱的對手比，勝率會掉得更多。")
    raw = load_abs_opp()
    if raw is None:
        st.info("尚未載入資料，請先在 Supabase 的 SQL Editor 執行 docs/sql/2026-11-16_缺陣場的對手.sql"
                "（建立 star_absence_opp_mv），再按左側「重新讀取最新資料」。")
        if VIEW_ERRORS.get("star_absence_opp_mv"):
            st.caption("讀取時的錯誤訊息：" + VIEW_ERRORS["star_absence_opp_mv"])
    else:
        AO = prep_abs_opp(raw)
        G = abs_opp_groups(AO)
        st.caption(f"例行賽、{AO['season'].nunique()} 季、{len(AO)} 個隊季；本季還沒打完，先不列入。"
                   "對手強弱用對手那一季的例行賽淨效率。")

        # ===== 1 缺陣場的對手比較弱嗎？ =====
        slot1 = section("1　缺陣場的對手比較弱嗎？",
                        "深紫＝有他上場的比賽、淺紫＝他缺陣的比賽；長條＝對手那一季的平均淨效率，越低＝對手越弱；長條上寫幾場")
        fig = go.Figure()
        for col, name, colr, ncol in [("with_net", "有他上場", ACCENT, "with_g"),
                                      ("without_net", "他缺陣", "#c4b5fd", "without_g")]:
            fig.add_trace(go.Bar(x=AO_GROUPS, y=G[col], name=name, marker_color=colr,
                                 text=[f"{fmt(v, '+.1f')}（{int(n):,} 場）" if pd.notna(v) else "-"
                                       for v, n in zip(G[col], G[ncol].fillna(0))],
                                 textposition="outside", textfont=dict(size=11, color=INK_2),
                                 hovertemplate="%{x}・" + name + "<br>對手平均淨效率 %{y:+.2f}<extra></extra>"))
        fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
        lo = min(G[["with_net", "without_net"]].min().min(), 0)
        hi = max(G[["with_net", "without_net"]].max().max(), 0)
        pad = max(0.6, (hi - lo) * 0.35)
        fig.update_yaxes(title="對手平均淨效率（每 100 回合）", range=[lo - pad, hi + pad])
        fig.update_xaxes(type="category")
        fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
        rounded(fig)
        st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})
        c_, s_, o_ = G.loc["冠軍"], G.loc["其他強隊"], G.loc["其他球隊"]
        sg = lambda v: f"{(0.0 if abs(v) < 0.05 else v):+.1f}"     # 不要出現「-0.0」
        lines, chk = [], None
        if pd.notna(c_["gap_net"]):
            lines.append(f"<b>冠軍的頭號得分手缺陣時，對手平均{'弱' if c_['gap_net'] < 0 else '強'} {abs(c_['gap_net']):.1f} 分</b>"
                         f"（每 100 回合淨效率；有他時 {sg(c_['with_net'])}、缺陣時 {sg(c_['without_net'])}，"
                         f"缺陣 {int(c_['without_g'])} 場）。")
            lines.append(f"其他強隊：缺陣場的對手{'弱' if s_['gap_net'] < 0 else '強'} {abs(s_['gap_net']):.1f} 分；"
                         f"其他球隊：{'弱' if o_['gap_net'] < 0 else '強'} {abs(o_['gap_net']):.1f} 分。")
            if pd.notna(c_["last10"]):
                lines.append(f"冠軍的缺陣場有 {c_['last10']:.0%} 在本季最後 10 場（如果平均分布，只會有約 {c_['base10']:.0%}）；"
                             f"其他強隊 {s_['last10']:.0%}、其他球隊 {o_['last10']:.0%}。")
            front = ("前半成立" if c_["gap_net"] <= -1 else
                     "前半不成立：冠軍缺陣場的對手只弱一點（不到 1 分）" if c_["gap_net"] < 0 else
                     "前半不成立：冠軍缺陣場的對手沒有比較弱")
            if front == "前半成立":
                front += f"：冠軍缺陣場的對手弱 {abs(c_['gap_net']):.1f} 分"
            more = ("冠軍比其他強隊明顯" if c_["gap_net"] < s_["gap_net"] - 0.5 else "冠軍和其他強隊差不多（差不到 0.5 分）"
                    if c_["gap_net"] <= s_["gap_net"] + 0.5 else "冠軍反而比其他強隊不明顯")
            chk = f"{front}；{more}。"
        lines.append("讀法：看同一組裡淺紫是不是比深紫低（缺陣時遇到比較弱的對手），再比較冠軍和其他強隊兩組的落差誰大。"
                     "淨效率 +5 大約是 55 勝的球隊，−5 大約是 27 勝。")
        insight(lines, where=slot1, check=chk)
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["頭號得分手", "缺陣場", "對手淨效率", "只和同樣強弱的對手比", "最後 10 場", "其他強隊"],
                       first_note="缺陣＝<b>沒有出賽紀錄</b>，不一定是受傷；季末輪休、禁賽也算。"
                                  "所以這頁只能說「缺陣場遇到的對手比較弱」，不能說「球隊故意挑弱隊讓他休息」。")

        # ===== 2 扣掉對手強弱，勝率掉多少？ =====
        st.divider()
        slot2 = section("2　扣掉對手強弱，少了他勝率掉多少？",
                        "灰＝直接比（有他的勝率 − 缺陣的勝率）、紫＝只和同樣強弱的對手比；越高＝少了他掉越多（百分點）")
        fig = go.Figure()
        for col, name, colr in [("raw_drop", "直接比", "#b3adc2"), ("adj_drop", "只和同樣強弱的對手比", ACCENT)]:
            fig.add_trace(go.Bar(x=AO_GROUPS, y=G[col], name=name, marker_color=colr,
                                 text=[fmt(v, "+.1f") for v in G[col]], textposition="outside",
                                 textfont=dict(size=11, color=INK_2),
                                 hovertemplate="%{x}・" + name + "<br>少了他勝率掉 %{y:.1f} 個百分點<extra></extra>"))
        fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
        top = max(G[["raw_drop", "adj_drop"]].max().max(), 1)
        bot = min(G[["raw_drop", "adj_drop"]].min().min(), 0)
        fig.update_yaxes(title="勝率掉幾個百分點", range=[bot - 3, top * 1.25 + 2])
        fig.update_xaxes(type="category")
        fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
        rounded(fig)
        st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
        lines, chk = [], None
        if pd.notna(c_["raw_drop"]) and pd.notna(c_["adj_drop"]):
            diff = c_["adj_drop"] - c_["raw_drop"]
            lines.append(f"<b>只和同樣強弱的對手比，冠軍少了頭號得分手勝率掉 {c_['adj_drop']:.1f} 個百分點</b>"
                         f"（直接比是 {c_['raw_drop']:.1f}，{'多掉' if diff > 0 else '少掉'} {abs(diff):.1f}）。")
            if pd.notna(s_["adj_drop"]):
                lines.append(f"其他強隊：直接比 {s_['raw_drop']:.1f}、同樣強弱 {s_['adj_drop']:.1f}；"
                             f"其他球隊：直接比 {o_['raw_drop']:.1f}、同樣強弱 {o_['adj_drop']:.1f}。")
            chk = ("後半成立：扣掉對手強弱後，冠軍掉得更多（直接比低估了少了他的影響）" if diff >= 1 else
                   "後半不成立：扣掉對手強弱後，冠軍掉得差不多（差不到 1 個百分點），缺陣場的對手強弱影響不大" if diff > -1 else
                   "後半不成立：扣掉對手強弱後，冠軍反而掉得比較少")
        lines.append("讀法：紫色比灰色高＝「缺陣剛好打弱隊」讓直接比的數字看起來比較好看；兩根差不多＝對手強弱不影響結論。"
                     "「頭號得分手缺陣」頁第 1 節用的就是灰色那種算法。")
        insight(lines, where=slot2, check=chk)

        # ===== 3 每一位冠軍 =====
        st.divider()
        slot3 = section("3　每一位冠軍：有他時 vs 缺陣時遇到的對手",
                        "灰點＝有他上場時對手的平均淨效率、彩色點＝他缺陣時；彩色點在左邊＝缺陣時遇到比較弱的對手；括號是缺陣幾場")
        C = AO[AO["grp"] == "冠軍"].sort_values("season")
        CA = C[C["without_g"] > 0]
        full = C[C["without_g"] == 0]
        if CA.empty:
            st.info("冠軍的頭號得分手都沒有缺陣，或資料還沒載入完整。")
        else:
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}　{p_}（{int(n_)} 場）" for s_, a_, p_, n_ in
                      zip(CA["season"], CA["abbreviation"], CA["player_name"], CA["without_g"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, CA.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["with_opp_net"], r_["without_opp_net"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=CA["with_opp_net"], y=labels, mode="markers", name="有他上場",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>有他時對手 %{x:+.2f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=CA["without_opp_net"], y=labels, mode="markers", name="他缺陣",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in CA["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>缺陣時對手 %{x:+.2f}<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="對手平均淨效率（左＝對手比較弱）", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 34 * len(CA)), width="stretch", config={"displayModeBar": False})
            k_weak = int((CA["without_opp_net"] < CA["with_opp_net"]).sum())
            few = int((CA["without_g"] < 5).sum())
            lines = [f"<b>{len(CA)} 位頭號得分手有缺陣過的冠軍裡，{k_weak} 位缺陣時遇到的對手比較弱。</b>",
                     f"其中 {few} 位缺陣不到 5 場，單一冠軍的點起伏很大，要以第 1 節的合計為準。"]
            if len(full):
                lines.append("整季全勤（沒有缺陣場）的冠軍：" + "、".join(
                    f"{s_} {ALL_ZH.get(a_, a_)} {p_}" for s_, a_, p_ in zip(full["season"], full["abbreviation"], full["player_name"])) + "。")
            insight(lines, where=slot3)
            with st.expander("看每一位冠軍的數字"):
                tb = pd.DataFrame({
                    "球季": C["season"], "冠軍": [ALL_ZH.get(a, a) for a in C["abbreviation"]], "_key": C["abbreviation"],
                    "頭號得分手": C["player_name"],
                    "有他": [f"{int(w)}-{int(g - w)}" for w, g in zip(C["with_w"], C["with_g"])],
                    "缺陣": [f"{int(w)}-{int(g - w)}" if g > 0 else "全勤" for w, g in zip(C["without_w"], C["without_g"])],
                    "有他時對手": [fmt(v, "+.1f") for v in C["with_opp_net"]],
                    "缺陣時對手": [fmt(v, "+.1f") for v in C["without_opp_net"]],
                    "缺陣在最後 10 場": [f"{int(x)} 場" if g > 0 else "-" for x, g in zip(C["without_last10"], C["without_g"])],
                })
                nice_table(tb, num_cols=("有他", "缺陣", "有他時對手", "缺陣時對手", "缺陣在最後 10 場"),
                           signed_cols=("有他時對手", "缺陣時對手"), dot_col="冠軍", colors=TEAM_COLORS)
                st.caption("戰績是「勝-敗」；對手欄是對手那一季例行賽的淨效率，正數＝比聯盟平均強。")


# ---------- 自動結論：用資料算出一句話，放在圖的上面 ----------
# ---------- 頭號得分手缺陣：少了頭號得分手，冠軍還贏得了嗎？（2026-11-14）----------
TERMS.update({
    "頭號得分手（本頁）": ("這一季例行賽在這一隊場均得分最高、至少上場 20 場的球員", "依例行賽場均得分排第 1"),
    "缺陣": ("球隊有比賽、但他沒有上場（沒有出賽紀錄或上場 0 分鐘）；不一定是受傷，也可能是休息、禁賽", "球隊這季的比賽 − 他有上場的比賽"),
    "缺陣時勝率": ("頭號得分手沒上場的那幾場，球隊贏了幾成", "缺陣時贏的場數 ÷ 缺陣場數"),
    "掉多少（百分點）": ("有他時的勝率 − 缺陣時的勝率；正數＝少了他就比較常輸", "70% → 55% 是掉 15 個百分點"),
})


@st.cache_data(ttl=3600, show_spinner="讀取頭號得分手缺陣彙總表中…")
def _read_star_absence():
    return fetch_all("star_absence_mv", ["team_id", "season"])


def load_star_absence():
    """讀 star_absence_mv（docs/sql/2026-11-14_頭號得分手缺陣.sql 建立）；還沒建立就回傳空表"""
    try:
        d = _read_star_absence()
    except Exception:
        return pd.DataFrame()
    if d.empty:
        return d
    for c in ["team_id", "star_gp", "star_ppg", "with_g", "with_w", "without_g", "without_w"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d


def prep_absence(sa, league_tbl, strong=0.6):
    """每隊每季一列：有他／缺陣的勝率、掉多少，再分成冠軍／其他強隊／其他球隊"""
    d = sa[sa["season"].isin(set(champs["season"]))].copy()   # 只看已經有冠軍的球季（本季還沒打完）
    d["with_pct"] = d["with_w"] / d["with_g"].where(d["with_g"] > 0)
    d["without_pct"] = d["without_w"] / d["without_g"].where(d["without_g"] > 0)
    d["drop"] = (d["with_pct"] - d["without_pct"]) * 100
    lg = league_tbl[league_tbl["season_type"] == "Regular Season"][["season", "team_id", "w", "gp"]].copy()
    for c in ["team_id", "w", "gp"]:
        lg[c] = pd.to_numeric(lg[c], errors="coerce")
    lg["season_win"] = lg["w"] / lg["gp"].where(lg["gp"] > 0)
    d = d.merge(lg[["season", "team_id", "season_win"]], on=["season", "team_id"], how="left")
    champ_ids = set(zip(champs["season"], pd.to_numeric(champs["team_id"], errors="coerce")))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    d["grp"] = "其他球隊"
    d.loc[(~d["champion"]) & (d["season_win"] >= strong), "grp"] = "其他強隊"
    d.loc[d["champion"], "grp"] = "冠軍"
    return d


ABS_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
ABS_COLORS = {"冠軍": ACCENT, "其他強隊": "#6b6480", "其他球隊": "#c9c3d6"}


if PAGE == "頭號得分手缺陣":
    hypothesis("少了頭號得分手，冠軍還贏得了嗎？冠軍是不是比其他強隊更不怕少一個人？",
               "頭號得分手缺陣時，冠軍的勝率還是在五成以上；而且掉得比其他強隊（勝率六成以上、沒奪冠）少——冠軍不是只靠一個人。")
    SA = load_star_absence()
    if SA.empty or league.empty:
        st.info("尚未載入資料：請先到 Supabase → SQL Editor 執行 docs/sql/2026-11-14_頭號得分手缺陣.sql"
                "（建立 star_absence_mv 彙總表），再按左側「重新讀取最新資料」。")
    else:
        AB = prep_absence(SA, league)
        st.caption(f"用 {AB['abbreviation'].nunique()} 隊、{AB['season'].nunique()} 季的例行賽計算；"
                   "缺陣不一定是受傷（也可能是休息、禁賽），資料庫分不出原因。")

        # ===== 1. 各組：有他 vs 缺陣 =====
        slot1 = section("1　少了頭號得分手，勝率掉多少？",
                        "把同一組所有隊季的比賽加起來：紫＝頭號得分手有上場時的勝率、淺色＝他缺陣時的勝率；"
                        "兩根長條差越多，代表越依賴他")
        G = AB.groupby("grp")[["with_w", "with_g", "without_w", "without_g"]].sum().reindex(ABS_GROUPS).dropna(how="all")
        G["with_pct"] = G["with_w"] / G["with_g"].where(G["with_g"] > 0)
        G["without_pct"] = G["without_w"] / G["without_g"].where(G["without_g"] > 0)
        G["drop"] = (G["with_pct"] - G["without_pct"]) * 100
        G["n"] = AB.groupby("grp").size().reindex(G.index)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=list(G.index), y=G["with_pct"], name="頭號得分手有上場", marker_color=ACCENT,
                             text=[f"{v:.0%}" for v in G["with_pct"]], textposition="outside", cliponaxis=False,
                             customdata=G[["with_g"]].values,
                             hovertemplate="%{x}：有他時勝率 %{y:.1%}（%{customdata[0]:.0f} 場）<extra></extra>"))
        fig.add_trace(go.Bar(x=list(G.index), y=G["without_pct"], name="頭號得分手缺陣", marker_color="#c7b3f3",
                             text=[f"{v:.0%}<br>（{n:.0f} 場）" for v, n in zip(G["without_pct"], G["without_g"])],
                             textposition="outside", cliponaxis=False,
                             hovertemplate="%{x}：缺陣時勝率 %{y:.1%}<extra></extra>"))
        rounded(fig)
        fig.add_hline(y=0.5, line=dict(color=MUTED, dash="dot", width=1))
        fig.update_layout(barmode="group")
        fig.update_xaxes(type="category")
        fig.update_yaxes(title="勝率（虛線＝五成）", tickformat=".0%", range=[0, 1.05])
        st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})
        if "冠軍" in G.index and pd.notna(G.loc["冠軍", "without_pct"]):
            c_ = G.loc["冠軍"]
            lines = [f"冠軍的頭號得分手缺陣時，勝率從 {c_['with_pct']:.0%} 變成 {c_['without_pct']:.0%}"
                     f"（掉 {c_['drop']:.0f} 個百分點，{c_['without_g']:.0f} 場）。"]
            for g_ in ["其他強隊", "其他球隊"]:
                if g_ in G.index and pd.notna(G.loc[g_, "drop"]):
                    lines.append(f"{g_}：{G.loc[g_, 'with_pct']:.0%} → {G.loc[g_, 'without_pct']:.0%}"
                                 f"（掉 {G.loc[g_, 'drop']:.0f} 個百分點，{G.loc[g_, 'without_g']:.0f} 場）。")
            front = "前半成立" if c_["without_pct"] >= 0.5 else "前半不成立"
            if "其他強隊" in G.index and pd.notna(G.loc["其他強隊", "drop"]):
                s_drop = G.loc["其他強隊", "drop"]
                back = ("後半成立：冠軍掉得比其他強隊少" if c_["drop"] < s_drop - 2 else
                        "後半不成立：冠軍和其他強隊掉得差不多（差不到 2 個百分點）" if c_["drop"] <= s_drop + 2 else
                        "後半不成立：冠軍掉得比其他強隊多")
            else:
                back = "後半無法判斷（沒有其他強隊的資料）"
            insight(lines, where=slot1,
                    check=f"{front}：缺陣時勝率 {c_['without_pct']:.0%}；{back}。")
        else:
            insight(["資料不足：冠軍的頭號得分手幾乎沒有缺陣紀錄。"], where=slot1)
        with st.expander("名詞小辭典"):
            term_table(["頭號得分手（本頁）", "缺陣", "缺陣時勝率", "掉多少（百分點）", "其他強隊"],
                       first_note="缺陣＝沒有出賽紀錄，不一定是受傷；缺陣場數常常不到 10 場，單一冠軍的勝率起伏會很大，看各組合計比較可靠。")

        # ===== 2. 每一位冠軍 =====
        st.divider()
        slot2 = section("2　每一位冠軍：有他 → 缺陣",
                        "一列一位冠軍：灰點＝頭號得分手有上場時的勝率、彩色點＝他缺陣時的勝率；括號是缺陣幾場，"
                        "整季全勤的冠軍只有灰點")
        C = AB[AB["champion"]].sort_values("season").copy()
        C["label"] = [f"{s_} {ALL_ZH.get(a_, a_)}　{n_}" for s_, a_, n_ in
                      zip(C["season"], C["abbreviation"], C["player_name"])]
        fig = go.Figure()
        for _, r_ in C.iterrows():
            if pd.notna(r_["without_pct"]):
                fig.add_trace(go.Scatter(x=[r_["with_pct"], r_["without_pct"]], y=[r_["label"]] * 2, mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=C["with_pct"], y=C["label"], mode="markers", name="有上場",
                                 marker=dict(size=11, color="#8f889f", line=dict(width=1, color=SURFACE)),
                                 customdata=C[["with_w", "with_g"]].values,
                                 hovertemplate="%{y}<br>有上場：%{customdata[0]:.0f} 勝 / %{customdata[1]:.0f} 場（%{x:.0%}）<extra></extra>"))
        M = C.dropna(subset=["without_pct"])
        fig.add_trace(go.Scatter(x=M["without_pct"], y=M["label"], mode="markers+text", name="缺陣",
                                 text=[f"（{n:.0f} 場）" for n in M["without_g"]], textposition="middle right",
                                 textfont=dict(size=11, color=INK_2),
                                 marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in M["abbreviation"]],
                                             line=dict(width=1.5, color=SURFACE)),
                                 customdata=M[["without_w", "without_g"]].values,
                                 hovertemplate="%{y}<br>缺陣：%{customdata[0]:.0f} 勝 / %{customdata[1]:.0f} 場（%{x:.0%}）<extra></extra>"))
        fig.add_vline(x=0.5, line=dict(color=MUTED, dash="dot", width=1))
        fig.update_xaxes(title="勝率（虛線＝五成）", tickformat=".0%", range=[0, 1.12])
        fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
        st.plotly_chart(style(fig, 100 + 30 * len(C)), width="stretch", config={"displayModeBar": False})
        full = C[C["without_g"].fillna(0) == 0]
        few = M[M["without_g"] < 5]
        win5 = int((M["without_pct"] >= 0.5).sum())
        lines = [f"{len(M)} 位有缺陣紀錄的冠軍裡，{win5} 位在頭號得分手缺陣時仍然贏五成以上。"]
        if len(M):
            worst = M.loc[M["drop"].idxmax()]
            lines.append(f"掉最多：{worst['season']} {ALL_ZH.get(worst['abbreviation'], worst['abbreviation'])}"
                         f"（{worst['player_name']} 缺陣 {worst['without_g']:.0f} 場，"
                         f"{worst['with_pct']:.0%} → {worst['without_pct']:.0%}）。")
        if len(full):
            lines.append("整季全勤（沒有缺陣）：" + "、".join(f"{s_} {n_}" for s_, n_ in zip(full["season"], full["player_name"])) + "。")
        if len(few):
            lines.append(f"其中 {len(few)} 位只缺陣 1～4 場，勝率一場就差 20～100 個百分點，不要只看單一冠軍下結論。")
        insight(lines, where=slot2)

        with st.expander("看每一位冠軍的數字"):
            T = C.copy()
            T["有上場"] = [f"{w:.0f} 勝 {g - w:.0f} 敗" for w, g in zip(T["with_w"], T["with_g"])]
            T["缺陣"] = [("全勤" if g == 0 else f"{w:.0f} 勝 {g - w:.0f} 敗") for w, g in zip(T["without_w"], T["without_g"])]
            T["掉多少"] = [("-" if pd.isna(v) else f"{v:+.0f}") for v in T["drop"]]
            T = T.rename(columns={"season": "球季", "player_name": "頭號得分手"})
            T["冠軍"] = T["abbreviation"].map(team_label)
            T["場均得分"] = T["star_ppg"].map(lambda v: f"{v:.1f}")
            T["_key"] = T["abbreviation"]
            nice_table(T[["球季", "冠軍", "_key", "頭號得分手", "場均得分", "有上場", "缺陣", "掉多少"]],
                       num_cols=("場均得分", "有上場", "缺陣", "掉多少"), signed_cols=(), dot_col="冠軍", colors=TEAM_COLORS)
            st.caption("掉多少＝有上場時的勝率 − 缺陣時的勝率（百分點）；正數＝少了他比較常輸。")

        # ===== 3. 全聯盟：越常缺陣，掉越多嗎？ =====
        st.divider()
        slot3 = section("3　放到全聯盟：越依賴頭號得分手的隊，少了他掉越多嗎？",
                        "每個點是一隊一季（缺陣至少 5 場）：橫軸＝頭號得分手的場均得分、縱軸＝少了他勝率掉幾個百分點；★ 是冠軍")
        L = AB[AB["without_g"] >= 5].dropna(subset=["drop", "star_ppg"])
        if len(L) < 10:
            insight(["資料不足：缺陣至少 5 場的隊季還不到 10 個。"], where=slot3)
        else:
            fig = go.Figure()
            for g_ in ["其他球隊", "其他強隊"]:
                o_ = L[L["grp"] == g_]
                fig.add_trace(go.Scatter(x=o_["star_ppg"], y=o_["drop"], mode="markers", name=g_,
                                         marker=dict(size=7, color=ABS_COLORS[g_], opacity=0.8, line=dict(width=0.5, color=SURFACE)),
                                         text=[f"{s_} {team_label(a_)}　{n_}" for s_, a_, n_ in zip(o_["season"], o_["abbreviation"], o_["player_name"])],
                                         hovertemplate="%{text}<br>場均 %{x:.1f} 分　掉 %{y:+.0f} 個百分點<extra></extra>"))
            c_ = L[L["champion"]]
            fig.add_trace(go.Scatter(x=c_["star_ppg"], y=c_["drop"], mode="markers", name="冠軍",
                                     marker=dict(symbol="star", size=15, color=ACCENT, line=dict(width=1, color=SURFACE)),
                                     text=[f"{s_} {team_label(a_)}　{n_}" for s_, a_, n_ in zip(c_["season"], c_["abbreviation"], c_["player_name"])],
                                     hovertemplate="★ %{text}<br>場均 %{x:.1f} 分　掉 %{y:+.0f} 個百分點<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=INK_2, width=1))
            fig.update_xaxes(title="頭號得分手場均得分")
            fig.update_yaxes(title="少了他勝率掉幾個百分點（正＝掉）")
            st.plotly_chart(style(fig, 420), width="stretch", config={"displayModeBar": False})
            r_ = L["star_ppg"].corr(L["drop"])
            neg = int((L["drop"] < 0).sum())
            insight(where=slot3, lines=[
                f"{len(L)} 個隊季裡，頭號得分手場均得分和「少了他掉多少」的相關係數 r = {r_:.2f}（{corr_word(r_)}）。",
                f"有 {neg} 個隊季（{neg / len(L):.0%}）少了頭號得分手反而贏比較多——缺陣場數少時，對手強弱、運氣影響很大。",
                "讀法：點越往右上，代表球星得分越多、少了他掉越多；如果點是一團、沒有往右上斜，就代表「得分最多的人」不一定是球隊最少不了的人。",
            ])


def _diff_txt(v, f):
    return f"{v * 100:+.1f} 個百分點" if "%" in f else f"{v:+.2f}"


def trend_findings(ts, col, f, name):
    """球季趨勢：奪冠球季和其他球季差多少、奪冠那季在所選球隊裡排第幾、整體趨勢"""
    out = []
    d = ts.dropna(subset=[col])
    if d.empty:
        return ["這個條件沒有資料。"]
    ch, ot = d[d["champion"]][col], d[~d["champion"]][col]
    if len(ch) and len(ot):
        out.append(f"<b>奪冠球季</b>的{name}平均 {fmt(ch.mean(), f)}，其他球季平均 {fmt(ot.mean(), f)}，"
                   f"差 {_diff_txt(ch.mean() - ot.mean(), f)}。")
        low = "越少越好" in name   # 例如失誤：數字小才是好
        d = d.assign(rk=d.groupby("season")[col].rank(ascending=low, method="min"))
        c = d[d["champion"]]
        out.append(f"{len(c)} 個奪冠球季中，有 <b>{int((c['rk'] == 1).sum())}</b> 個是當季所選球隊裡{name}"
                   f"{'最少' if low else '最高'}的。")
    by = d.groupby("season")[col].mean()
    if len(by) >= 2:
        out.append(f"所選球隊的平均從 {by.index[0]} 的 {fmt(by.iloc[0], f)} 變成 {by.index[-1]} 的 {fmt(by.iloc[-1], f)}。")
    return out


def heat_findings(pv, f, name):
    """熱力圖：最高與最低的格子、奪冠球季是不是當季最高"""
    st_ = pv.stack().dropna()
    if st_.empty:
        return ["這個條件沒有資料。"]
    (ha, hs), (la, ls) = st_.idxmax(), st_.idxmin()
    out = [f"最高：<b>{team_label(ha)} {hs}</b>（{fmt(st_.max(), f)}）；最低：{team_label(la)} {ls}（{fmt(st_.min(), f)}）。"]
    top = pv.idxmax(axis=0).dropna()
    champ_cols = [(s_, a_) for s_, a_ in CHAMP_SET if s_ in pv.columns and a_ in pv.index]
    if champ_cols:
        hit = sum(1 for s_, a_ in champ_cols if top.get(s_) == a_)
        out.append(f"表上 {len(champ_cols)} 個奪冠球季（★）中，有 <b>{hit}</b> 個是那一季這一欄顏色最深的。"
                   + ("所以這個指標和奪冠很有關。" if hit >= len(champ_cols) * 0.6 else "所以光看這個指標，猜不到誰會奪冠。"))
    return out


def champ_findings(cr, ts, col, f, name):
    """冠軍球季比較：幾位冠軍在奪冠那季比自己其他球季好"""
    diffs = []
    for _, r in cr.iterrows():
        o = ts[(ts["abbreviation"] == r["abbreviation"]) & (~ts["champion"])][col].mean()
        if pd.notna(o) and pd.notna(r[col]):
            diffs.append((r["label"], r[col] - o))
    if not diffs:
        return ["範圍內沒有可以比較的球季。"]
    low = "越少越好" in name
    up = sum(1 for _, v in diffs if (v < 0 if low else v > 0))
    big = (min if low else max)(diffs, key=lambda x: x[1])
    return [f"{len(diffs)} 個奪冠球季中，有 <b>{up}</b> 個的{name}比同隊其他球季{'少' if low else '高'}。",
            f"差距最大：<b>{big[0]}</b>（{_diff_txt(big[1], f)}）。"
            + ("奪冠那季通常是這支球隊的高峰。" if up >= len(diffs) * 0.7 else "奪冠不一定是這項數字的高峰。")]


# ---------- 1. 球季趨勢 ----------
# ---------- 防守端：冠軍的防守強在哪裡？（2026-11-09 新增）----------
# 只用 league_team_seasons（全聯盟 30 隊每季，本來就有對手數據），不需要新的 SQL
DEF_ITEMS = {  # 名稱: (欄位, 數值越高越好?, 格式)
    "防守效率": ("def_rating", False, "num1"),
    "對手有效命中率": ("opp_efg", False, "pct"),
    "對手三分出手比例": ("opp_3par", False, "pct"),
    "對手三分命中率": ("opp_3p", False, "pct"),
    "逼對手失誤率": ("forced_tov", True, "pct"),
    "防守籃板率": ("dreb_pct", True, "pct"),
    "抄截（每 100 回合）": ("stl100", True, "num1"),
    "阻攻（每 100 回合）": ("blk100", True, "num1"),
}
DEF_FACTORS = [n for n in DEF_ITEMS if n != "防守效率"]   # 防守效率是「總成績」，其他是「拆開來的原因」
TERMS.update({
    "對手有效命中率": ("對手每次出手的命中率，三分球多算半顆（因為多 1 分），數字越低＝防守讓對手投得越差",
                 "（對手命中 ＋ 0.5 × 對手三分命中）÷ 對手出手"),
    "對手三分出手比例": ("對手全部出手中三分球佔幾成；越低＝越不讓對手投三分", "對手三分出手 ÷ 對手出手"),
    "對手三分命中率": ("對手三分球投進的比例；越低＝對手三分投不進", "對手三分命中 ÷ 對手三分出手"),
    "逼對手失誤率": ("每 100 個防守回合，逼出對手幾次失誤（抄截、走步、出界…）", "對手失誤 ÷ 防守回合"),
    "防守回合": ("對手進攻了幾次；網站用 NBA 官方的防守效率反推，不另外估計", "對手得分 ÷ 防守效率 × 100"),
    "聯盟排名（本頁）": ("同一季例行賽 30 隊裡排第幾，1＝防守這一項最好（對手數字越低越好的項目，最低是第 1）", "每一季各自排名，不同年代才能比"),
})


def prep_defense(lg):
    """全聯盟每隊每季（例行賽）的防守項目＋同季聯盟排名＋和同季平均的差"""
    d = lg[lg["season_type"] == "Regular Season"].copy()
    num = ["gp", "w", "stl", "blk", "dreb_pct", "def_rating",
           "opp_pts", "opp_fgm", "opp_fga", "opp_fg3m", "opp_fg3a", "opp_tov"]
    for c in num:
        d[c] = pd.to_numeric(d[c], errors="coerce") if c in d else float("nan")
    d = d[d["opp_fga"] > 0].copy()
    if d.empty:
        return d
    d["poss"] = d["opp_pts"] / d["def_rating"].where(d["def_rating"] > 0) * 100   # 防守回合（官方防守效率反推）
    d["opp_efg"] = (d["opp_fgm"] + 0.5 * d["opp_fg3m"]) / d["opp_fga"]
    d["opp_3par"] = d["opp_fg3a"] / d["opp_fga"]
    d["opp_3p"] = d["opp_fg3m"] / d["opp_fg3a"].where(d["opp_fg3a"] > 0)
    d["forced_tov"] = d["opp_tov"] / d["poss"]
    d["stl100"] = d["stl"] / d["poss"] * 100
    d["blk100"] = d["blk"] / d["poss"] * 100
    if d["dreb_pct"].max() > 1.5:          # 保險絲：百分比存成 75 而不是 0.75 時
        d["dreb_pct"] = d["dreb_pct"] / 100
    d["w_pct"] = d["w"] / d["gp"].where(d["gp"] > 0)
    for name, (col, hb, _) in DEF_ITEMS.items():
        d[f"rk_{col}"] = d.groupby("season")[col].rank(ascending=not hb, method="min")
        # 和同季平均的差；「越低越好」的項目乘 −1，讓正數永遠＝比聯盟好
        d[f"g_{col}"] = (d[col] - d.groupby("season")[col].transform("mean")) * (1 if hb else -1)
    champ_ids = set(zip(champs["season"], champs["team_id"]))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    return d[d["season"].isin(set(champs["season"]))]   # 只留已經有冠軍的球季（本季還沒打完，不列入）


def def_show(v, kind):
    if pd.isna(v):
        return "-"
    return f"{v * 100:.1f}%" if kind == "pct" else f"{v:.1f}"


if PAGE == "防守端":
    hypothesis("冠軍的防守強在哪裡？是讓對手投不準、逼對手失誤，還是把籃板搶下來？",
               "冠軍防守最一致的強項是「讓對手投不準」（對手有效命中率排聯盟前 10），不是逼失誤或搶籃板；"
               "三分也一樣：冠軍不一定讓對手少投三分，而是讓對手三分投不進。")
    DF = prep_defense(league) if not league.empty else pd.DataFrame()
    if DF.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py --only league（全聯盟每季數據與對手數據還沒有寫進資料庫）")
    else:
        DCH = DF[DF["champion"]].sort_values("season")
        st.caption(f"全聯盟 30 隊的例行賽數據（{DF['season'].min()}～{DF['season'].max()}，共 {len(DCH)} 位冠軍）；"
                   "排名都是同一季 30 隊裡排第幾，1＝這一項防守最好。")
        if DCH.empty:
            st.info("資料不足：全聯盟數據裡還沒有冠軍球季。")
        else:
            # ===== 1. 冠軍在每一項防守排第幾 =====
            slot1 = section("1　冠軍在每一項防守排聯盟第幾？",
                            "長條＝排進聯盟前 10 的冠軍佔幾成，越長越是冠軍的共同點；右邊數字是排名中位數。"
                            "最上面的「防守效率」是總成績，下面 7 項是拆開來的原因")
            rows = []
            for name in DEF_ITEMS:
                r = DCH[f"rk_{DEF_ITEMS[name][0]}"].dropna()
                rows.append({"name": name, "top10": (r <= 10).mean() if len(r) else float("nan"),
                             "med": r.median() if len(r) else float("nan"), "n": len(r)})
            S1 = pd.DataFrame(rows)
            S1 = pd.concat([S1[S1["name"] == "防守效率"],
                            S1[S1["name"] != "防守效率"].sort_values("top10", ascending=False)])
            fig = go.Figure(go.Bar(
                x=S1["top10"], y=S1["name"], orientation="h",
                marker_color=[INK_2 if n == "防守效率" else ACCENT for n in S1["name"]],
                text=[f"中位數第 {m:.0f} 名" if pd.notna(m) else "-" for m in S1["med"]],
                textposition="outside", cliponaxis=False, textfont=dict(color=INK_2),
                customdata=S1[["n"]].values,
                hovertemplate="%{y}<br>排進前 10 的冠軍：%{x:.0%}（共 %{customdata[0]} 位）<extra></extra>"))
            rounded(fig)
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="排進聯盟前 10 的冠軍比例", tickformat=".0%", range=[0, 1.18],
                             showgrid=True, gridcolor=GRID)
            st.plotly_chart(style(fig, 70 + 42 * len(S1)), width="stretch", config={"displayModeBar": False})
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["防守效率", "對手有效命中率", "對手三分出手比例", "對手三分命中率", "逼對手失誤率",
                            "防守籃板率", "防守回合", "聯盟排名（本頁）"],
                           first_note="這一頁只比「整季平均」：league_team_seasons 只有對手的得分、出手、三分、失誤，"
                                      "沒有對手罰球，所以「讓對手少上罰球線」這一項目前算不出來。")
            fac = S1[S1["name"] != "防守效率"].dropna(subset=["top10"])
            best = fac.iloc[0] if len(fac) else None
            de = S1[S1["name"] == "防守效率"].iloc[0]
            lines = []
            if best is not None:
                lines.append(f"冠軍防守最一致的強項是<b>{best['name']}</b>："
                             f"{best['top10']:.0%} 的冠軍排進聯盟前 10（中位數第 {best['med']:.0f} 名）。")
            lines.append(f"總成績「防守效率」有 {de['top10']:.0%} 的冠軍排進前 10（中位數第 {de['med']:.0f} 名）。")
            efg = S1.set_index("name").loc["對手有效命中率"]
            tov = S1.set_index("name").loc["逼對手失誤率"]
            reb = S1.set_index("name").loc["防守籃板率"]
            check = None
            if pd.notna(efg["top10"]):
                if best is not None and best["name"] == "對手有效命中率":
                    verdict = "成立"
                elif efg["top10"] > max(tov["top10"], reb["top10"]):
                    verdict = "部分成立（比逼失誤、搶籃板一致，但不是最一致的一項）"
                else:
                    verdict = "不成立"
                check = (f"前半句{verdict}：對手有效命中率 {efg['top10']:.0%} 排前 10，"
                         f"逼對手失誤率 {tov['top10']:.0%}、防守籃板率 {reb['top10']:.0%}。")
            insight(lines, where=slot1, check=check)

            # ===== 2. 交叉驗證：哪一項最影響防守效率（全聯盟）=====
            st.divider()
            slot2 = section("2　放到全聯盟看：哪一項最影響防守好壞？",
                            "每一項「比同季平均好多少」和「防守效率比同季平均好多少」的相關係數；用全聯盟每隊每季算，不只冠軍。"
                            "長條越長，代表這一項做得好，整體防守就越好")
            rr = []
            for name in DEF_FACTORS:
                col = DEF_ITEMS[name][0]
                x_ = DF[[f"g_{col}", "g_def_rating"]].dropna()
                rr.append({"name": name, "r": x_[f"g_{col}"].corr(x_["g_def_rating"]) if len(x_) > 10 else float("nan"),
                           "n": len(x_)})
            R2 = pd.DataFrame(rr).sort_values("r", ascending=False)
            fig = go.Figure(go.Bar(
                x=R2["r"], y=R2["name"], orientation="h",
                marker_color=[ACCENT if (pd.notna(v) and v >= 0.3) else "#c9c3d6" for v in R2["r"]],
                text=[f"r = {v:+.2f}" if pd.notna(v) else "-" for v in R2["r"]],
                textposition="outside", cliponaxis=False, textfont=dict(color=INK_2),
                hovertemplate="%{y}<br>和防守效率的相關係數 %{x:+.2f}<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1))
            rounded(fig)
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="相關係數 r（正數＝這一項好，防守效率也好）", range=[-0.45, 1.15],
                             showgrid=True, gridcolor=GRID)
            st.plotly_chart(style(fig, 70 + 42 * len(R2)), width="stretch", config={"displayModeBar": False})
            top_r = R2.dropna(subset=["r"])
            lines = []
            if len(top_r):
                t_ = top_r.iloc[0]
                lines.append(f"全聯盟來看，和防守好壞最有關的是<b>{t_['name']}</b>（r = {t_['r']:+.2f}，"
                             f"{int(t_['n'])} 個隊季）。")
                strong = [n for n, v in zip(top_r["name"], top_r["r"]) if v >= 0.3]
                if strong:
                    lines.append("相關係數 0.3 以上（中等以上）的項目：" + "、".join(strong) + "。")
                lines.append("讀法：第 1 節看「冠軍做得好的是哪一項」，這一節看「哪一項真的會讓防守變好」；"
                             "兩邊都排在最上面的那一項，才是冠軍防守的關鍵。相關係數 0.1 弱、0.3 中、0.5 以上強。")
            insight(lines, where=slot2)

            # ===== 3. 每一位冠軍 =====
            st.divider()
            slot3 = section("3　每一位冠軍的防守：排名一覽",
                            "一列一位冠軍、一欄一項防守，格子是聯盟排名；顏色越深排名越前面（1＝最好）")
            labels = [f"{s_} {team_label(a_)}" for s_, a_ in zip(DCH["season"], DCH["abbreviation"])]
            names = list(DEF_ITEMS)
            zr = [[DCH.loc[idx, f"rk_{DEF_ITEMS[n][0]}"] for n in names] for idx in DCH.index]
            fig = go.Figure(go.Heatmap(
                z=zr, x=names, y=labels, zmin=1, zmax=30,
                colorscale=[[i / (len(PURPLE_RAMP) - 1), c] for i, c in enumerate(PURPLE_RAMP[::-1])],
                xgap=3, ygap=3, showscale=False,
                hovertemplate="%{y}<br>%{x}：聯盟第 %{z:.0f} 名<extra></extra>"))
            for i, lab in enumerate(labels):
                for j, n in enumerate(names):
                    v = zr[i][j]
                    if pd.isna(v):
                        continue
                    fig.add_annotation(x=n, y=lab, showarrow=False, text=f"{int(v)}",
                                       font=dict(size=11, color="#ffffff" if v <= 8 else INK))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(type="category", showgrid=False, side="top", tickangle=0)
            st.plotly_chart(style(fig, 110 + 30 * len(labels)), width="stretch", config={"displayModeBar": False})
            zdf = pd.DataFrame(zr, columns=names, index=labels)
            n_top10_eff = int((zdf["防守效率"] <= 10).sum())
            weak = zdf[zdf["防守效率"] > 10]
            lines = [f"{len(zdf)} 位冠軍裡有 <b>{n_top10_eff}</b> 位的防守效率排進聯盟前 10。"]
            if len(weak):
                lines.append("防守效率沒進前 10 的冠軍：" + "、".join(f"{l}（第 {int(v)}）" for l, v in weak["防守效率"].items())
                             + "——這幾隊多半是靠進攻奪冠，可以到「冠軍密碼」Q1 對照進攻效率。")
            insight(lines, where=slot3)

            # ===== 4. 延伸：對手三分，少讓投還是投不進？ =====
            st.divider()
            slot4 = section("4　延伸：對手三分，是「少讓投」還是「投不進」？",
                            "每個點是一隊一季：橫軸＝對手三分出手比例比同季平均少多少、縱軸＝對手三分命中率比同季平均低多少（都是百分點，"
                            "正數＝防守比較好）；★ 是冠軍。右上＝少讓投又投不進，左上＝讓對手投、但對手投不進")
            fig = go.Figure()
            oth = DF[~DF["champion"]].dropna(subset=["g_opp_3par", "g_opp_3p"])
            fig.add_trace(go.Scatter(
                x=oth["g_opp_3par"] * 100, y=oth["g_opp_3p"] * 100, mode="markers", name="其他隊季",
                marker=dict(size=6, color="#d9d3e6"),
                customdata=oth[["season", "abbreviation"]].values,
                hovertemplate="%{customdata[0]} %{customdata[1]}<br>少讓投 %{x:+.1f}、投不進 %{y:+.1f} 百分點<extra></extra>"))
            ch4 = DCH.dropna(subset=["g_opp_3par", "g_opp_3p"])
            fig.add_trace(go.Scatter(
                x=ch4["g_opp_3par"] * 100, y=ch4["g_opp_3p"] * 100, mode="markers", name="冠軍",
                marker=dict(size=15, symbol="star", color=[TEAM_COLORS.get(a, ACCENT) for a in ch4["abbreviation"]],
                            line=dict(width=1, color=SURFACE)),
                customdata=[[s_, ALL_ZH.get(a_, a_)] for s_, a_ in zip(ch4["season"], ch4["abbreviation"])],
                hovertemplate="★ %{customdata[0]} %{customdata[1]}<br>少讓投 %{x:+.1f}、投不進 %{y:+.1f} 百分點<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_xaxes(title="對手三分出手比例：比同季平均少幾個百分點（→ 越不讓投）", zeroline=False)
            fig.update_yaxes(title="對手三分命中率：比同季平均低幾個百分點（↑ 越投不進）", zeroline=False)
            fig.update_layout(legend=dict(orientation="h", y=1.06, x=0))
            st.plotly_chart(style(fig, 460), width="stretch", config={"displayModeBar": False})
            n4 = len(ch4)
            if n4:
                less = int((ch4["g_opp_3par"] > 0).sum())
                miss = int((ch4["g_opp_3p"] > 0).sum())
                both = int(((ch4["g_opp_3par"] > 0) & (ch4["g_opp_3p"] > 0)).sum())
                lines = [f"{n4} 位冠軍裡，<b>{miss}</b> 位讓對手三分投得比同季平均差，"
                         f"<b>{less}</b> 位讓對手少投三分（兩者都有：{both} 位）。"]
                r3 = DF[["g_opp_3p", "g_opp_3par", "g_def_rating"]].dropna()
                if len(r3) > 10:
                    lines.append(f"全聯盟來看，對手三分命中率和防守效率的相關 r = {r3['g_opp_3p'].corr(r3['g_def_rating']):+.2f}，"
                                 f"對手三分出手比例 r = {r3['g_opp_3par'].corr(r3['g_def_rating']):+.2f}。")
                lines.append("注意：對手三分命中率有很大一部分是運氣（對手空檔投不進也算），"
                             "要知道是不是防守逼出來的，需要「防守者距離」資料（目前沒有）。")
                check = (("後半句成立" if miss > less else "後半句不成立")
                         + f"：讓對手投不進的冠軍（{miss} 位）{'比' if miss > less else '沒有比'}讓對手少投的（{less} 位）多。")
                insight(lines, where=slot4, check=check)

            with st.expander("看每一位冠軍的實際數字"):
                nice_table(pd.DataFrame({
                    "球季": DCH["season"], "冠軍": [ALL_ZH.get(a, a) for a in DCH["abbreviation"]], "_key": DCH["abbreviation"],
                    "防守效率": [def_show(v, "num1") for v in DCH["def_rating"]],
                    "對手有效命中率": [def_show(v, "pct") for v in DCH["opp_efg"]],
                    "對手三分出手比例": [def_show(v, "pct") for v in DCH["opp_3par"]],
                    "對手三分命中率": [def_show(v, "pct") for v in DCH["opp_3p"]],
                    "逼對手失誤率": [def_show(v, "pct") for v in DCH["forced_tov"]],
                    "防守籃板率": [def_show(v, "pct") for v in DCH["dreb_pct"]],
                }), num_cols=("防守效率", "對手有效命中率", "對手三分出手比例", "對手三分命中率", "逼對手失誤率", "防守籃板率"),
                    dot_col="冠軍", colors=TEAM_COLORS)


if PAGE == "球季趨勢":
    tr_slot = section(f"{metric_name}：各隊逐季變化", "★ 是該隊奪冠的球季；選擇聚焦球隊，其他球隊會變成灰色背景，線條就不會互相干擾")
    insight(trend_findings(team_season, metric, mfmt, metric_name), where=tr_slot)
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
    hm_slot = section(f"{metric_name}：球隊 × 球季交叉表", "顏色越深數值越高；★ 是奪冠球季；空白代表該季沒有這類比賽")
    pivot = team_season.pivot(index="abbreviation", columns="season", values=metric)
    pivot = pivot.reindex(index=[a for a in teams_sel if a in pivot.index], columns=seasons)
    insight(heat_findings(pivot, mfmt, metric_name), where=hm_slot)
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
        insight(champ_findings(champ_rows, team_season, metric, mfmt, metric_name))
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

# ---------- 奪冠隔年：冠軍隔年還強嗎？（2026-11-07 補做）----------
TERMS.update({
    "比同季平均（淨效率）": ("這隊的淨效率減掉同一季 30 隊的平均；+5 代表每 100 回合比一般球隊多贏 5 分", "淨效率 − 同季 30 隊平均"),
    "回歸平均": ("特別好的一季，隔年通常會往平均靠一點（運氣、傷病、對手針對）。所以要和「同樣強的球隊」比，才知道冠軍是不是特別掉", "用全部球隊畫一條「今年 → 隔年」的直線當基準"),
    "比預期多掉幾分": ("冠軍隔年的實際數字，減掉「同樣強的球隊隔年平均會在哪裡」（直線上的值）；負數＝掉得比一般強隊多", "實際 − 直線預測"),
})


def rp_prep(lg):
    """例行賽每一隊每一季：勝率、淨效率比同季平均、同季名次，接上「隔年」同一隊的數字"""
    d = lg[lg["season_type"] == "Regular Season"].copy()
    for c in ["w", "gp", "net_rating", "off_rating", "def_rating"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["net_rating", "gp"])
    d = d[d["gp"] > 0]
    d["win"] = d["w"] / d["gp"]
    d["net_d"] = d["net_rating"] - d.groupby("season")["net_rating"].transform("mean")
    d["net_rk"] = d.groupby("season")["net_rating"].rank(ascending=False, method="min")
    seasons = sorted(d["season"].unique())
    done = set(lg.loc[lg["season_type"] == "Playoffs", "season"])          # 有季後賽＝這一季打完了
    nxt = {s: seasons[i + 1] for i, s in enumerate(seasons[:-1])}
    d["next_season"] = d["season"].map(nxt)
    cols = ["season", "team_id", "win", "net_d", "net_rk"]
    n = d[cols].rename(columns={"season": "next_season", "win": "win_n", "net_d": "net_d_n", "net_rk": "net_rk_n"})
    d = d.merge(n, on=["next_season", "team_id"], how="left")
    d = d[d["next_season"].isin(done)].dropna(subset=["net_d_n"])          # 隔年要打完才算
    d["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(d["season"], d["abbreviation"])]
    d["grp"] = "其他球隊"
    d.loc[(~d["champion"]) & (d["win"] >= 0.6), "grp"] = "其他強隊"
    d.loc[d["champion"], "grp"] = "冠軍"
    return d


RP_METRIC = {"淨效率（比同季平均）": ("net_d", "net_d_n", "{:+.1f}", "淨效率比同季平均（分／100 回合）"),
             "勝率": ("win", "win_n", "{:.0%}", "勝率"),
             "淨效率名次": ("net_rk", "net_rk_n", "第 {:.0f}", "淨效率同季名次（1＝最好）")}

if PAGE == "奪冠隔年":
    hypothesis("拿到冠軍的隔年，球隊還一樣強嗎？會不會有「冠軍宿醉」？",
               "冠軍隔年會退步（淨效率比同季平均少 2 分以上），但退步幅度和同樣強的其他球隊差不多——只是「回歸平均」，"
               "不是冠軍特別掉；而且一半以上的冠軍隔年仍是淨效率前 5 名。")
    LG = league if isinstance(league, pd.DataFrame) else pd.DataFrame()
    if LG.empty or "net_rating" not in LG.columns:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（league_team_seasons 全聯盟每季數據還沒有寫進資料庫）")
    else:
        RP = rp_prep(LG)
        C = RP[RP["grp"] == "冠軍"].sort_values("season")
        st.caption(f"只看例行賽；{RP['season'].nunique()} 個「今年 → 隔年」，{len(C)} 位冠軍（最近一位冠軍的隔年還沒打完，先不列入）。")
        if C.empty:
            st.info("還沒有「冠軍隔年」已經打完的資料。")
        else:
            # ===== 1 各組：今年 → 隔年 =====
            slot1 = section("1　冠軍隔年掉多少？和其他強隊比",
                            "灰點＝今年、彩色點＝隔年；冠軍、其他強隊（勝率六成以上、沒奪冠）、其他球隊各一列，點旁是隔年 − 今年")
            mname = seg("看哪一項", list(RP_METRIC), key="rp_metric")
            a_, b_, f_, axis_ = RP_METRIC[mname]
            G = RP.groupby("grp").agg(a=(a_, "mean"), b=(b_, "mean"), n=(a_, "size")).reindex(["冠軍", "其他強隊", "其他球隊"]).dropna(subset=["a"])
            labs = [f"{g_}（{int(r_.n)} 個隊季）" for g_, r_ in G.iterrows()]
            fig = go.Figure()
            for lab, (_, r_) in zip(labs, G.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["a"], r_["b"]], y=[lab, lab], mode="lines", line=dict(color="#d9d3e6", width=4),
                                         showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=G["a"], y=labs, mode="markers", name="今年", marker=dict(size=13, color="#b3adc2"),
                                     hovertemplate="%{y}<br>今年 %{x:.2f}<extra></extra>"))
            dtxt = [(f"{(r_.b - r_.a) * 100:+.1f} 個百分點" if a_ == "win" else f"{r_.b - r_.a:+.1f}") for _, r_ in G.iterrows()]
            fig.add_trace(go.Scatter(x=G["b"], y=labs, mode="markers+text", name="隔年", text=dtxt, textposition="top center",
                                     textfont=dict(size=11, color=INK_2),
                                     marker=dict(size=15, color=[ACCENT, "#8f889f", "#c9c3d6"][:len(G)], line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>隔年 %{x:.2f}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title=axis_, showgrid=True, gridcolor=GRID, tickformat=".0%" if a_ == "win" else None,
                             autorange="reversed" if a_ == "net_rk" else True)
            fig.update_layout(legend=dict(orientation="h", y=1.1, x=0))
            st.plotly_chart(style(fig, 260), width="stretch", config={"displayModeBar": False})
            c_drop = (C["net_d_n"] - C["net_d"]).mean()
            O = RP[RP["grp"] == "其他強隊"]
            o_drop = (O["net_d_n"] - O["net_d"]).mean() if len(O) else float("nan")
            k_top5 = int((C["net_rk_n"] <= 5).sum())
            lines = [f"<b>冠軍隔年平均掉 {abs(c_drop):.1f} 分：</b>淨效率比同季平均從 {C['net_d'].mean():+.1f} 變成 {C['net_d_n'].mean():+.1f}"
                     f"（{len(C)} 位冠軍）。" if c_drop < 0 else
                     f"<b>冠軍隔年沒有退步：</b>淨效率比同季平均從 {C['net_d'].mean():+.1f} 變成 {C['net_d_n'].mean():+.1f}（平均 {c_drop:+.1f}）。",
                     (f"其他強隊（{len(O)} 個隊季）隔年平均 {o_drop:+.1f} 分；" if len(O) else "")
                     + f"{len(C)} 位冠軍裡，{k_top5} 位隔年仍是淨效率前 5 名。",
                     "讀法：先看紫色那一列往左掉多少，再和其他強隊那一列比；兩列掉得差不多，就是「強隊隔年都會往平均靠」，不是冠軍特別。"]
            chk = (("前段成立" if c_drop <= -2 else "前段不成立") + f"：冠軍隔年平均 {c_drop:+.1f} 分；"
                   + (("中段成立" if abs(c_drop - o_drop) < 1.5 else "中段不成立") + f"：其他強隊 {o_drop:+.1f} 分（差 {c_drop - o_drop:+.1f}）；" if len(O) else "")
                   + ("後段成立" if k_top5 * 2 >= len(C) else "後段不成立") + f"：{k_top5} / {len(C)} 位隔年仍是前 5。")
            insight(lines, where=slot1, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["淨效率", "比同季平均（淨效率）", "其他強隊", "回歸平均", "比預期多掉幾分"],
                           first_note="這頁只比<b>例行賽</b>。冠軍的隔年常常有主力受傷、休賽季延後（總冠軍賽打到 6 月）、陣容被挖角，"
                                      "這些原因資料庫看不出來，所以這頁只回答「掉多少」，不回答「為什麼掉」。")

            # ===== 2 每一位冠軍 =====
            st.divider()
            slot2 = section("2　每一位冠軍：奪冠季 → 隔年的淨效率名次",
                            "灰點＝奪冠季名次、彩色點＝隔年名次（越左越好）；括號是隔年淨效率比同季平均")
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}（隔年 {d_:+.1f}）" for s_, a_, d_ in zip(C["season"], C["abbreviation"], C["net_d_n"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, C.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["net_rk"], r_["net_rk_n"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C["net_rk"], y=labels, mode="markers", name="奪冠季",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>奪冠季第 %{x:.0f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=C["net_rk_n"], y=labels, mode="markers+text", name="隔年",
                                     text=[f"第 {v:.0f}" for v in C["net_rk_n"]], textposition="middle right",
                                     textfont=dict(size=10.5, color=INK_2),
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in C["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>隔年第 %{x:.0f}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="淨效率同季名次（1＝最好）", range=[0.5, 30.5], showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 34 * len(C)), width="stretch", config={"displayModeBar": False})
            PO = LG[LG["season_type"] == "Playoffs"].copy()
            for c in ["w", "l"]:
                PO[c] = pd.to_numeric(PO[c], errors="coerce")
            po_map = {(s_, t_): (w_, l_) for s_, t_, w_, l_ in zip(PO["season"], PO["team_id"], PO["w"], PO["l"])}
            repeat = [(ns_, a_) in CHAMP_SET for ns_, a_ in zip(C["next_season"], C["abbreviation"])]
            no_po = [(ns_, t_) not in po_map for ns_, t_ in zip(C["next_season"], C["team_id"])]
            worst = C.loc[C["net_rk_n"].idxmax()]
            insight([f"<b>衛冕成功 {sum(repeat)} 次：</b>{len(C)} 位冠軍裡，{sum(repeat)} 位隔年再拿冠軍、"
                     f"{sum(no_po)} 位隔年沒進季後賽。",
                     f"掉最多的是 {worst['season']} {ALL_ZH.get(worst['abbreviation'], worst['abbreviation'])}："
                     f"隔年淨效率第 {worst['net_rk_n']:.0f} 名。"], where=slot2)
            with st.expander("看每一位冠軍的數字"):
                tb = pd.DataFrame({"奪冠季": C["season"], "冠軍": [ALL_ZH.get(a, a) for a in C["abbreviation"]], "_key": C["abbreviation"],
                                   "奪冠季勝率": [fmt(v, ".0%") for v in C["win"]], "隔年勝率": [fmt(v, ".0%") for v in C["win_n"]],
                                   "奪冠季淨效率（比平均）": [f"{v:+.1f}" for v in C["net_d"]],
                                   "隔年淨效率（比平均）": [f"{v:+.1f}" for v in C["net_d_n"]],
                                   "隔年季後賽": [("沒進" if (ns_, t_) not in po_map else f"{po_map[(ns_, t_)][0]:.0f} 勝 {po_map[(ns_, t_)][1]:.0f} 敗")
                                               + ("　★ 衛冕" if rp_ else "")
                                               for ns_, t_, rp_ in zip(C["next_season"], C["team_id"], repeat)]})
                nice_table(tb, num_cols=("奪冠季勝率", "隔年勝率", "奪冠季淨效率（比平均）", "隔年淨效率（比平均）"),
                           signed_cols=("奪冠季淨效率（比平均）", "隔年淨效率（比平均）"), dot_col="冠軍", colors=TEAM_COLORS)

            # ===== 3 交叉驗證：和「同樣強的球隊」比 =====
            st.divider()
            slot3 = section("3　交叉驗證：和同樣強的球隊比，冠軍掉得比較多嗎？",
                            "每一點是一隊一季：橫軸＝今年淨效率比同季平均、縱軸＝隔年；灰線＝所有球隊的平均走勢（同樣強的球隊隔年大概在哪裡）；★＝冠軍")
            x_, y_ = RP["net_d"], RP["net_d_n"]
            n_ = len(RP)
            slope = ((x_ - x_.mean()) * (y_ - y_.mean())).sum() / max(((x_ - x_.mean()) ** 2).sum(), 1e-9)
            icpt = y_.mean() - slope * x_.mean()
            RP["resid"] = y_ - (icpt + slope * x_)
            O2 = RP[RP["grp"] != "冠軍"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=O2["net_d"], y=O2["net_d_n"], mode="markers", name="其他球隊季",
                                     marker=dict(size=6, color="#cfc9dc"),
                                     text=[f"{s_} {ALL_ZH.get(a_, a_)}" for s_, a_ in zip(O2["season"], O2["abbreviation"])],
                                     hovertemplate="%{text}<br>今年 %{x:+.1f} → 隔年 %{y:+.1f}<extra></extra>"))
            xs = [float(x_.min()), float(x_.max())]
            fig.add_trace(go.Scatter(x=xs, y=[icpt + slope * v for v in xs], mode="lines", name="平均走勢",
                                     line=dict(color=MUTED, width=2, dash="dash"), hoverinfo="skip"))
            C2 = RP[RP["grp"] == "冠軍"]
            fig.add_trace(go.Scatter(x=C2["net_d"], y=C2["net_d_n"], mode="markers", name="★ 冠軍",
                                     marker=dict(size=15, symbol="star", color=[TEAM_COLORS.get(a, ACCENT) for a in C2["abbreviation"]],
                                                 line=dict(width=1, color=SURFACE)),
                                     text=[f"{s_} {ALL_ZH.get(a_, a_)}" for s_, a_ in zip(C2["season"], C2["abbreviation"])],
                                     hovertemplate="%{text}<br>今年 %{x:+.1f} → 隔年 %{y:+.1f}<extra></extra>"))
            fig.update_xaxes(title="今年：淨效率比同季平均", zeroline=True, zerolinecolor="#e4e0ec")
            fig.update_yaxes(title="隔年：淨效率比同季平均", zeroline=True, zerolinecolor="#e4e0ec")
            fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
            st.plotly_chart(style(fig, 420), width="stretch")
            c_res = C2["resid"].mean()
            k_below = int((C2["resid"] < 0).sum())
            insight([f"<b>扣掉「本來就很強」之後，冠軍隔年比預期{'多掉' if c_res < 0 else '少掉'} {abs(c_res):.1f} 分。</b>",
                     f"平均走勢：今年比平均好 10 分的隊，隔年大約剩 {icpt + slope * 10:+.1f} 分（斜率 {slope:.2f}，"
                     f"代表只留下約 {slope:.0%} 的優勢）；{len(C2)} 位冠軍裡 {k_below} 位落在灰線下面（比同樣強的隊掉得多）。",
                     "讀法：★ 在灰線下面＝比同樣強的球隊掉更多（冠軍宿醉）；在上面＝比預期撐得住。"],
                    where=slot3,
                    check=("中段成立（交叉驗證）" if abs(c_res) < 1.5 else "中段不成立（交叉驗證）")
                          + f"：和同樣強的球隊比，冠軍隔年差 {c_res:+.1f} 分（門檻 ±1.5 分）。")


# ---------- 輸球之後：冠軍輸球後會馬上反彈嗎？（2026-11-08 補做）----------
TERMS.update({
    "反彈": ("輸球之後的下一場，勝率比自己整季勝率還高多少；正數＝輸完特別會贏", "輸球後下一場勝率 − 整季勝率"),
    "最長連敗": ("這一季例行賽最多連續輸幾場", "依日期排好，數連續的 L"),
    "預期勝率（log5）": ("用兩隊整季勝率估「這一場本來應該贏幾成」，再加上主場優勢；強隊打弱隊本來就容易贏，要扣掉", "A×(1−B) ÷［A×(1−B) ＋ B×(1−A)］，主場再加一點"),
})


def bb_prep(d, strong=0.6):
    """例行賽每一場：上一場是贏是輸、這一場的對手整季勝率、預期勝率（log5＋主場）"""
    d = d[d["season_type"] == "Regular Season"].dropna(subset=["game_date"]).sort_values(["team_id", "season", "game_date", "game_id"]).copy()
    d["season_win"] = d.groupby(["team_id", "season"])["win"].transform("mean")
    d["prev"] = d.groupby(["team_id", "season"])["win"].shift(1)
    opp = d[["game_id", "team_id", "season_win"]].rename(columns={"team_id": "opp_id", "season_win": "opp_win"})
    d = d.merge(opp, on="game_id")
    d = d[d["opp_id"] != d["team_id"]]
    home_edge = d.loc[d["is_home"] == True, "win"].mean() - 0.5      # noqa: E712  聯盟整體主場多贏幾成
    a, b = d["season_win"].clip(0.02, 0.98), d["opp_win"].clip(0.02, 0.98)
    p = a * (1 - b) / (a * (1 - b) + b * (1 - a))
    d["exp"] = (p + d["is_home"].map({True: home_edge, False: -home_edge}).fillna(0)).clip(0.01, 0.99)
    d["grp"] = "其他球隊"
    d.loc[(~d["champion"]) & (d["season_win"] >= strong), "grp"] = "其他強隊"
    d.loc[d["champion"], "grp"] = "冠軍"
    return d


def bb_streak(d):
    """每一隊每一季的最長連敗"""
    out = []
    for (s_, t_, a_, g_), x in d.groupby(["season", "team_id", "abbreviation", "grp"]):
        best = cur = 0
        for w in x["win"]:
            cur = 0 if w else cur + 1
            best = max(best, cur)
        out.append({"season": s_, "team_id": t_, "abbreviation": a_, "grp": g_, "streak": best})
    return pd.DataFrame(out)


BB_GRPS = ["冠軍", "其他強隊", "其他球隊"]

if PAGE == "輸球之後":
    hypothesis("冠軍輸球之後，下一場會馬上贏回來嗎？是不是很少連敗？",
               "冠軍輸球後的下一場勝率，比自己整季勝率還高（反彈 +3 個百分點以上）；同樣強的其他球隊沒有這種反彈；"
               "大部分冠軍整季最長連敗不超過 3 場。")
    TG = team_games_with_abbr()
    if TG.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球隊逐場比賽還沒有寫進資料庫）")
    else:
        BB = bb_prep(TG)
        BB = BB[BB["season"] != ALL_SEASONS[-1]]          # 本季還沒打完，先不列入
        AFT = BB.dropna(subset=["prev"])
        st.caption(f"例行賽；{BB['abbreviation'].nunique()} 隊、{BB['season'].nunique()} 季（本季還沒打完，先不列入）。")
        # ===== 1 各組：輸球後 vs 贏球後 vs 整季 =====
        slot1 = section("1　輸球之後的下一場：冠軍 vs 其他強隊",
                        "每一組三根長條：整季勝率、贏球後下一場、輸球後下一場；輸球後那根比整季高＝會反彈")
        rows = []
        for g_ in BB_GRPS:
            x = AFT[AFT["grp"] == g_]
            if x.empty:
                continue
            rows.append({"grp": g_, "整季": x["win"].mean(), "贏球後下一場": x.loc[x["prev"] == 1, "win"].mean(),
                         "輸球後下一場": x.loc[x["prev"] == 0, "win"].mean(), "n_loss": int((x["prev"] == 0).sum())})
        G = pd.DataFrame(rows)
        fig = go.Figure()
        for col_, colr in [("整季", "#cfc9dc"), ("贏球後下一場", "#8f889f"), ("輸球後下一場", ACCENT)]:
            fig.add_trace(go.Bar(x=G["grp"], y=G[col_], name=col_, marker_color=colr,
                                 text=[fmt(v, ".0%") for v in G[col_]], textposition="outside",
                                 hovertemplate="%{x}　" + col_ + "：%{y:.1%}<extra></extra>"))
        rounded(fig)
        fig.update_xaxes(type="category")
        fig.update_yaxes(title="勝率", tickformat=".0%", range=[0, 1])
        fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
        G["bounce"] = (G["輸球後下一場"] - G["整季"]) * 100
        gb = G.set_index("grp")["bounce"]
        lines = []
        if "冠軍" in gb:
            lines.append(f"<b>冠軍輸球後的下一場，勝率比整季{'高' if gb['冠軍'] >= 0 else '低'} {abs(gb['冠軍']):.1f} 個百分點</b>"
                         f"（{int(G.set_index('grp').loc['冠軍', 'n_loss'])} 次輸球）。")
        if "其他強隊" in gb:
            lines.append(f"其他強隊 {gb['其他強隊']:+.1f}、其他球隊 {gb.get('其他球隊', float('nan')):+.1f} 個百分點。")
        lines.append("讀法：只看「輸球後」那根不準，因為強隊本來就常贏；要和同一組的「整季」那根比，高出來的才是反彈。")
        chk = None
        if "冠軍" in gb and "其他強隊" in gb:
            chk = (("前段成立" if gb["冠軍"] >= 3 else "前段不成立") + f"：冠軍反彈 {gb['冠軍']:+.1f} 個百分點；"
                   + ("中段成立" if gb["其他強隊"] < gb["冠軍"] - 2 else "中段不成立") + f"：其他強隊 {gb['其他強隊']:+.1f}。")
        insight(lines, where=slot1, check=chk)
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["反彈", "其他強隊", "最長連敗", "預期勝率（log5）"],
                       first_note="這頁只看<b>例行賽</b>。季後賽是同一個對手連打，輸球後的下一場常常換到主場，和例行賽不能放在一起比。")

        # ===== 2 每一位冠軍 =====
        st.divider()
        slot2 = section("2　每一位冠軍：輸球後的下一場、最長連敗",
                        "灰點＝整季勝率、彩色點＝輸球後下一場勝率（在右邊＝會反彈）；括號是整季最長連敗")
        ST = bb_streak(BB)
        C = AFT[AFT["grp"] == "冠軍"]
        if C.empty:
            st.info("資料庫裡還沒有冠軍球季的逐場比賽。")
        else:
            CC = C.groupby(["season", "abbreviation"]).apply(
                lambda x: pd.Series({"整季": x["win"].mean(), "輸球後": x.loc[x["prev"] == 0, "win"].mean(),
                                     "輸球次數": int((x["prev"] == 0).sum())}), include_groups=False).reset_index()
            CC = CC.merge(ST[["season", "abbreviation", "streak"]], on=["season", "abbreviation"], how="left").sort_values("season")
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}（最長 {k_:.0f} 連敗）" for s_, a_, k_ in zip(CC["season"], CC["abbreviation"], CC["streak"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, CC.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["整季"], r_["輸球後"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=CC["整季"], y=labels, mode="markers", name="整季勝率",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>整季 %{x:.1%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=CC["輸球後"], y=labels, mode="markers", name="輸球後下一場",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in CC["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     customdata=CC["輸球次數"],
                                     hovertemplate="%{y}<br>輸球後下一場 %{x:.1%}（%{customdata} 次）<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="勝率", tickformat=".0%", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 34 * len(CC)), width="stretch", config={"displayModeBar": False})
            k_up = int((CC["輸球後"] > CC["整季"]).sum())
            k3 = int((CC["streak"] <= 3).sum())
            OS = ST[ST["grp"] == "其他強隊"]
            insight([f"<b>{len(CC)} 位冠軍裡，{k_up} 位輸球後的下一場比整季還會贏；{k3} 位整季最長連敗不超過 3 場。</b>",
                     (f"其他強隊（{len(OS)} 個隊季）最長連敗平均 {OS['streak'].mean():.1f} 場，冠軍 {CC['streak'].mean():.1f} 場。" if len(OS) else ""),
                     "注意：冠軍一季只輸 15～25 場，單一冠軍的「輸球後勝率」起伏很大，要看第 1 節各組合計。"],
                    where=slot2,
                    check=("後段成立" if k3 * 2 > len(CC) else "後段不成立") + f"：{k3} / {len(CC)} 位冠軍最長連敗 ≤ 3 場。")

        # ===== 3 交叉驗證：扣掉下一場的對手強弱與主客場 =====
        st.divider()
        slot3 = section("3　交叉驗證：扣掉下一場的對手強弱與主客場",
                        "下一場如果剛好打弱隊、又在主場，本來就容易贏；長條＝實際勝率 − 預期勝率（用兩隊整季勝率和主場估），正數＝比預期還會贏")
        rows = []
        for g_ in BB_GRPS:
            x = AFT[AFT["grp"] == g_]
            for pv, lab in [(0, "輸球後下一場"), (1, "贏球後下一場")]:
                y = x[x["prev"] == pv]
                if len(y):
                    rows.append({"grp": g_, "kind": lab, "d": (y["win"].mean() - y["exp"].mean()) * 100, "n": len(y)})
        E = pd.DataFrame(rows)
        fig = go.Figure()
        for lab, colr in [("贏球後下一場", "#8f889f"), ("輸球後下一場", ACCENT)]:
            e = E[E["kind"] == lab]
            fig.add_trace(go.Bar(x=e["grp"], y=e["d"], name=lab, marker_color=colr,
                                 text=[f"{v:+.1f}" for v in e["d"]], textposition="outside", customdata=e["n"],
                                 hovertemplate="%{x}　" + lab + "：比預期 %{y:+.1f} 個百分點（%{customdata} 場）<extra></extra>"))
        rounded(fig)
        fig.add_hline(y=0, line_color=MUTED, line_width=1)
        fig.update_xaxes(type="category")
        fig.update_yaxes(title="實際 − 預期（百分點）")
        fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(style(fig, 340), width="stretch", config={"displayModeBar": False})
        ev = E[E["kind"] == "輸球後下一場"].set_index("grp")["d"]
        if "冠軍" in ev:
            insight([f"<b>扣掉對手強弱與主客場後，冠軍輸球後的下一場比預期{'多' if ev['冠軍'] >= 0 else '少'}贏 {abs(ev['冠軍']):.1f} 個百分點。</b>",
                     (f"其他強隊 {ev['其他強隊']:+.1f}。" if "其他強隊" in ev else "")
                     + "如果第 1 節的反彈在這裡變小，代表有一部分只是下一場剛好比較好打。",
                     "限制：預期勝率用的是兩隊「整季」勝率，不知道那一場誰受傷、誰背靠背（背靠背看「賽程與休息」頁）。"],
                    where=slot3,
                    check=("前段成立（交叉驗證）" if ev["冠軍"] >= 3 else "前段不成立（交叉驗證）")
                          + f"：扣掉對手與主客場後，冠軍輸球後比預期 {ev['冠軍']:+.1f} 個百分點。")


# ---------- 輸球時的球星（2026-11-15 新增）----------
@st.cache_data(ttl=900, show_spinner="讀取球星贏球／輸球數據中…")
def load_star_wl():
    """讀取預先算好的彙總表 star_wl_mv（docs/sql/2026-11-15_輸球時的球星.sql）；還沒建立就回傳空表格"""
    try:
        return fetch_all("star_wl_mv", ["team_id", "season", "season_type", "wl"])
    except Exception:
        return pd.DataFrame()


SWL_SUM = ["games", "star_pts", "star_fga", "star_fta", "star_min", "team_pts", "team_fga", "team_fta"]


def swl_rates(g):
    """把加總數字換成每場平均與真實命中率（g 可以是一隊一季，也可以是一整組加起來）"""
    out = pd.DataFrame(index=g.index)
    n = g["games"].where(g["games"] > 0)
    out["star_ppg"] = g["star_pts"] / n
    out["rest_ppg"] = (g["team_pts"] - g["star_pts"]) / n
    out["star_ts"] = g["star_pts"] / (2 * (g["star_fga"] + 0.44 * g["star_fta"])).where(lambda x: x > 0)
    rest_den = 2 * ((g["team_fga"] - g["star_fga"]) + 0.44 * (g["team_fta"] - g["star_fta"]))
    out["rest_ts"] = (g["team_pts"] - g["star_pts"]) / rest_den.where(rest_den > 0)
    out["star_mpg"] = g["star_min"] / n
    out["games"] = g["games"]
    return out


def prep_star_wl(sw, league_tbl, season_type, strong=0.6):
    """一隊一季一列：頭號得分手在贏球場 vs 輸球場（只算他有上場的比賽）"""
    d = sw[sw["season_type"] == season_type].copy()
    if d.empty:
        return d
    for c in SWL_SUM + ["star_ppg"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    keys = ["season", "team_id", "abbreviation", "player_name"]
    w = d[d["wl"] == "W"].set_index(keys)[SWL_SUM]
    l_ = d[d["wl"] == "L"].set_index(keys)[SWL_SUM]
    both = w.join(l_, how="inner", lsuffix="_w", rsuffix="_l")
    if both.empty:
        return pd.DataFrame()
    rw = swl_rates(both[[f"{c}_w" for c in SWL_SUM]].rename(columns=lambda c: c[:-2]))
    rl = swl_rates(both[[f"{c}_l" for c in SWL_SUM]].rename(columns=lambda c: c[:-2]))
    out = rw.add_suffix("_w").join(rl.add_suffix("_l")).reset_index()
    tot = (both[[f"{c}_w" for c in SWL_SUM]].values + both[[f"{c}_l" for c in SWL_SUM]].values)
    tot = pd.DataFrame(tot, columns=SWL_SUM)
    out["share"] = (tot["star_pts"] / tot["team_pts"].where(tot["team_pts"] > 0)).values
    out["star_drop"] = (out["star_ppg_w"] - out["star_ppg_l"]) / out["star_ppg_w"].where(out["star_ppg_w"] > 0) * 100
    out["rest_drop"] = (out["rest_ppg_w"] - out["rest_ppg_l"]) / out["rest_ppg_w"].where(out["rest_ppg_w"] > 0) * 100
    out["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(out["season"], out["abbreviation"])]
    # 其他強隊：例行賽勝率六成以上、沒奪冠（和月份趨勢、頭號得分手缺陣同一個定義）
    out["grp"] = "其他球隊"
    if not league_tbl.empty and {"w", "gp"} <= set(league_tbl.columns):
        lg = league_tbl[league_tbl["season_type"] == "Regular Season"][["season", "team_id", "w", "gp"]].copy()
        lg["win_pct"] = pd.to_numeric(lg["w"], errors="coerce") / pd.to_numeric(lg["gp"], errors="coerce").where(lambda x: x > 0)
        out = out.merge(lg[["season", "team_id", "win_pct"]], on=["season", "team_id"], how="left")
        out.loc[(~out["champion"]) & (out["win_pct"] >= strong), "grp"] = "其他強隊"
    out.loc[out["champion"], "grp"] = "冠軍"
    # 本季還沒打完，不列入
    return out[out["season"] != ALL_SEASONS[-1]] if season_type == "Regular Season" else out


SWL_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
TERMS.setdefault("頭號得分手", ("這一季在這隊例行賽場均得分最高的球員（至少上場 20 場）", "季中被交易的球員只算替這隊打的比賽"))
TERMS.setdefault("隊友得分", ("同一場比賽裡，頭號得分手以外所有人的得分加起來", "全隊得分 − 頭號得分手得分"))
TERMS.setdefault("輸球時少了幾 %", ("（贏球場均 − 輸球場均）÷ 贏球場均；20 分 → 17 分＝少了 15%", "用百分比，球星和隊友才能放在同一把尺上比"))
TERMS.setdefault("其他強隊", ("整季勝率六成以上、但沒有奪冠的球隊季", "例行賽勝率 ≥ 60%"))
SWL_VIEW = {"場均得分（少了幾 %）": ("ppg", "%"), "真實命中率（掉幾個百分點）": ("ts", "百分點")}

if PAGE == "輸球時的球星":
    hypothesis("冠軍輸球的那幾場，是頭號球星失常，還是隊友沒跟上？",
               "冠軍輸球時，頭號得分手的得分只比贏球時少一點；以百分比算，掉比較多的是其他隊友。"
               "而且冠軍的頭號得分手，輸球時掉得比其他強隊（勝率六成以上、沒奪冠）的頭號得分手少。")
    SW = load_star_wl()
    if SW.empty:
        st.info("尚未載入資料：請先在 Supabase → SQL Editor 執行 docs/sql/2026-11-15_輸球時的球星.sql"
                "（建立 star_wl_mv），再按左側「重新讀取最新資料」。")
    else:
        swl_type = seg("比賽類型", ["例行賽", "季後賽"], "swl_type")
        SWL = prep_star_wl(SW, league, TYPE_OPTIONS[swl_type])
        st.caption("頭號得分手＝這一季在這隊例行賽場均得分最高、至少上場 20 場的球員；只算他有上場的比賽"
                   "（他缺陣的比賽在「頭號得分手缺陣」頁）。隊友＝同一場其他所有人加起來。")
        if SWL.empty or not SWL["champion"].any():
            st.info("資料不足：還沒有同時有贏球場和輸球場的冠軍。")
        else:
            view = seg("看哪一項", list(SWL_VIEW), "swl_view")
            vkey, unit = SWL_VIEW[view]

            # ===== 1. 冠軍／其他強隊／其他球隊：球星和隊友各掉多少 =====
            slot1 = section("1　輸球時，誰掉比較多：頭號得分手，還是隊友？",
                            "紫＝頭號得分手、灰＝其他隊友；長條越高＝輸球時掉越多。同一組的比賽先全部加起來再算，"
                            "所以輸球只有 1、2 場的隊不會把平均拉歪")
            G = SWL.copy()
            gsum = pd.DataFrame()
            for side in ["w", "l"]:
                base = pd.DataFrame({
                    "grp": G["grp"], "games": G[f"games_{side}"],
                    "star_pts": G[f"star_ppg_{side}"] * G[f"games_{side}"],
                    "team_pts": (G[f"star_ppg_{side}"] + G[f"rest_ppg_{side}"]) * G[f"games_{side}"],
                    "star_tsa": G[f"star_ppg_{side}"] * G[f"games_{side}"] / (2 * G[f"star_ts_{side}"]),
                    "rest_tsa": G[f"rest_ppg_{side}"] * G[f"games_{side}"] / (2 * G[f"rest_ts_{side}"]),
                }).replace([float("inf"), -float("inf")], float("nan"))
                s_ = base.groupby("grp")[["games", "star_pts", "team_pts", "star_tsa", "rest_tsa"]].sum()
                s_["star_ppg"] = s_["star_pts"] / s_["games"]
                s_["rest_ppg"] = (s_["team_pts"] - s_["star_pts"]) / s_["games"]
                s_["star_ts"] = s_["star_pts"] / (2 * s_["star_tsa"])
                s_["rest_ts"] = (s_["team_pts"] - s_["star_pts"]) / (2 * s_["rest_tsa"])
                gsum = s_.add_suffix(f"_{side}") if gsum.empty else gsum.join(s_.add_suffix(f"_{side}"))
            gsum = gsum.reindex([g_ for g_ in SWL_GROUPS if g_ in gsum.index])
            gsum["n"] = SWL.groupby("grp").size().reindex(gsum.index)
            for who in ["star", "rest"]:
                if vkey == "ppg":
                    gsum[f"{who}_d"] = (gsum[f"{who}_ppg_w"] - gsum[f"{who}_ppg_l"]) / gsum[f"{who}_ppg_w"] * 100
                else:
                    gsum[f"{who}_d"] = (gsum[f"{who}_ts_w"] - gsum[f"{who}_ts_l"]) * 100
            xlab = [f"{g_}（{int(n_)} 隊季）" for g_, n_ in zip(gsum.index, gsum["n"])]
            fig = go.Figure()
            for who, name, colr in [("star", "頭號得分手", ACCENT), ("rest", "其他隊友", "#b9b2c7")]:
                fig.add_trace(go.Bar(x=xlab, y=gsum[f"{who}_d"], name=name, marker_color=colr,
                                     text=[f"{v:.1f}{'%' if unit == '%' else ''}" for v in gsum[f"{who}_d"]],
                                     textposition="outside", cliponaxis=False, textfont=dict(color=INK),
                                     hovertemplate=f"<b>%{{x}}</b>　{name}<br>輸球時少了 %{{y:.1f}} {unit}<extra></extra>"))
            rounded(fig)
            fig.update_layout(barmode="group")
            fig.update_yaxes(title=f"輸球時少了幾{'%' if unit == '%' else '個百分點'}", rangemode="tozero")
            st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})

            if "冠軍" in gsum.index:
                c_ = gsum.loc["冠軍"]
                u_ = "%" if unit == "%" else " 個百分點"
                front = ("前半成立：冠軍輸球時，頭號得分手掉得比隊友少" if c_["star_d"] < c_["rest_d"] else
                         "前半不成立：冠軍輸球時，頭號得分手掉得比隊友多（輸球時球星也一起失常）")
                back = "其他強隊資料不足，後半無法比較"
                if "其他強隊" in gsum.index:
                    s_d = gsum.loc["其他強隊", "star_d"]
                    back = ("後半成立：冠軍的頭號得分手掉得比其他強隊的少" if c_["star_d"] < s_d - 2 else
                            "後半不成立：冠軍和其他強隊的頭號得分手掉得差不多（差不到 2）" if c_["star_d"] <= s_d + 2 else
                            "後半不成立：冠軍的頭號得分手掉得比其他強隊的多")
                lines = [f"冠軍輸球時，頭號得分手{view.split('（')[0]}少了 <b>{c_['star_d']:.1f}{u_}</b>，"
                         f"其他隊友少了 <b>{c_['rest_d']:.1f}{u_}</b>",
                         f"冠軍頭號得分手：贏球場均 {c_['star_ppg_w']:.1f} 分 → 輸球 {c_['star_ppg_l']:.1f} 分；"
                         f"隊友合計：{c_['rest_ppg_w']:.1f} → {c_['rest_ppg_l']:.1f} 分（{swl_type}）。"]
                if "其他強隊" in gsum.index:
                    lines.append(f"其他強隊的頭號得分手少了 {gsum.loc['其他強隊', 'star_d']:.1f}{u_}、"
                                 f"隊友少了 {gsum.loc['其他強隊', 'rest_d']:.1f}{u_}。")
                insight(lines, where=slot1, check=f"{front}；{back}")

            with st.expander("名詞小辭典"):
                term_table(["頭號得分手", "隊友得分", "輸球時少了幾 %", "其他強隊", "真實命中率"],
                           first_note="只算頭號得分手有上場的比賽；輸球時大家得分都會變少（比賽本來就輸了），"
                                      "所以要比的是「誰少得多」，而不是有沒有變少。")

            # ===== 2. 每一位冠軍的頭號得分手：贏球 → 輸球 =====
            C2 = SWL[SWL["champion"]].sort_values("season")
            slot2 = section(f"2　每一位冠軍的頭號得分手：贏球 → 輸球（{swl_type}）",
                            "灰點＝贏球場均得分、彩色點＝輸球場均得分，括號是少了幾 %；"
                            "最右邊灰字是同一場其他隊友少了幾 %。季後賽冠軍只輸 2～8 場，單一冠軍的數字起伏很大")
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}　{p_}" for s_, a_, p_ in
                      zip(C2["season"], C2["abbreviation"], C2["player_name"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, C2.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["star_ppg_w"], r_["star_ppg_l"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C2["star_ppg_w"], y=labels, mode="markers", name="贏球",
                                     marker=dict(size=11, color="#b9b2c7", line=dict(width=1.5, color=SURFACE)),
                                     customdata=C2[["games_w"]].values,
                                     hovertemplate="%{y}<br>贏球 %{customdata[0]:.0f} 場，場均 %{x:.1f} 分<extra></extra>"))
            fig.add_trace(go.Scatter(x=C2["star_ppg_l"], y=labels, mode="markers+text", name="輸球",
                                     text=[f"（−{v:.0f}%）" if v >= 0 else f"（+{-v:.0f}%）" for v in C2["star_drop"]],
                                     textposition="middle left", textfont=dict(size=11, color=INK_2),
                                     marker=dict(size=13, color=[TEAM_COLORS.get(a_, ACCENT) for a_ in C2["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     customdata=C2[["games_l", "rest_drop"]].values,
                                     hovertemplate="%{y}<br>輸球 %{customdata[0]:.0f} 場，場均 %{x:.1f} 分"
                                                   "<br>隊友少了 %{customdata[1]:.0f}%<extra></extra>"))
            xmax = float(max(C2["star_ppg_w"].max(), C2["star_ppg_l"].max()))
            for lab, v in zip(labels, C2["rest_drop"]):
                fig.add_annotation(x=xmax + 4, y=lab, text=f"隊友 −{v:.0f}%" if v >= 0 else f"隊友 +{-v:.0f}%",
                                   showarrow=False, xanchor="left", font=dict(size=11, color=MUTED))
            fig.update_xaxes(title="頭號得分手場均得分", range=[0, xmax + 11])
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            st.plotly_chart(style(fig, 110 + 30 * len(C2)), width="stretch", config={"displayModeBar": False})
            k_less = int((C2["star_drop"] < C2["rest_drop"]).sum())
            insight([f"{len(C2)} 位冠軍裡，有 <b>{k_less} 位</b>輸球時頭號得分手掉得比隊友少",
                     f"掉最多的是 {C2.loc[C2['star_drop'].idxmax(), 'season']} "
                     f"{C2.loc[C2['star_drop'].idxmax(), 'player_name']}（少了 {C2['star_drop'].max():.0f}%）；"
                     f"掉最少的是 {C2.loc[C2['star_drop'].idxmin(), 'season']} "
                     f"{C2.loc[C2['star_drop'].idxmin(), 'player_name']}"
                     + (f"（少了 {C2['star_drop'].min():.0f}%）。" if C2['star_drop'].min() >= 0
                        else f"（輸球時反而多得 {-C2['star_drop'].min():.0f}%）。")],
                    where=slot2)
            with st.expander("看每一位冠軍的數字"):
                tb = C2.assign(**{
                    "球季": C2["season"], "冠軍": C2["abbreviation"].map(lambda a_: ALL_ZH.get(a_, a_)),
                    "頭號得分手": C2["player_name"],
                    "贏／輸場數": [f"{w_:.0f}／{l_:.0f}" for w_, l_ in zip(C2["games_w"], C2["games_l"])],
                    "球星得分 贏→輸": [f"{a:.1f} → {b:.1f}" for a, b in zip(C2["star_ppg_w"], C2["star_ppg_l"])],
                    "球星命中率 贏→輸": [f"{a * 100:.1f}% → {b * 100:.1f}%" for a, b in zip(C2["star_ts_w"], C2["star_ts_l"])],
                    "隊友得分 贏→輸": [f"{a:.1f} → {b:.1f}" for a, b in zip(C2["rest_ppg_w"], C2["rest_ppg_l"])],
                    "球星變化": [f"{-v:+.0f}%" for v in C2["star_drop"]],
                    "隊友變化": [f"{-v:+.0f}%" for v in C2["rest_drop"]],
                })
                nice_table(tb[["球季", "冠軍", "頭號得分手", "贏／輸場數", "球星得分 贏→輸", "球星命中率 贏→輸",
                               "隊友得分 贏→輸", "球星變化", "隊友變化"]],
                           num_cols=("贏／輸場數", "球星變化", "隊友變化"), signed_cols=("球星變化", "隊友變化"))

            # ===== 3. 全聯盟：越依賴頭號得分手的隊，輸球時他掉越多嗎？ =====
            if swl_type == "例行賽":
                A3 = SWL[(SWL["games_w"] >= 10) & (SWL["games_l"] >= 10)].dropna(subset=["share", "star_drop"])
                slot3 = section("3　放到全聯盟：越依賴頭號得分手的隊，輸球時他掉越多嗎？",
                                "每個點是一隊一季（贏、輸都至少 10 場），橫軸＝他的得分佔全隊幾成、縱軸＝輸球時他少了幾 %；★ 是冠軍")
                if len(A3) >= 10:
                    oth, ch = A3[~A3["champion"]], A3[A3["champion"]]
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=oth["share"], y=oth["star_drop"], mode="markers", name="其他隊季",
                                             marker=dict(size=7, color="#cfc9da", line=dict(width=0.5, color=SURFACE)),
                                             customdata=oth[["season", "abbreviation", "player_name"]].values,
                                             hovertemplate="%{customdata[0]} %{customdata[1]}　%{customdata[2]}"
                                                           "<br>佔全隊 %{x:.0%}，輸球時少了 %{y:.0f}%<extra></extra>"))
                    fig.add_trace(go.Scatter(x=ch["share"], y=ch["star_drop"], mode="markers", name="冠軍",
                                             marker=dict(symbol="star", size=15,
                                                         color=[TEAM_COLORS.get(a_, ACCENT) for a_ in ch["abbreviation"]],
                                                         line=dict(width=1, color=SURFACE)),
                                             customdata=ch[["season", "abbreviation", "player_name"]].values,
                                             hovertemplate="★ %{customdata[0]} %{customdata[1]}　%{customdata[2]}"
                                                           "<br>佔全隊 %{x:.0%}，輸球時少了 %{y:.0f}%<extra></extra>"))
                    fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
                    fig.update_xaxes(title="頭號得分手佔全隊得分", tickformat=".0%")
                    fig.update_yaxes(title="輸球時他少了幾 %")
                    st.plotly_chart(style(fig, 420), width="stretch", config={"displayModeBar": False})
                    r3 = A3["share"].corr(A3["star_drop"])
                    insight([f"得分佔比和「輸球時掉多少」的相關係數 r ＝ <b>{r3:+.2f}</b>（{corr_word(r3)}）",
                             f"共 {len(A3)} 個隊季；r 是正的＝越依賴他的隊，輸球時他掉越多（對手比較會針對他），"
                             "接近 0＝兩件事沒什麼關係。"], where=slot3)
                else:
                    st.info("資料不足：贏、輸都至少 10 場的隊季不到 10 個。")


# ---------- 誰補上得分：頭號得分手缺陣時，得分由誰補上？（2026-11-17）----------
FILL_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
FILL_PARTS = [("第 2 號得分手", ACCENT), ("第 3 號得分手", "#a78bfa"), ("其他隊友", "#c9c3d6")]
FILL_NUM = ["team_id", "player_id", "star_id", "team_g_with", "team_w_with", "team_g_without", "team_w_without",
            "g_with", "min_with", "pts_with", "fga_with", "fta_with",
            "g_without", "min_without", "pts_without", "fga_without", "fta_without"]


@st.cache_data(ttl=3600, show_spinner="讀取「缺陣時誰補上得分」彙總表中…")
def _read_fill():
    """讀 star_fill_mv（一隊一季一位球員一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("star_fill_mv", ["season", "team_id", "player_id"])


def load_fill():
    try:
        df = _read_fill()
        return df if not df.empty else None
    except Exception as e:
        VIEW_ERRORS["star_fill_mv"] = f"{type(e).__name__}: {e}"[:300]
        return None


def _fill_pos(s):
    """分母是 0 時變成空值，不除以 0"""
    return s.where(s > 0)


def _fill_ts(pts, fga, fta):
    return pts / _fill_pos(2 * (fga + 0.44 * fta))


def prep_fill(df, league_tbl, strong=0.6):
    """一隊一季一列：頭號得分手有上場 vs 缺陣時，第 2 號、第 3 號得分手和其他隊友「每場」多得幾分。
    隊友的每場都用「球隊打了幾場」當分母（他那場沒上場就算 0 分），三段加起來剛好＝全部隊友多得的分數。"""
    d = df.copy()
    for c in FILL_NUM:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["is_star"] = d["is_star"].astype(str).str.lower().isin(["true", "t", "1"])
    keys = ["season", "team_id"]
    mates = d[~d["is_star"]].copy()
    # 隊內得分排名（不含頭號得分手）：用「他有上場的那些比賽」裡的場均得分，至少出賽 10 場才排得上前面
    mates["ppg_on"] = mates["pts_with"] / _fill_pos(mates["g_with"])
    mates["rk_key"] = mates["ppg_on"].where(mates["g_with"] >= 10, -1).fillna(-1)
    mates["rk"] = mates.groupby(keys)["rk_key"].rank(ascending=False, method="first")
    mates["part"] = mates["rk"].map(lambda r: "第 2 號得分手" if r == 1 else ("第 3 號得分手" if r == 2 else "其他隊友"))

    t = d.groupby(keys).agg(abbreviation=("abbreviation", "first"), star_name=("star_name", "first"),
                            gw=("team_g_with", "first"), ww=("team_w_with", "first"),
                            go=("team_g_without", "first"), wo=("team_w_without", "first"))
    star = d[d["is_star"]].groupby(keys)["pts_with"].sum().reindex(t.index).fillna(0)
    t["star_on"] = star / _fill_pos(t["gw"])
    sums = ["pts_with", "pts_without", "fga_with", "fga_without", "fta_with", "fta_without"]
    for part, _ in FILL_PARTS:
        m = mates[mates["part"] == part].groupby(keys)[sums].sum().reindex(t.index).fillna(0)
        t[f"{part}_gain"] = m["pts_without"] / _fill_pos(t["go"]) - m["pts_with"] / _fill_pos(t["gw"])
    a = mates.groupby(keys)[sums].sum().reindex(t.index).fillna(0)
    t["mate_on"] = a["pts_with"] / _fill_pos(t["gw"])
    t["mate_off"] = a["pts_without"] / _fill_pos(t["go"])
    t["gain"] = t["mate_off"] - t["mate_on"]
    t["fga_on"] = a["fga_with"] / _fill_pos(t["gw"])
    t["fga_off"] = a["fga_without"] / _fill_pos(t["go"])
    t["ts_on"] = _fill_ts(a["pts_with"], a["fga_with"], a["fta_with"])
    t["ts_off"] = _fill_ts(a["pts_without"], a["fga_without"], a["fta_without"])
    t["fill"] = t["gain"] / _fill_pos(t["star_on"])
    second = mates[mates["rk"] == 1].groupby(keys)["player_name"].first()
    t["second_name"] = second.reindex(t.index)
    t = t.reset_index()
    # 整季勝率（分出「其他強隊」）：用全聯盟每季數據
    lg = league_tbl[league_tbl["season_type"] == "Regular Season"][["season", "team_id", "w", "gp"]].copy() \
        if not league_tbl.empty else pd.DataFrame(columns=["season", "team_id", "w", "gp"])
    for c in ["team_id", "w", "gp"]:
        lg[c] = pd.to_numeric(lg[c], errors="coerce")
    lg["season_win"] = lg["w"] / _fill_pos(lg["gp"])
    t = t.merge(lg[["season", "team_id", "season_win"]], on=["season", "team_id"], how="left")
    t["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(t["season"], t["abbreviation"])]
    t["grp"] = "其他球隊"
    t.loc[(~t["champion"]) & (t["season_win"] >= strong), "grp"] = "其他強隊"
    t.loc[t["champion"], "grp"] = "冠軍"
    return t[t["season"] != ALL_SEASONS[-1]]      # 本季還沒打完，先不列入


def pool_fill(t):
    """各組合計：每一隊依「缺陣場數」加權（缺陣 1 場的隊不會和缺陣 20 場的隊一樣重）"""
    rows = []
    for grp in FILL_GROUPS:
        s = t[(t["grp"] == grp) & (t["go"] > 0)].dropna(subset=["gain", "star_on"])
        w = s["go"]
        W = w.sum()
        if W == 0:
            continue
        r = {"grp": grp, "n_team": len(s), "games": int(W), "star": (s["star_on"] * w).sum() / W,
             "gain": (s["gain"] * w).sum() / W,
             "fga_d": ((s["fga_off"] - s["fga_on"]) * w).sum() / W}
        for part, _ in FILL_PARTS:
            r[part] = (s[f"{part}_gain"].fillna(0) * w).sum() / W
        ok = s.dropna(subset=["ts_on", "ts_off"])
        r["ts_d"] = ((ok["ts_off"] - ok["ts_on"]) * ok["go"]).sum() / ok["go"].sum() * 100 if ok["go"].sum() else float("nan")
        r["win_on"] = s["ww"].sum() / s["gw"].sum() if s["gw"].sum() else float("nan")
        r["win_off"] = s["wo"].sum() / W
        r["fill"] = r["gain"] / r["star"] if r["star"] else float("nan")
        rows.append(r)
    return pd.DataFrame(rows)


if PAGE == "誰補上得分":
    hypothesis("頭號得分手缺陣時，誰補上他的得分？是第 2 號球星一肩扛起，還是大家一起多得一點？",
               "隊友能補回他平常得分的一半以上；補上的分數分散在很多人身上（第 2 號得分手補的不到總補回的四成）；"
               "冠軍的隊友補得比其他強隊（整季勝率六成以上、沒奪冠）多（補回比例高 5 個百分點以上）。")
    FD = load_fill()
    if FD is None:
        st.info("尚未載入資料，請先在 Supabase 的 SQL Editor 執行 docs/sql/2026-11-17_誰補上得分.sql"
                "（建立 star_fill_mv 彙總表），再按左側「重新讀取最新資料」。")
        if "star_fill_mv" in VIEW_ERRORS:
            st.caption(f"讀取 star_fill_mv 的錯誤訊息（截圖給助教看）：{VIEW_ERRORS['star_fill_mv']}")
    else:
        FT = prep_fill(FD, league)
        P = pool_fill(FT)
        st.caption(f"用 {FT['abbreviation'].nunique()} 隊、{FT['season'].nunique()} 季例行賽計算；"
                   "頭號得分手＝這一季在這隊場均得分最高、至少上場 20 場的球員；缺陣＝球隊有打、他沒有上場（不知道原因）。本季還沒打完，先不列入。")
        if P.empty:
            st.info("資料庫裡還沒有「頭號得分手缺陣」的比賽可以比較。")
        else:
            # ===== 1 各組：補回幾成？誰補的？ =====
            slot1 = section("1　少了他，隊友補回幾成？",
                            "長條＝隊友每場多得的分數，佔他平常場均得分的幾 %；三段由左到右是第 2 號得分手、第 3 號、其他隊友；"
                            "虛線 100%＝把他的分數全部補回來。各組依缺陣場數加權合計。")
            P = P.set_index("grp").reindex([g for g in FILL_GROUPS if g in set(P["grp"])])
            labels = [f"{g}（{int(r['n_team'])} 隊季、缺陣 {int(r['games'])} 場）" for g, r in P.iterrows()]
            fig = go.Figure()
            for part, colr in FILL_PARTS:
                share = P[part] / P["star"]
                fig.add_trace(go.Bar(y=labels, x=share, name=part, orientation="h", marker_color=colr,
                                     customdata=P[part],
                                     hovertemplate=part + "：每場多得 %{customdata:+.1f} 分（補回 %{x:.0%}）<extra></extra>"))
            fig.add_trace(go.Scatter(y=labels, x=P["fill"].clip(lower=0), mode="text", showlegend=False, hoverinfo="skip",
                                     text=[f"  合計 {f:.0%}（{g:+.1f} 分／他平常 {s:.1f} 分）"
                                           for f, g, s in zip(P["fill"], P["gain"], P["star"])],
                                     textposition="middle right", textfont=dict(size=11.5, color=INK_2)))
            fig.add_vline(x=1, line_dash="dash", line_color="#b3adc2")
            fig.add_vline(x=0.5, line_dash="dot", line_color="#d9d3e6")
            fig.update_layout(barmode="relative", legend=dict(orientation="h", y=1.12, x=0))
            fig.update_xaxes(title="補回他平常得分的幾 %", tickformat=".0%", range=[min(0, float((P["fill"]).min()) - 0.05), 1.6])
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            rounded(fig)
            st.plotly_chart(style(fig, 120 + 62 * len(P)), width="stretch", config={"displayModeBar": False})

            lines, chk = [], None
            if "冠軍" in P.index:
                c_ = P.loc["冠軍"]
                sec = c_["第 2 號得分手"] / c_["gain"] if c_["gain"] > 0 else float("nan")
                lines.append(f"<b>頭號得分手缺陣時，冠軍的隊友補回他 {c_['fill']:.0%}：</b>每場多得 {c_['gain']:+.1f} 分"
                             f"（他平常場均 {c_['star']:.1f} 分），其中第 2 號得分手多得 {c_['第 2 號得分手']:+.1f} 分。")
                others = [f"{g} {P.loc[g, 'fill']:.0%}" for g in ["其他強隊", "其他球隊"] if g in P.index]
                if others:
                    lines.append("其他組補回：" + "、".join(others) + "。")
                if c_["games"] < 60:
                    lines.append(f"冠軍的頭號得分手合計只缺陣 {int(c_['games'])} 場，數字起伏會比較大。")
                front = ("前段成立" if c_["fill"] >= 0.5 else "前段不成立") + f"：冠軍補回 {c_['fill']:.0%}（門檻五成）"
                mid = ("中段不成立：第 2 號得分手沒有多得分" if not (sec == sec) else
                       ("中段成立" if sec < 0.4 else "中段不成立") + f"：第 2 號得分手佔總補回的 {sec:.0%}（門檻四成）")
                if "其他強隊" in P.index:
                    gap = (c_["fill"] - P.loc["其他強隊", "fill"]) * 100
                    back = ("後段成立" if gap >= 5 else "後段不成立：冠軍和其他強隊差不多（差不到 5 個百分點）" if gap > -5
                            else "後段不成立：冠軍補得比其他強隊少") + f"（冠軍 − 其他強隊 {gap:+.0f} 個百分點）"
                else:
                    back = "後段無法比較：還沒有其他強隊的資料"
                chk = f"{front}；{mid}；{back}。"
            else:
                lines.append("資料庫裡的冠軍球季還沒有頭號得分手缺陣的比賽。")
            lines.append("讀法：先看冠軍那一列的合計有沒有超過 50% 的點線（前段假設）；再看紫色那一段（第 2 號得分手）"
                         "佔整條的多少（中段）；最後比冠軍和其他強隊兩列誰比較長（後段）。"
                         "隊友多得的分數，是用「球隊每一場」平均（他那場沒上場就算 0 分），所以三段加起來就是全部隊友多得的分數。"
                         "缺陣的比賽可能剛好打弱隊（見「缺陣場的對手」頁），補回比例可能被高估。")
            insight(lines, where=slot1, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["頭號得分手（本頁）", "缺陣（本頁）", "補回比例", "第 2 號、第 3 號得分手", "其他強隊", "真實命中率"],
                           first_note="隊友的「每場多得幾分」是用球隊的場數當分母：缺陣的比賽裡隊友一共得幾分 ÷ 缺陣場數，"
                                      "減掉有他上場時的同樣算法。這樣三段加起來，剛好是全部隊友多得的分數。")

            # ===== 2 每一位冠軍 =====
            st.divider()
            slot2 = section("2　每一位冠軍：缺陣時誰多得分",
                            "長條＝隊友每場多得幾分（三段同上）；灰色空心點＝他平常的場均得分，長條碰到灰點＝全部補回；括號是缺陣幾場")
            C = FT[(FT["grp"] == "冠軍") & (FT["go"] > 0)].sort_values("season")
            full = FT[(FT["grp"] == "冠軍") & (FT["go"] == 0)].sort_values("season")
            if C.empty:
                st.info("資料庫裡的冠軍球季還沒有頭號得分手缺陣的比賽。")
            else:
                labels2 = [f"{s_} {ALL_ZH.get(a_, a_)}　{n_}（{int(g_)} 場）"
                           for s_, a_, n_, g_ in zip(C["season"], C["abbreviation"], C["star_name"], C["go"])]
                fig = go.Figure()
                for part, colr in FILL_PARTS:
                    fig.add_trace(go.Bar(y=labels2, x=C[f"{part}_gain"], name=part, orientation="h", marker_color=colr,
                                         hovertemplate=part + "：每場 %{x:+.1f} 分<extra></extra>"))
                fig.add_trace(go.Scatter(y=labels2, x=C["star_on"], mode="markers", name="他平常的場均",
                                         marker=dict(size=11, symbol="circle-open", color="#8f889f", line=dict(width=2)),
                                         hovertemplate="他平常場均 %{x:.1f} 分<extra></extra>"))
                fig.update_layout(barmode="relative", legend=dict(orientation="h", y=1.04, x=0))
                fig.update_xaxes(title="隊友每場多得幾分", zeroline=True, zerolinecolor="#b3adc2")
                fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
                rounded(fig)
                st.plotly_chart(style(fig, 100 + 34 * len(C)), width="stretch", config={"displayModeBar": False})
                big = C[C["go"] >= 5]
                lines2 = []
                if len(big):
                    k50 = int((big["fill"] >= 0.5).sum())
                    top = big.sort_values("fill", ascending=False).iloc[0]
                    lines2.append(f"<b>缺陣至少 5 場的 {len(big)} 位冠軍裡，{k50} 位的隊友補回一半以上：</b>"
                                  f"補最多的是 {top['season']} {ALL_ZH.get(top['abbreviation'], top['abbreviation'])}"
                                  f"（少了 {top['star_name']}，隊友補回 {top['fill']:.0%}）。")
                else:
                    lines2.append("冠軍的頭號得分手缺陣都不到 5 場，單一冠軍的數字只能當參考。")
                if len(full):
                    lines2.append("整季全勤（沒有缺陣場、不在圖上）：" + "、".join(
                        f"{s_} {ALL_ZH.get(a_, a_)} {n_}" for s_, a_, n_ in zip(full["season"], full["abbreviation"], full["star_name"])) + "。")
                lines2.append("讀法：缺陣只有 1、2 場的冠軍，一場爆發就會讓長條變很長，不要只看單一冠軍；"
                              "長條在 0 左邊＝缺陣時那群隊友反而得比較少（例如輪休時主力一起休息）。")
                insight(lines2, where=slot2)
                with st.expander("看每一位冠軍的數字"):
                    tb = pd.DataFrame({
                        "球季": C["season"], "冠軍": [ALL_ZH.get(a, a) for a in C["abbreviation"]], "_key": C["abbreviation"],
                        "頭號得分手": C["star_name"], "他的場均": [fmt(v, ".1f") for v in C["star_on"]],
                        "缺陣場數": C["go"].astype(int),
                        "有他／缺陣戰績": [f"{int(a)}-{int(b - a)}／{int(c)}-{int(d - c)}"
                                     for a, b, c, d in zip(C["ww"], C["gw"], C["wo"], C["go"])],
                        "第 2 號得分手": C["second_name"].fillna("-"),
                        "他多得": [f"{v:+.1f}" for v in C["第 2 號得分手_gain"].fillna(0)],
                        "隊友合計多得": [f"{v:+.1f}" for v in C["gain"]],
                        "補回": [fmt(v, ".0%") for v in C["fill"]],
                    })
                    nice_table(tb, num_cols=("他的場均", "缺陣場數", "他多得", "隊友合計多得", "補回"),
                               signed_cols=("他多得", "隊友合計多得"), dot_col="冠軍", colors=TEAM_COLORS)
                    st.caption("戰績是「勝-敗」。第 2 號得分手＝有他上場的比賽裡，隊上場均得分第二高（至少出賽 10 場）的人。")

            # ===== 3 怎麼補：多出手還是更準？ =====
            st.divider()
            slot3 = section("3　怎麼補：多出手，還是投得更準？",
                            "全部隊友合計：缺陣時每場多出手幾次、真實命中率變多少；最後兩欄是全隊得分和勝率的變化")
            tb3 = pd.DataFrame({
                "組": P.index, "缺陣場數": [int(v) for v in P["games"]],
                "隊友每場出手": [f"{v:+.1f} 次" for v in P["fga_d"]],
                "隊友真實命中率": [f"{v:+.1f} 百分點" for v in P["ts_d"]],
                "全隊每場得分": [f"{g - s:+.1f} 分" for g, s in zip(P["gain"], P["star"])],
                "勝率（有他 → 缺陣）": [f"{a:.0%} → {b:.0%}" for a, b in zip(P["win_on"], P["win_off"])],
            })
            nice_table(tb3, num_cols=("缺陣場數", "隊友每場出手", "隊友真實命中率", "全隊每場得分"),
                       signed_cols=("隊友每場出手", "隊友真實命中率", "全隊每場得分"))
            lines3 = []
            if "冠軍" in P.index:
                c_ = P.loc["冠軍"]
                how = ("主要靠多出手（接手他的出手權），命中率沒有變好" if c_["fga_d"] >= 3 and c_["ts_d"] <= 0.5 else
                       "多出手、也投得更準" if c_["fga_d"] >= 3 else
                       "出手沒有多很多，主要靠投得更準" if c_["ts_d"] > 0.5 else "出手和命中率都沒有明顯變化")
                lines3.append(f"<b>冠軍的隊友{how}：</b>缺陣時每場多出手 {c_['fga_d']:+.1f} 次、"
                              f"真實命中率 {c_['ts_d']:+.1f} 個百分點；全隊每場得分 {c_['gain'] - c_['star']:+.1f} 分。")
            lines3.append("讀法：出手變多、命中率變低，代表隊友是「硬接」他的出手權；兩樣都變好，代表少了他反而打得更流暢。"
                          "全隊每場得分是負數＝沒有全部補回來。")
            insight(lines3, where=slot3)


# =====================================================================
# 對手防守與球星（2026-11-19 每日任務）：季後賽每一輪對手的例行賽防守強弱 × 頭號得分手命中率掉多少
# 資料：star_round_mv（2026-11-18 的 SQL 建立）＋ league_team_seasons（對手那一季的防守效率）
# =====================================================================
ODF_PAGE = "對手防守與球星"
ODF_NEED = ["season", "team_id", "abbreviation", "player_name", "rnd", "opp_id", "wins", "games",
            "star_g", "star_pts", "star_fga", "star_fta", "reg_pts", "reg_g", "reg_fga", "reg_fta"]
ODF_ROUND = ["首輪", "次輪", "分區決賽", "總冠軍賽"]
ODF_BINS = [("防守前 5 名", 1, 5), ("第 6～15 名", 6, 15), ("第 16 名以後", 16, 30)]
ODF_GROUPS = ["冠軍", "其他晉級球隊", "被淘汰的球隊"]
ODF_COLORS = {"冠軍": ACCENT, "其他晉級球隊": "#5f5873", "被淘汰的球隊": "#c9c4d4"}
TERMS.setdefault("對手防守排名", ("季後賽對手在那一季例行賽的防守效率，在 30 隊裡排第幾（1＝最會守）",
                                 "league_team_seasons 的 def_rating（每 100 回合讓對手得幾分），越低排越前面"))
TERMS.setdefault("對手防守比聯盟好幾分", ("對手每 100 回合比同季聯盟平均少讓幾分；正數＝防守比平均好",
                                     "同季 30 隊防守效率平均 − 對手的防守效率"))
TERMS.setdefault("命中率變化（百分點）", ("頭號得分手這一輪的真實命中率，減掉他自己這一季例行賽的；−3 就是 58% → 55%",
                                     "這一輪 − 例行賽，兩個百分比相減叫「百分點」"))
TERMS.setdefault("扣掉對手防守後", ("先用全部資料畫一條「對手防守 → 命中率變化」的直線，再看每一輪比這條線高或低；"
                               "剩下的差距就不是對手防守造成的", "命中率變化 −（a ＋ b × 對手防守比聯盟好幾分）"))


@st.cache_data(ttl=900, show_spinner="讀取每一輪的球星資料中…")
def odf_load():
    """讀 2026-11-18 建立的彙總表；還沒建立就回傳空表格（頁面顯示提示，不會報錯）"""
    try:
        return fetch_all("star_round_mv", ["season", "team_id", "rnd"])
    except Exception:
        return pd.DataFrame()


def odf_pos(s):
    return s.where(s > 0)


def odf_wmean(v, w):
    """加權平均：出手越多的那一輪越重（只有 2、3 次出手的一輪不會和 100 次出手的一樣重）"""
    ok = v.notna() & w.notna() & (w > 0)
    return (v[ok] * w[ok]).sum() / w[ok].sum() if ok.any() else float("nan")


def odf_prep(sr, lg, champs_):
    d = sr.copy()
    for c in ODF_NEED[4:] + ["team_id"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["rnd"].between(1, 4)]
    d["tsa"] = d["star_fga"] + 0.44 * d["star_fta"]
    d["ts"] = d["star_pts"] / odf_pos(2 * d["tsa"])
    d["ts_reg"] = d["reg_pts"] / odf_pos(2 * (d["reg_fga"] + 0.44 * d["reg_fta"]))
    d["d_ts"] = (d["ts"] - d["ts_reg"]) * 100
    L = lg[lg["season_type"] == "Regular Season"][["season", "team_id", "def_rating"]].copy()
    L["team_id"] = pd.to_numeric(L["team_id"], errors="coerce")
    L["def_rating"] = pd.to_numeric(L["def_rating"], errors="coerce")
    L["opp_rk"] = L.groupby("season")["def_rating"].rank(method="min")             # 1＝防守最好
    L["opp_gap"] = L.groupby("season")["def_rating"].transform("mean") - L["def_rating"]   # 正＝比平均少讓幾分
    L = L.rename(columns={"team_id": "opp_id", "def_rating": "opp_def"})
    d = d.merge(L, on=["season", "opp_id"], how="inner")
    champ_ids = set(zip(champs_["season"], pd.to_numeric(champs_["team_id"], errors="coerce")))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    d["won"] = d["wins"] >= 4
    d["grp"] = ["冠軍" if c_ else ("其他晉級球隊" if w_ else "被淘汰的球隊") for c_, w_ in zip(d["champion"], d["won"])]
    d["round"] = d["rnd"].map(lambda r: ODF_ROUND[int(r) - 1])
    d["bin"] = pd.cut(d["opp_rk"], [0, 5, 15, 30], labels=[b[0] for b in ODF_BINS])
    return d[(d["star_g"] >= 2) & d["d_ts"].notna()].copy()


if PAGE == ODF_PAGE:
    hypothesis("季後賽遇到防守強的對手，頭號得分手的命中率是不是掉比較多？冠軍的頭號得分手比較不怕好防守嗎？",
               "對手例行賽防守越好，頭號得分手這一輪的真實命中率比他自己例行賽掉越多（中等相關，r ≤ −0.3）；"
               "遇到防守前 5 名的對手時，冠軍的頭號得分手掉得比其他晉級球隊的少（至少少 1 個百分點）；"
               "「越到後面越難投」主要是因為對手防守越來越好——扣掉對手防守後，四輪的差距會縮小一半以上。")
    st.markdown('<div class="howread">頭號得分手＝這一季例行賽場均得分隊內最高、至少上場 20 場的球員（和「每一輪的球星」頁同一個人）。'
                '只看季後賽，每一輪都和他自己這一季的例行賽比，所以場均 30 分和 20 分的球星可以放在一起看。</div>',
                unsafe_allow_html=True)
    SR = odf_load()
    miss = [c for c in ODF_NEED if c not in SR.columns]
    if SR.empty or miss:
        insight(["尚未載入資料：請先在 Supabase 的 SQL Editor 執行 docs/sql/2026-11-18_每一輪的球星.sql（建立 star_round_mv），"
                 "再按左側「重新讀取最新資料」。"], to_summary=False)
    elif league.empty or "def_rating" not in league.columns:
        insight(["尚未載入資料：league_team_seasons 讀不到，請執行 python load_to_supabase.py"], to_summary=False)
    else:
        D = odf_prep(SR, league, champs)
        if D.empty:
            insight(["資料不足：star_round_mv 和 league_team_seasons 對不起來（球季或球隊編號不同）。"], to_summary=False)
        else:
            # ---------- 1 對手防守越好，命中率掉越多嗎？ ----------
            slot = section("1　對手防守越好，命中率掉越多嗎？",
                           "每個點是一位頭號得分手打的一輪（至少上場 3 場），★ 是冠軍。"
                           "橫軸越右＝對手例行賽防守越好；縱軸越低＝這一輪命中率比他自己例行賽掉越多；斜線是全部點的趨勢。")
            S = D[D["star_g"] >= 3]
            r_all = S["opp_gap"].corr(S["d_ts"])
            xm, ym = S["opp_gap"].mean(), S["d_ts"].mean()
            b = ((S["opp_gap"] - xm) * (S["d_ts"] - ym)).sum() / ((S["opp_gap"] - xm) ** 2).sum()
            a = ym - b * xm
            fig = go.Figure()
            o = S[~S["champion"]]
            fig.add_trace(go.Scatter(
                x=o["opp_gap"], y=o["d_ts"], mode="markers", name="其他季後賽球隊",
                marker=dict(size=6, color="#c9c4d4", opacity=0.75),
                customdata=list(zip(o["season"], o["abbreviation"].map(lambda x: ALL_ZH.get(x, x)), o["player_name"], o["round"], o["opp_rk"])),
                hovertemplate="%{customdata[0]} %{customdata[1]}　%{customdata[2]}<br>%{customdata[3]}，對手防守第 %{customdata[4]:.0f}"
                              "<br>命中率變化 %{y:+.1f} 百分點<extra></extra>"))
            c = S[S["champion"]]
            fig.add_trace(go.Scatter(
                x=c["opp_gap"], y=c["d_ts"], mode="markers", name="冠軍",
                marker=dict(size=13, symbol="star", color=[TEAM_COLORS.get(x, ACCENT) for x in c["abbreviation"]],
                            line=dict(width=1, color="#ffffff")),
                customdata=list(zip(c["season"], c["abbreviation"].map(lambda x: ALL_ZH.get(x, x)), c["player_name"], c["round"], c["opp_rk"])),
                hovertemplate="★ %{customdata[0]} %{customdata[1]}　%{customdata[2]}<br>%{customdata[3]}，對手防守第 %{customdata[4]:.0f}"
                              "<br>命中率變化 %{y:+.1f} 百分點<extra></extra>"))
            xs = [S["opp_gap"].min(), S["opp_gap"].max()]
            fig.add_trace(go.Scatter(x=xs, y=[a + b * v for v in xs], mode="lines", name="趨勢",
                                     line=dict(color=INK_2, width=2, dash="dash"), hoverinfo="skip"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_xaxes(title="對手例行賽防守比同季聯盟平均好幾分（每 100 回合）→ 越右越會守")
            fig.update_yaxes(title="真實命中率變化（百分點）", ticksuffix="")
            st.plotly_chart(style(fig, 440), width="stretch", config={"displayModeBar": False})
            front = ("前段成立" if r_all <= -0.3 else
                     "前段不成立：方向對（防守越好掉越多），但只是" + corr_word(r_all) if r_all < 0 else
                     "前段不成立：對手防守越好，命中率沒有掉比較多")
            insight([f"對手防守和球星命中率變化的 r＝{r_all:+.2f}（{corr_word(r_all)}）：對手例行賽防守每好 1 分，"
                      f"頭號得分手這一輪的命中率平均{'多掉' if b < 0 else '反而多'} {abs(b):.2f} 個百分點",
                      f"一共 {len(S)} 輪（{S['season'].nunique()} 季），其中冠軍 {len(c)} 輪。",
                      "讀法：點越往右下排，代表「越會守的對手讓球星掉越多」；如果點散成一團、斜線很平，就是對手防守好壞和命中率掉多少關係不大。"
                      "單一點起伏很大（一輪只有 4～7 場），要看整體的斜線和 r。"],
                    where=slot, check=front + f"（r＝{r_all:+.2f}，門檻 −0.3）")
            with st.expander("名詞小辭典"):
                term_table(["對手防守排名", "對手防守比聯盟好幾分", "真實命中率", "命中率變化（百分點）", "相關係數 r", "扣掉對手防守後"],
                           first_note="對手的防守用「那一季例行賽」的數字，不是季後賽的（季後賽只有 16 隊、場數不同，排名不公平）。")

            # ---------- 2 遇到前 5 名的防守，冠軍比較撐得住嗎？ ----------
            slot2 = section("2　遇到防守前 5 名，冠軍的頭號得分手比較撐得住嗎？",
                            "把對手依例行賽防守排名分三組，每組裡比冠軍、其他晉級球隊（贏下這一輪）、被淘汰的球隊；"
                            "長條＝命中率比自己例行賽變多少（依出手次數加權），長條上寫幾輪。")
            rows = []
            for bn, _, _ in ODF_BINS:
                for g in ODF_GROUPS:
                    x = D[(D["bin"] == bn) & (D["grp"] == g)]
                    rows.append({"bin": bn, "grp": g, "mean": odf_wmean(x["d_ts"], x["tsa"]), "n": len(x)})
            B = pd.DataFrame(rows)
            fig = go.Figure()
            for g in ODF_GROUPS:
                x = B[B["grp"] == g]
                fig.add_trace(go.Bar(x=x["bin"], y=x["mean"], name=g, marker_color=ODF_COLORS[g],
                                     text=[f"{m:+.1f}<br>{n} 輪" if pd.notna(m) else "" for m, n in zip(x["mean"], x["n"])],
                                     textposition="outside", cliponaxis=False,
                                     hovertemplate=g + "<br>%{x}：%{y:+.1f} 百分點<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1))
            fig.update_layout(barmode="group")
            fig.update_xaxes(type="category", title="對手例行賽防守排名")
            fig.update_yaxes(title="真實命中率變化（百分點）")
            rounded(fig)
            st.plotly_chart(style(fig, 400), width="stretch", config={"displayModeBar": False})
            top = B[B["bin"] == ODF_BINS[0][0]].set_index("grp")
            cm, om, cn = top.loc["冠軍", "mean"], top.loc["其他晉級球隊", "mean"], int(top.loc["冠軍", "n"])
            if pd.isna(cm) or pd.isna(om):
                back = "中段無法判斷：防守前 5 名這一組沒有冠軍或其他晉級球隊的資料"
                lines2 = ["資料不足：防守前 5 名這一組的輪數太少，無法比較。"]
            else:
                back = ("中段成立" if cm >= om + 1 else
                        "中段不成立：冠軍和其他晉級球隊掉得差不多（差不到 1 個百分點）" if cm >= om - 1 else
                        "中段不成立：冠軍掉得比其他晉級球隊多") + f"（冠軍 {cm:+.1f}、其他晉級 {om:+.1f}）"
                lines2 = [f"遇到防守前 5 名的對手，冠軍的頭號得分手命中率變化 {cm:+.1f} 個百分點，其他晉級球隊 {om:+.1f}",
                          f"冠軍在這一組只有 {cn} 輪，單一冠軍的影響很大，結論要保守看。" if cn < 15 else "",
                          "讀法：先看同一組裡紫色和深灰色誰比較高（比較接近 0＝掉得少）；再看三組由左到右，長條是不是越來越接近 0（對手越弱越好投）。"
                          "淺灰色（被淘汰的球隊）通常最低——投不進本來就是輸掉系列賽的原因之一，所以公平的比較是紫色 vs 深灰色。"]
            insight(lines2, where=slot2, check=back)

            # ---------- 3 交叉驗證：越後面越難投，是因為對手越會守嗎？ ----------
            slot3 = section("3　交叉驗證：越後面越難投，是因為對手越會守嗎？",
                            "四輪各算一次「直接看」的命中率變化，再算「扣掉對手防守後」的（和第 1 節那條斜線比）；"
                            "所有季後賽球隊的頭號得分手一起算，依出手次數加權。")
            D["resid"] = D["d_ts"] - (a + b * D["opp_gap"])
            R = []
            for i, rn in enumerate(ODF_ROUND):
                x = D[D["round"] == rn]
                R.append({"輪次": rn, "_raw": odf_wmean(x["d_ts"], x["tsa"]), "_adj": odf_wmean(x["resid"], x["tsa"]) + odf_wmean(D["d_ts"], D["tsa"]),
                          "_rk": x["opp_rk"].mean(), "_n": len(x)})
            R = pd.DataFrame(R)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=R["輪次"], y=R["_raw"], mode="lines+markers+text", name="直接看",
                                     line=dict(color=MUTED, width=2), marker=dict(size=9),
                                     text=[f"{v:+.1f}" for v in R["_raw"]], textposition="bottom center"))
            fig.add_trace(go.Scatter(x=R["輪次"], y=R["_adj"], mode="lines+markers+text", name="扣掉對手防守後",
                                     line=dict(color=ACCENT, width=3), marker=dict(size=10),
                                     text=[f"{v:+.1f}" for v in R["_adj"]], textposition="top center"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_xaxes(type="category", title="")
            fig.update_yaxes(title="真實命中率變化（百分點）")
            st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
            raw_gap = R["_raw"].iloc[-1] - R["_raw"].iloc[0]
            adj_gap = R["_adj"].iloc[-1] - R["_adj"].iloc[0]
            if raw_gap < 0:
                shrink = 1 - (adj_gap / raw_gap if raw_gap else 1)
                how = ("差距完全消失" if shrink >= 1 else f"差距縮小 {shrink:.0%}" if shrink > 0 else "差距沒有縮小")
                last = ("後段成立" if shrink >= 0.5 else "後段不成立") + \
                       f"：總冠軍賽比首輪多掉 {abs(raw_gap):.1f} 個百分點，扣掉對手防守後是 {adj_gap:+.1f}（{how}，門檻一半）"
            else:
                last = f"後段不成立：總冠軍賽的命中率沒有比首輪掉更多（{raw_gap:+.1f}），所以不需要用對手防守解釋"
            insight([f"對手的平均防守排名：首輪第 {R['_rk'].iloc[0]:.1f}、總冠軍賽第 {R['_rk'].iloc[-1]:.1f}；"
                     f"總冠軍賽比首輪的命中率差 {raw_gap:+.1f} 個百分點，扣掉對手防守後是 {adj_gap:+.1f}",
                     "讀法：灰線是直接看；紫線是「如果每一輪遇到的對手防守都一樣」會是多少。兩條線越平、越接近，代表輪次本身影響不大；"
                     "紫線比灰線平很多，代表「越後面越難投」大部分是因為對手越會守。"],
                    where=slot3, check=last)
            nice_table(pd.DataFrame({"輪次": R["輪次"], "幾輪": R["_n"].astype(int),
                                     "對手平均防守排名": R["_rk"].map(lambda v: f"第 {v:.1f}"),
                                     "直接看（百分點）": R["_raw"].map(lambda v: f"{v:+.1f}"),
                                     "扣掉對手防守後": R["_adj"].map(lambda v: f"{v:+.1f}")}),
                       num_cols=("幾輪", "對手平均防守排名", "直接看（百分點）", "扣掉對手防守後"),
                       signed_cols=("直接看（百分點）", "扣掉對手防守後"))

            with st.expander("看每一位冠軍每一輪的數字"):
                C = D[D["champion"]].sort_values(["season", "rnd"])
                nice_table(pd.DataFrame({
                    "球季": C["season"], "冠軍": C["abbreviation"].map(lambda x: ALL_ZH.get(x, x)),
                    "頭號得分手": C["player_name"], "輪次": C["round"],
                    "對手": C["opp_abbr"].map(lambda x: ALL_ZH.get(x, x)) if "opp_abbr" in C.columns else "-",
                    "對手防守排名": C["opp_rk"].map(lambda v: f"第 {v:.0f}"),
                    "這一輪命中率": (C["ts"] * 100).map(lambda v: f"{v:.1f}%"),
                    "例行賽命中率": (C["ts_reg"] * 100).map(lambda v: f"{v:.1f}%"),
                    "變化": C["d_ts"].map(lambda v: f"{v:+.1f}")}),
                    num_cols=("對手防守排名", "這一輪命中率", "例行賽命中率", "變化"), signed_cols=("變化",))


# ---------- 系列賽主場優勢：有主場優勢的一方比較常晉級嗎？（2026-11-22 補做）----------
TERMS.update({
    "系列賽主場優勢": ("七戰四勝的系列賽裡，第 1、2、5、7 戰在自己主場的那一隊（例行賽戰績比較好的一方）", "第 1 戰的主場球隊"),
    "搶七": ("系列賽打到第 7 戰；第 7 戰一定在有主場優勢的那一隊的主場", "第 7 場"),
    "同一組對手的主客場差": ("同一個系列賽、同樣兩隊，有主場優勢的一方在自己主場和到對方主場的單場勝率差；兩隊實力沒變，差出來的就是「場地」的影響", "主場單場勝率 − 客場單場勝率"),
})
HC_NO_HOME = {"2019-20"}       # 泡泡園區：沒有真正的主場，第 3 節不列入


def hc_series(d):
    """把季後賽每一場整理成系列賽：一個系列賽一列，從「有主場優勢的一方」來看"""
    p = d[d["season_type"] == "Playoffs"].dropna(subset=["game_date"]).copy()
    if p.empty:
        return p, p
    opp = p[["game_id", "team_id", "abbreviation"]].rename(columns={"team_id": "opp_id", "abbreviation": "opp_abbr"})
    p = p.merge(opp, on="game_id")
    p = p[p["opp_id"] != p["team_id"]].sort_values(["season", "team_id", "game_date", "game_id"])
    p["gno"] = p.groupby(["season", "team_id", "opp_id"]).cumcount() + 1
    first = p[p["gno"] == 1][["season", "team_id", "opp_id", "is_home", "game_date"]].rename(
        columns={"is_home": "hc", "game_date": "d0"})
    p = p.merge(first, on=["season", "team_id", "opp_id"])
    S = (p.groupby(["season", "team_id", "abbreviation", "opp_id", "opp_abbr", "hc", "d0"])
         .agg(w=("win", "sum"), g=("win", "size")).reset_index())
    S["l"] = S["g"] - S["w"]
    S["won"] = S["w"] > S["l"]
    S["rnd"] = S.groupby(["season", "team_id"])["d0"].rank(method="first").astype(int)
    S["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(S["season"], S["abbreviation"])]
    return S, p


if PAGE == "系列賽主場優勢":
    hypothesis("季後賽有主場優勢（第 1、2、5、7 戰在自己主場）的一方，比較常晉級嗎？冠軍是不是大多數輪次都有主場優勢？",
               "有主場優勢的一方贏下系列賽的比例超過 70%；冠軍至少四分之三的系列賽有主場優勢；"
               "而且同一組對手，有主場優勢的一方在自己主場的單場勝率比到客場高 10 個百分點以上——主場本身有幫助，不只是因為比較強。")
    TG = team_games_with_abbr()
    S, PG = hc_series(TG) if not TG.empty else (pd.DataFrame(), pd.DataFrame())
    if S.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py（球隊的季後賽逐場比賽還沒有寫進資料庫）")
    else:
        H = S[S["hc"] == True]                  # noqa: E712  每個系列賽只留有主場優勢的那一隊
        H = H[H["g"] >= 4]                       # 還沒打完的系列賽不算
        st.caption(f"{H['season'].nunique()} 季、{len(H)} 個系列賽（季後賽；附加賽不算）。第幾輪＝這一隊這一季的第幾個系列賽。")
        # ===== 1 每一輪：主場優勢一方的晉級比例 =====
        slot1 = section("1　有主場優勢的一方，晉級比例有多高？",
                        "一根長條是一輪；可以切換成「打到搶七的比例」。虛線＝50%（兩隊一樣）")
        kind = seg("看哪一項", ["晉級比例", "打到搶七的比例"], key="hc_kind")
        R = H.groupby("rnd").agg(won=("won", "mean"), g7=("g", lambda s: (s == 7).mean()), n=("won", "size")).reset_index()
        R["name"] = [ROUND_ZH[i - 1] if 1 <= i <= 4 else f"第 {i} 輪" for i in R["rnd"]]
        col_ = "won" if kind == "晉級比例" else "g7"
        fig = go.Figure(go.Bar(x=R["name"], y=R[col_], marker_color=ACCENT,
                               text=[f"{v:.0%}" for v in R[col_]], textposition="outside", customdata=R["n"],
                               hovertemplate="%{x}：%{y:.1%}（%{customdata} 個系列賽）<extra></extra>"))
        rounded(fig)
        if kind == "晉級比例":
            fig.add_hline(y=0.5, line_dash="dash", line_color=MUTED, annotation_text="50%", annotation_position="right")
        fig.update_xaxes(type="category", categoryorder="array", categoryarray=list(R["name"]))
        fig.update_yaxes(title=kind, tickformat=".0%", range=[0, 1.05])
        st.plotly_chart(style(fig, 330), width="stretch", config={"displayModeBar": False})
        all_won = H["won"].mean()
        g7_rate = (H["g"] == 7).mean()
        g7 = H[H["g"] == 7]
        lines = [f"<b>有主場優勢的一方贏下 {all_won:.0%} 的系列賽</b>（{len(H)} 個系列賽，各輪 {R['won'].min():.0%}～{R['won'].max():.0%}）。",
                 f"{g7_rate:.0%} 的系列賽打到搶七；搶七時主場那一隊贏 {g7['won'].mean():.0%}（{len(g7)} 場）。" if len(g7) else
                 "還沒有打到搶七的系列賽。",
                 "讀法：主場優勢給的是例行賽戰績比較好的那一隊，所以這個比例同時包含「比較強」和「在主場打」兩件事，第 3 節再把兩件事分開。"]
        insight(lines, where=slot1, check=("前段成立" if all_won > 0.7 else "前段不成立") + f"：有主場優勢的一方晉級 {all_won:.0%}（門檻 70%）。")
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["系列賽主場優勢", "搶七", "同一組對手的主客場差"],
                       first_note="2019-20 的季後賽全部在泡泡園區（奧蘭多）打，沒有真正的主場；第 1、2 節照官方的主客場標示算，第 3 節不列入。")

        # ===== 2 每一位冠軍：四輪有沒有主場優勢 =====
        st.divider()
        slot2 = section("2　每一位冠軍：哪幾輪有主場優勢？",
                        "一列一位冠軍、一欄一輪；深紫＝有主場優勢、淺色＝沒有；格子是系列賽比分和對手")
        CS = S[S["champion"] & (S["rnd"] <= 4)].copy()
        if CS.empty:
            st.info("資料庫裡還沒有冠軍的季後賽逐場比賽。")
        else:
            CS["txt"] = [f"{w_:.0f}-{l_:.0f} {o_}" for w_, l_, o_ in zip(CS["w"], CS["l"], CS["opp_abbr"])]
            rows_ = sorted(CS["season"].unique())
            ylab = {s_: f"{s_} {ALL_ZH.get(a_, a_)}" for s_, a_ in zip(CS["season"], CS["abbreviation"])}
            z = CS.pivot(index="season", columns="rnd", values="hc").reindex(index=rows_, columns=[1, 2, 3, 4])
            tx = CS.pivot(index="season", columns="rnd", values="txt").reindex(index=rows_, columns=[1, 2, 3, 4])
            zz = z.apply(lambda c: c.map(lambda v: float("nan") if pd.isna(v) else (1.0 if v else 0.0)))
            fig = go.Figure(go.Heatmap(z=zz.values, x=ROUND_ZH, y=[ylab[s_] for s_ in rows_],
                                       text=tx.fillna("").values, texttemplate="%{text}", textfont=dict(size=11),
                                       colorscale=[[0, "#ede9fe"], [1, "#6d28d9"]], zmin=0, zmax=1, showscale=False,
                                       xgap=3, ygap=3, hovertemplate="%{y}　%{x}<br>%{text}<extra></extra>"))
            fig.update_xaxes(type="category", side="top")
            fig.update_yaxes(type="category", autorange="reversed")
            st.plotly_chart(style(fig, 80 + 32 * len(rows_)), width="stretch", config={"displayModeBar": False})
            share = CS["hc"].astype(bool).mean()
            k_all = int(CS.groupby("season")["hc"].apply(lambda s: s.astype(bool).all()).sum())
            no_hc = CS[~CS["hc"].astype(bool)]
            insight([f"<b>冠軍 {share:.0%} 的系列賽有主場優勢</b>（{len(CS)} 個系列賽）；{len(rows_)} 位冠軍裡 {k_all} 位四輪都有。",
                     (f"沒有主場優勢還贏下來的有 {len(no_hc)} 次，" + "、".join(
                         f"{s_} {ALL_ZH.get(a_, a_)}（{ROUND_ZH[r_ - 1]}）" for s_, a_, r_ in zip(no_hc["season"], no_hc["abbreviation"], no_hc["rnd"]))[:160] + "。")
                     if len(no_hc) else "每一個系列賽都有主場優勢。"],
                    where=slot2, check=("中段成立" if share >= 0.75 else "中段不成立") + f"：冠軍 {share:.0%} 的系列賽有主場優勢（門檻 75%）。")
            with st.expander("看每一位冠軍每一輪的明細"):
                tb = CS.sort_values(["season", "rnd"])
                nice_table(pd.DataFrame({"球季": tb["season"], "冠軍": [ALL_ZH.get(a, a) for a in tb["abbreviation"]], "_key": tb["abbreviation"],
                                         "輪": [ROUND_ZH[r - 1] for r in tb["rnd"]],
                                         "對手": [ALL_ZH.get(o, o) for o in tb["opp_abbr"]],
                                         "比分": [f"{w_:.0f}-{l_:.0f}" for w_, l_ in zip(tb["w"], tb["l"])],
                                         "主場優勢": ["有" if h_ else "沒有" for h_ in tb["hc"].astype(bool)]}),
                           num_cols=("比分",), dot_col="冠軍", colors=TEAM_COLORS)

        # ===== 3 交叉驗證：同一組對手，在主場 vs 到客場 =====
        st.divider()
        slot3 = section("3　交叉驗證：同樣兩隊，換到客場就比較難贏嗎？",
                        "同一個系列賽裡，有主場優勢的一方在自己主場（第 1、2、5、7 戰）和到客場（第 3、4、6 戰）的單場勝率；兩隊實力沒變，差出來的是場地的影響")
        P2 = PG[(PG["hc"] == True) & (~PG["season"].isin(HC_NO_HOME))]          # noqa: E712
        P2 = P2.merge(H[["season", "team_id", "opp_id", "rnd"]], on=["season", "team_id", "opp_id"])
        if P2.empty:
            st.info("還沒有足夠的季後賽逐場比賽。")
        else:
            P2["where"] = P2["is_home"].map({True: "在自己主場", False: "到對方主場"})
            Q = P2.groupby(["rnd", "where"])["win"].agg(["mean", "size"]).reset_index()
            Q["name"] = [ROUND_ZH[i - 1] if 1 <= i <= 4 else f"第 {i} 輪" for i in Q["rnd"]]
            fig = go.Figure()
            for w_, colr in [("在自己主場", ACCENT), ("到對方主場", "#b3adc2")]:
                q = Q[Q["where"] == w_]
                fig.add_trace(go.Bar(x=q["name"], y=q["mean"], name=w_, marker_color=colr,
                                     text=[f"{v:.0%}" for v in q["mean"]], textposition="outside", customdata=q["size"],
                                     hovertemplate="%{x}　" + w_ + "：%{y:.1%}（%{customdata} 場）<extra></extra>"))
            rounded(fig)
            fig.add_hline(y=0.5, line_dash="dash", line_color=MUTED)
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=[n for n in ROUND_ZH if n in set(Q["name"])])
            fig.update_yaxes(title="有主場優勢一方的單場勝率", tickformat=".0%", range=[0, 1.05])
            fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
            st.plotly_chart(style(fig, 340), width="stretch", config={"displayModeBar": False})
            hw = P2.loc[P2["is_home"] == True, "win"].mean()        # noqa: E712
            aw = P2.loc[P2["is_home"] == False, "win"].mean()       # noqa: E712
            gap = (hw - aw) * 100
            insight([f"<b>同樣兩隊，有主場優勢的一方在主場贏 {hw:.0%}、到客場只贏 {aw:.0%}，差 {gap:.0f} 個百分點。</b>",
                     f"到客場仍然贏 {aw:.0%}：{'超過' if aw > 0.5 else '不到'}一半，代表他們本來就比較強；主客場差的那 {gap:.0f} 個百分點，才是場地本身的影響。",
                     "限制：系列賽打到第 5～7 戰才有的比賽，多半是兩隊比較接近的系列賽，所以「主場」那邊會稍微偏向難打的比賽；2019-20 泡泡園區不列入。"],
                    where=slot3,
                    check=("後段成立（交叉驗證）" if gap >= 10 else "後段不成立（交叉驗證）") + f"：同一組對手主客場差 {gap:.0f} 個百分點（門檻 10）。")


# ---------- 季末輪休：最後 10 場，主力真的在休息嗎？（2026-11-23）----------
TERMS.update({
    "前 3 號主力": ("這一季替這隊上場總分鐘最多的 3 個人（至少上場 20 場）", "依整季例行賽上場分鐘排名"),
    "主力缺陣比例": ("主力「應該上場」的人次裡，有幾成沒有上場；3 位主力打 10 場＝30 人次，缺 6 人次就是 20%", "缺陣人次 ÷（主力人數 × 場數）"),
    "最後 10 場／前面": ("這一季例行賽依日期排好，最後 10 場和前面所有比賽", "82 場＝前 72 場、最後 10 場"),
    "主力全員上場的比賽": ("3 位主力都有上場的比賽；只看這些比賽，就把「輪休」的影響拿掉了", "缺陣人次＝0 的比賽"),
})
RE_GRPS = ["冠軍", "其他強隊", "其他季後賽球隊", "沒進季後賽"]
RE_METRIC = {"主力缺陣比例": ("out_rate", ".0%", "前 3 號主力缺陣比例"),
             "主力上場分鐘": ("core_min", ".1f", "主力有上場時，每人平均幾分鐘"),
             "每場上場人數": ("used", ".1f", "每場上場人數"),
             "勝率": ("win", ".0%", "勝率")}


@st.cache_data(ttl=3600, show_spinner="讀取季末輪休彙總表中…")
def _read_rest_end():
    """讀 rest_end_mv（一隊一季兩段一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("rest_end_mv", ["season", "team_id", "seg"])


def load_rest_end():
    try:
        df = _read_rest_end()
        return df if not df.empty else None
    except Exception as e:
        VIEW_ERRORS["rest_end_mv"] = f"{type(e).__name__}: {e}"[:300]
        return None


def re_prep(df, strong=0.6):
    d = df.copy()
    for c in ["season_win", "games", "wins", "core_slots", "core_out", "games_full", "wins_full", "core_min", "used", "opp_win"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["playoff"] = d["playoff"].astype(str).str.lower().isin(["true", "t", "1"])
    d["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(d["season"], d["abbreviation"])]
    d["grp"] = "沒進季後賽"
    d.loc[d["playoff"], "grp"] = "其他季後賽球隊"
    d.loc[(~d["champion"]) & (d["season_win"] >= strong), "grp"] = "其他強隊"
    d.loc[d["champion"], "grp"] = "冠軍"
    return d


def re_sum(x):
    """一堆隊季合起來：用加總再相除（場數多的隊季比重大）"""
    g = x["games"].sum()
    return pd.Series({"out_rate": x["core_out"].sum() / max(x["core_slots"].sum(), 1),
                      "core_min": (x["core_min"] * x["games"]).sum() / max(g, 1),
                      "used": (x["used"] * x["games"]).sum() / max(g, 1),
                      "win": x["wins"].sum() / max(g, 1),
                      "win_full": x["wins_full"].sum() / max(x["games_full"].sum(), 1),
                      "opp_win": (x["opp_win"] * x["games"]).sum() / max(g, 1),
                      "n": x[["season", "team_id"]].drop_duplicates().shape[0]})


if PAGE == "季末輪休":
    hypothesis("例行賽最後 10 場，球隊是不是真的讓主力休息？季末勝率下滑是因為輪休嗎？",
               "強隊（冠軍、其他強隊）最後 10 場的前 3 號主力缺陣比例，比前面的比賽高 5 個百分點以上，而且冠軍上升得比其他強隊多；"
               "強隊季末勝率會下滑，但只看主力全員上場的比賽，下滑縮小到 3 個百分點以內——下滑主要是輪休造成的。")
    RE = load_rest_end()
    if RE is None:
        st.info("尚未載入資料：請先在 Supabase 的 SQL Editor 執行 docs/sql/2026-11-23_季末輪休.sql（建立 rest_end_mv），"
                "再按左側「重新讀取最新資料」。")
        if "rest_end_mv" in VIEW_ERRORS:
            st.caption(f"讀取時的錯誤訊息：{VIEW_ERRORS['rest_end_mv']}")
    else:
        RE = re_prep(RE)
        st.caption(f"例行賽；{RE['season'].nunique()} 季、{RE[['season', 'team_id']].drop_duplicates().shape[0]} 個隊季"
                   "（只算已經打完的球季；本季還沒打完，先不列入）。")
        G = RE.groupby(["grp", "seg"]).apply(re_sum, include_groups=False).reset_index()
        # ===== 1 各組：前面 → 最後 10 場 =====
        slot1 = section("1　最後 10 場，主力缺陣變多了嗎？",
                        "灰點＝前面的比賽、彩色點＝最後 10 場；四組各一列，點旁是最後 10 場 − 前面。可以切換看主力上場分鐘、上場人數、勝率")
        mname = seg("看哪一項", list(RE_METRIC), key="re_metric")
        col_, f_, axis_ = RE_METRIC[mname]
        A = G[G["seg"] == "前面"].set_index("grp").reindex(RE_GRPS)
        B = G[G["seg"] == "最後10場"].set_index("grp").reindex(RE_GRPS)
        keep = [g_ for g_ in RE_GRPS if pd.notna(A.loc[g_, col_]) and pd.notna(B.loc[g_, col_])]
        labs = [f"{g_}（{int(A.loc[g_, 'n'])} 個隊季）" for g_ in keep]
        diff = [(B.loc[g_, col_] - A.loc[g_, col_]) for g_ in keep]
        dtxt = [(f"{v * 100:+.1f} 個百分點" if "%" in f_ else f"{v:+.1f}") for v in diff]
        fig = go.Figure()
        for lab, g_ in zip(labs, keep):
            fig.add_trace(go.Scatter(x=[A.loc[g_, col_], B.loc[g_, col_]], y=[lab, lab], mode="lines",
                                     line=dict(color="#d9d3e6", width=4), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=[A.loc[g_, col_] for g_ in keep], y=labs, mode="markers", name="前面",
                                 marker=dict(size=13, color="#b3adc2"), hovertemplate="%{y}<br>前面 %{x}<extra></extra>"))
        fig.add_trace(go.Scatter(x=[B.loc[g_, col_] for g_ in keep], y=labs, mode="markers+text", name="最後 10 場",
                                 text=dtxt, textposition="top center", textfont=dict(size=11, color=INK_2),
                                 marker=dict(size=15, color=[{"冠軍": ACCENT, "其他強隊": "#8f889f"}.get(g_, "#c9c3d6") for g_ in keep],
                                             line=dict(width=1.5, color=SURFACE)),
                                 hovertemplate="%{y}<br>最後 10 場 %{x}<extra></extra>"))
        fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
        fig.update_xaxes(title=axis_, showgrid=True, gridcolor=GRID, tickformat=".0%" if "%" in f_ else None)
        fig.update_layout(legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(style(fig, 300), width="stretch", config={"displayModeBar": False})
        up = {g_: (B.loc[g_, "out_rate"] - A.loc[g_, "out_rate"]) * 100 for g_ in RE_GRPS if g_ in A.index and pd.notna(A.loc[g_, "out_rate"])}
        lines = []
        if "冠軍" in up:
            lines.append(f"<b>冠軍最後 10 場，前 3 號主力缺陣比例從 {A.loc['冠軍', 'out_rate']:.0%} 變成 {B.loc['冠軍', 'out_rate']:.0%}"
                         f"（{up['冠軍']:+.1f} 個百分點）。</b>")
        others = "、".join(f"{g_} {up[g_]:+.1f}" for g_ in RE_GRPS[1:] if g_ in up and pd.notna(up[g_]))
        if others:
            lines.append(f"其他三組（個百分點）：{others}。")
        lines.append("讀法：缺陣比例是「看主力」的指標，固定用它判斷假設；上面的切換只是換個角度看同一件事"
                     "（輪休→主力上場分鐘變少、上場人數變多）。沒進季後賽的球隊季末也常讓主力收工（養傷、看年輕球員）。")
        chk = None
        if "冠軍" in up and "其他強隊" in up:
            strong_up = (B.loc[["冠軍", "其他強隊"], "out_rate"].mean() - A.loc[["冠軍", "其他強隊"], "out_rate"].mean()) * 100
            chk = (("前段成立" if strong_up >= 5 else "前段不成立") + f"：強隊主力缺陣比例平均 {strong_up:+.1f} 個百分點（門檻 +5）；"
                   + ("中段成立" if up["冠軍"] > up["其他強隊"] else "中段不成立") + f"：冠軍 {up['冠軍']:+.1f}、其他強隊 {up['其他強隊']:+.1f}。")
        insight(lines, where=slot1, check=chk)
        with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
            term_table(["前 3 號主力", "主力缺陣比例", "最後 10 場／前面", "其他強隊", "主力全員上場的比賽"],
                       first_note="資料庫只知道「沒有上場」，<b>不知道原因</b>（輪休、受傷、禁賽、被交易都可能）。"
                                  "主力被交易走以後、加入球隊以前的比賽不算缺陣；但季末受傷和季末輪休分不出來。")

        # ===== 2 每一位冠軍 =====
        st.divider()
        slot2 = section("2　每一位冠軍：最後 10 場有沒有讓主力休息？",
                        "灰點＝前面的主力缺陣比例、彩色點＝最後 10 場；括號是最後 10 場的戰績")
        C = RE[RE["grp"] == "冠軍"]
        if C.empty:
            st.info("資料庫裡還沒有冠軍球季的資料。")
        else:
            CA = C[C["seg"] == "前面"].set_index("season")
            CB = C[C["seg"] == "最後10場"].set_index("season")
            ss = sorted(set(CA.index) & set(CB.index))
            ra = [CA.loc[s_, "core_out"] / max(CA.loc[s_, "core_slots"], 1) for s_ in ss]
            rb = [CB.loc[s_, "core_out"] / max(CB.loc[s_, "core_slots"], 1) for s_ in ss]
            ab = [CA.loc[s_, "abbreviation"] for s_ in ss]
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}（{CB.loc[s_, 'wins']:.0f}-{CB.loc[s_, 'games'] - CB.loc[s_, 'wins']:.0f}）" for s_, a_ in zip(ss, ab)]
            fig = go.Figure()
            for lab, a1, b1 in zip(labels, ra, rb):
                fig.add_trace(go.Scatter(x=[a1, b1], y=[lab, lab], mode="lines", line=dict(color="#d9d3e6", width=3),
                                         showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=ra, y=labels, mode="markers", name="前面",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>前面缺陣 %{x:.0%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=rb, y=labels, mode="markers", name="最後 10 場",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in ab], line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>最後 10 場缺陣 %{x:.0%}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="前 3 號主力缺陣比例", tickformat=".0%", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 90 + 34 * len(ss)), width="stretch", config={"displayModeBar": False})
            k_up = sum(b1 > a1 for a1, b1 in zip(ra, rb))
            i_max = max(range(len(ss)), key=lambda i: rb[i] - ra[i])
            insight([f"<b>{len(ss)} 位冠軍裡，{k_up} 位最後 10 場的主力缺陣比前面多。</b>",
                     f"差最多的是 {ss[i_max]} {ALL_ZH.get(ab[i_max], ab[i_max])}：{ra[i_max]:.0%} → {rb[i_max]:.0%}。",
                     "2019-20 的最後幾場是 7、8 月泡泡園區的「種子排名賽」，和一般季末不同。"], where=slot2)
            with st.expander("看每一位冠軍的數字"):
                nice_table(pd.DataFrame({"球季": ss, "冠軍": [ALL_ZH.get(a, a) for a in ab], "_key": ab,
                                         "前面缺陣": [f"{v:.0%}" for v in ra], "最後 10 場缺陣": [f"{v:.0%}" for v in rb],
                                         "前面勝率": [f"{CA.loc[s_, 'wins'] / CA.loc[s_, 'games']:.0%}" for s_ in ss],
                                         "最後 10 場戰績": [f"{CB.loc[s_, 'wins']:.0f}-{CB.loc[s_, 'games'] - CB.loc[s_, 'wins']:.0f}" for s_ in ss],
                                         "主力上場分鐘（前面 → 最後 10 場）": [f"{CA.loc[s_, 'core_min']:.1f} → {CB.loc[s_, 'core_min']:.1f}" for s_ in ss]}),
                           num_cols=("前面缺陣", "最後 10 場缺陣", "前面勝率", "最後 10 場戰績"), dot_col="冠軍", colors=TEAM_COLORS)

        # ===== 3 交叉驗證：只看主力全員上場的比賽 =====
        st.divider()
        slot3 = section("3　交叉驗證：季末勝率下滑，是輪休造成的嗎？",
                        "每一組兩根長條：最後 10 場 − 前面的勝率變化；灰＝所有比賽、紫＝只看 3 位主力都上場的比賽。紫色那根變短＝下滑主要來自輪休")
        rows = []
        for g_ in RE_GRPS:
            if g_ in A.index and pd.notna(A.loc[g_, "win"]) and pd.notna(B.loc[g_, "win"]):
                rows.append({"grp": g_, "所有比賽": (B.loc[g_, "win"] - A.loc[g_, "win"]) * 100,
                             "只看主力全員上場": (B.loc[g_, "win_full"] - A.loc[g_, "win_full"]) * 100,
                             "opp": (B.loc[g_, "opp_win"] - A.loc[g_, "opp_win"]) * 100})
        W = pd.DataFrame(rows)
        fig = go.Figure()
        for c_, colr in [("所有比賽", "#b3adc2"), ("只看主力全員上場", ACCENT)]:
            fig.add_trace(go.Bar(x=W["grp"], y=W[c_], name=c_, marker_color=colr, text=[f"{v:+.1f}" for v in W[c_]],
                                 textposition="outside", hovertemplate="%{x}　" + c_ + "：%{y:+.1f} 個百分點<extra></extra>"))
        rounded(fig)
        fig.add_hline(y=0, line_color=MUTED, line_width=1)
        fig.update_xaxes(type="category")
        fig.update_yaxes(title="最後 10 場 − 前面（勝率，百分點）")
        fig.update_layout(barmode="group", legend=dict(orientation="h", y=1.1, x=0))
        st.plotly_chart(style(fig, 340), width="stretch", config={"displayModeBar": False})
        Wi = W.set_index("grp")
        sg = [g_ for g_ in ["冠軍", "其他強隊"] if g_ in Wi.index]
        if sg:
            d_all, d_full = Wi.loc[sg, "所有比賽"].mean(), Wi.loc[sg, "只看主力全員上場"].mean()
            insight([f"<b>強隊最後 10 場勝率 {d_all:+.1f} 個百分點；只看主力全員上場的比賽是 {d_full:+.1f}。</b>",
                     f"最後 10 場遇到的對手整季勝率，比前面 {Wi.loc[sg, 'opp'].mean():+.1f} 個百分點"
                     "（季末對手比較強或比較弱，也會讓勝率變，所以一起列出來）。",
                     "限制：主力全員上場的比賽，可能剛好是比較重要、對手比較強的比賽；最後 10 場只有 10 場，單一隊季起伏很大，要看各組合計。"],
                    where=slot3,
                    check=(("後段成立（交叉驗證）" if d_all < 0 and abs(d_full) <= 3 else "後段不成立（交叉驗證）")
                           + f"：強隊季末勝率 {d_all:+.1f}，扣掉輪休後 {d_full:+.1f} 個百分點（門檻：下滑、而且扣掉後在 ±3 以內）。"))


# =====================================================================
# 每頁共用的結尾：頁首摘要、資料來源與方法、相關頁面、上一頁／下一頁（1030-1、1030-2、1030-4）
# =====================================================================
# 相關頁面：（頁面, 為什麼要接著看）
# ---------- 贏球與輸球：冠軍輸球那幾場，是哪一項數據掉最多？（2026-11-06）----------
WL_METRICS = {   # 顯示名稱 → (欄位, 格式, 越高越好?)
    "真實命中率": ("ts", ".1%", True),
    "三分命中率": ("fg3_pct", ".1%", True),
    "兩分命中率": ("fg2_pct", ".1%", True),
    "罰球出手率": ("fta_rate", ".2f", True),
    "失誤": ("tov", ".1f", False),
    "進攻籃板": ("oreb", ".1f", True),
    "防守籃板": ("dreb", ".1f", True),
    "助攻": ("ast", ".1f", True),
    "抄截": ("stl", ".1f", True),
    "阻攻": ("blk", ".1f", True),
    "犯規": ("pf", ".1f", False),
}
TERMS.update({
    "贏球場 − 輸球場": ("同一隊、同一季，贏球那幾場的平均減掉輸球那幾場的平均", "失誤、犯規越少越好，所以反過來減，正數一樣代表「贏球時比較好」"),
    "標準差（本頁）": ("這隊這一季每場數字「平常會上下跳多少」；差 1 個標準差＝差了一場正常的起伏那麼多", "把不同單位（%、次數）換成同一把尺，才能比哪一項掉最多"),
    "真實命中率": ("把兩分、三分、罰球都算進去的命中率", "得分 ÷［2 ×（投籃出手 ＋ 0.44 × 罰球出手）］"),
    "罰球出手率": ("每投 1 次籃，換到幾次罰球；越高代表越常切入、造犯規", "罰球出手 ÷ 投籃出手"),
    "其他強隊": ("整季勝率六成以上、但那一季沒有奪冠的球隊", "和月份趨勢頁同一個定義"),
})
WL_SHOOT = {"真實命中率", "三分命中率", "兩分命中率"}


@st.cache_data(ttl=900, show_spinner="讀取贏球場／輸球場的平均數據中…")
def load_wl_splits():
    """team_wl_splits_mv（docs/sql/2026-11-06_贏球與輸球.sql 建立）；還沒建立就回傳 None"""
    try:
        return fetch_all("team_wl_splits_mv", ["team_id", "season", "season_type", "wl"])
    except Exception:
        return None


def prep_wl(df, season_type, strong=0.6):
    """一隊一季一列：每項指標「贏球場平均 − 輸球場平均」換成幾個標準差（正數＝贏球時比較好）"""
    d = df[df["season_type"] == season_type].copy()
    num = ["games"] + [c for c, _, _ in WL_METRICS.values()] + [f"sd_{c}" for c, _, _ in WL_METRICS.values()]
    for c in num:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    keys = ["team_id", "abbreviation", "season"]
    w = d[d["wl"] == "W"].set_index(keys)
    l_ = d[d["wl"] == "L"].set_index(keys)
    out = w[["games"]].rename(columns={"games": "n_w"}).join(l_[["games"]].rename(columns={"games": "n_l"}), how="inner")
    for name, (c, _, up) in WL_METRICS.items():
        out[f"w_{c}"], out[f"l_{c}"] = w[c], l_[c]
        sd = w[f"sd_{c}"].where(w[f"sd_{c}"] > 0)
        out[f"z_{c}"] = (w[c] - l_[c]) / sd * (1 if up else -1)
    out = out.reset_index()
    out = out[(out["n_w"] >= 5) & (out["n_l"] >= 5)]          # 贏或輸不到 5 場的球季，平均不可靠
    out["win_pct"] = out["n_w"] / (out["n_w"] + out["n_l"])
    out["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(out["season"], out["abbreviation"])]
    out["grp"] = "其他球隊"
    out.loc[(~out["champion"]) & (out["win_pct"] >= strong), "grp"] = "其他強隊"
    out.loc[out["champion"], "grp"] = "冠軍"
    return out[out["season"] != ALL_SEASONS[-1]]                # 本季還沒打完


if PAGE == "贏球與輸球":
    hypothesis("冠軍輸球的那幾場，是哪一項數據掉最多？是投不進，還是失誤、籃板這類「打法亂掉」？",
               "冠軍輸球時掉最多的是投籃命中（真實命中率、三分命中率），不是失誤或籃板；而且其他強隊也是一樣——輸球主要是手感，不是努力不夠。")
    WL_RAW = load_wl_splits()
    if WL_RAW is None or WL_RAW.empty:
        st.info("尚未載入資料，請先到 Supabase → SQL Editor 執行 docs/sql/2026-11-06_贏球與輸球.sql"
                "（建立 team_wl_splits_mv），再按左側「重新讀取最新資料」。")
    else:
        wl_type = seg("比賽類型", ["例行賽", "季後賽"], key="wl_type")
        WL = prep_wl(WL_RAW, "Regular Season" if wl_type == "例行賽" else "Playoffs")
        st.caption(f"目前用資料庫已載入球員逐場數據的 {WL['abbreviation'].nunique()} 隊、{WL['season'].nunique()} 季計算"
                   "（每天自動增加 2 隊）；贏或輸不到 5 場的球季不列入。")
        names = list(WL_METRICS)
        if WL.empty or not WL["champion"].any():
            st.info("這個條件下還沒有足夠的冠軍球季（季後賽冠軍輸球的場數常常不到 5 場，可以先看例行賽）。")
        else:
            # ===== 1. 哪一項掉最多 =====
            slot1 = section("1　冠軍輸球時，哪一項掉最多？",
                            "長條＝贏球場平均 − 輸球場平均，換成「幾個標準差」，不同單位的數據才能放在一起比；越長代表輸球時掉越多。"
                            "失誤、犯規是越少越好，已經反過來算（輸球時失誤變多，長條一樣往右）")
            G = WL.groupby("grp")[[f"z_{WL_METRICS[n][0]}" for n in names]].mean()
            G.columns = names
            order = G.loc["冠軍"].sort_values().index.tolist()
            fig = go.Figure()
            for grp_, color in [("其他球隊", "#d9d4e3"), ("其他強隊", "#a59db5"), ("冠軍", ACCENT)]:
                if grp_ in G.index:
                    n_ = int((WL["grp"] == grp_).sum())
                    fig.add_trace(go.Bar(y=order, x=G.loc[grp_, order], orientation="h", name=f"{grp_}（{n_} 季）",
                                         marker_color=color,
                                         hovertemplate="%{y}：贏球比輸球好 %{x:.2f} 個標準差<extra>" + grp_ + "</extra>"))
            fig.add_vline(x=0, line=dict(color=INK_2, width=1))
            fig.update_layout(barmode="group", bargap=0.25, legend=dict(traceorder="reversed"))
            fig.update_xaxes(title="贏球場 − 輸球場（標準差；越大＝輸球時掉越多）")
            rounded(fig)
            st.plotly_chart(style(fig, 520), width="stretch")
            ch = G.loc["冠軍"].sort_values(ascending=False)
            top, second = ch.index[0], ch.index[1]
            effort = [n for n in ["失誤", "進攻籃板"] if n in ch.index]
            lines = [f"冠軍輸球時掉最多的是{top}（平均 {ch.iloc[0]:.2f} 個標準差），其次是{second}（{ch.iloc[1]:.2f}）。",
                     "「努力型」數據掉得少：" + "、".join(f"{n} {ch[n]:.2f}" for n in effort) + "。" if effort else "",
                     ("其他強隊掉最多的也是" + G.loc["其他強隊"].idxmax() + "。") if "其他強隊" in G.index else "",
                     "讀法：防守籃板常常是「結果」不是原因——對手投不進，我們才搶得到防守籃板，所以它也會在贏球時比較多。"]
            shoot_top = top in WL_SHOOT
            same = "其他強隊" in G.index and G.loc["其他強隊"].idxmax() in WL_SHOOT
            insight(lines, where=slot1, label="發現",
                    check=("成立：冠軍輸球主要是投不進，其他強隊也一樣。" if shoot_top and same else
                           "部分成立：冠軍輸球主要是投不進，但其他強隊掉最多的是別的項目。" if shoot_top else
                           f"不成立：冠軍輸球時掉最多的是{top}，不是投籃命中。"))
            with st.expander("名詞小辭典"):
                term_table(["贏球場 − 輸球場", "標準差（本頁）", "真實命中率", "罰球出手率", "其他強隊"],
                           first_note="只看自己隊的數據，不知道對手那一場打得多好；輸球可能是對手手感太好，不一定是自己變差。")

            # ===== 2. 每一位冠軍都一樣嗎 =====
            st.divider()
            slot2 = section("2　每一位冠軍都是這樣輸球的嗎？",
                            "一列一位冠軍、一欄一項數據，顏色越深＝那一項輸球時掉越多；每一列框起來的是這位冠軍掉最多的那一項")
            C = WL[WL["champion"]].sort_values("season")
            zc = [f"z_{WL_METRICS[n][0]}" for n in order[::-1]]
            Z = C[zc].to_numpy()
            ylab = [f"{s_} {team_label(a_)}" for s_, a_ in zip(C["season"], C["abbreviation"])]
            xlab = order[::-1]
            fig = go.Figure(go.Heatmap(
                z=Z, x=xlab, y=ylab, zmin=0, zmax=max(1.0, float(pd.Series(Z.ravel()).quantile(0.95))),
                colorscale=[[i / (len(PURPLE_RAMP) - 1), c_] for i, c_ in enumerate(PURPLE_RAMP)], xgap=3, ygap=3,
                text=[[f"{v:.1f}" if pd.notna(v) else "" for v in row] for row in Z], texttemplate="%{text}",
                hovertemplate="%{y}<br>%{x}：贏球比輸球好 %{z:.2f} 個標準差<extra></extra>",
                colorbar=dict(title="標準差", thickness=10)))
            best = C[zc].idxmax(axis=1).map(lambda c_: xlab[zc.index(c_)])
            for i, b in enumerate(best):
                j = xlab.index(b)
                fig.add_shape(type="rect", x0=j - 0.5, x1=j + 0.5, y0=i - 0.5, y1=i + 0.5,
                              line=dict(color=INK, width=2))
            fig.update_yaxes(autorange="reversed", type="category")
            fig.update_xaxes(side="top", type="category")
            st.plotly_chart(style(fig, 120 + 30 * len(C)), width="stretch")
            cnt = best.value_counts()
            n_shoot = int(best.isin(WL_SHOOT).sum())
            insight(where=slot2, label="發現", lines=[
                f"{len(C)} 位冠軍裡，有 {n_shoot} 位輸球時掉最多的是投籃命中（真實／三分／兩分命中率）。",
                "掉最多的項目：" + "、".join(f"{k} {v} 位" for k, v in cnt.items()) + "。",
                ("例外：" + "、".join([f"{ylab[i]}（{b}）" for i, b in enumerate(best) if b not in WL_SHOOT][:6])
                 + ("…" if len(C) - n_shoot > 6 else "") + "。")
                if n_shoot < len(C) else "",
            ], check=("成立：大多數冠軍都是「投不進就輸」。" if n_shoot >= len(C) * 0.6 else
                      "不成立：超過四成的冠軍，輸球時掉最多的不是投籃命中。"))

            # ===== 3. 單一冠軍的實際數字 =====
            st.divider()
            section("3　單一冠軍：贏球場 vs 輸球場的實際數字", "選一位冠軍，看每一項數據贏球時、輸球時各是多少")
            pick = st.selectbox("冠軍球季", ylab[::-1], key="wl_pick")
            r = C.iloc[ylab.index(pick)]
            rows = []
            for n in order[::-1]:
                c_, f_, up = WL_METRICS[n]
                rows.append({"數據": n, "贏球場": fmt(r[f"w_{c_}"], f_), "輸球場": fmt(r[f"l_{c_}"], f_),
                             "差（標準差）": fmt(r[f"z_{c_}"], "+.2f"), "_z": min(max(r[f"z_{c_}"], 0) / 1.5, 1)})
            st.caption(f"{pick}：贏 {int(r['n_w'])} 場、輸 {int(r['n_l'])} 場（{wl_type}）")
            nice_table(pd.DataFrame(rows), num_cols=("贏球場", "輸球場", "差（標準差）"), bars={"差（標準差）": "_z"})


RELATED = {
    "誰補上得分": [("頭號得分手缺陣", "少了他之後勝率掉多少"), ("缺陣場的對手", "缺陣的那幾場，對手是不是比較弱"),
              ("陣容深度", "平常的得分就分散在幾個人身上")],
    "缺陣場的對手": [("頭號得分手缺陣", "這頁是在檢查那一頁的勝率下滑公不公平"), ("月份趨勢", "季末輪休：最後 10 場的勝率"), ("賽程與休息", "另一個「對手強弱以外」的因素：累不累")],
    "輸球時的球星": [("頭號得分手缺陣", "他沒上場的比賽，球隊還贏得了嗎"), ("陣容深度", "得分本來就靠幾個人"),
               ("得分穩定度", "球星每場得分的起伏")],
    "頭號得分手缺陣": [("陣容深度", "得分分散在幾個人身上"), ("得分穩定度", "頭號球星每場的起伏"),
                ("籤運與傷兵", "對手主力缺陣，冠軍是不是撿到便宜")],
    "奪冠前一季": [("冠軍球季比較", "奪冠那季和自己「所有」其他球季比，不只前一季"), ("防守端", "防守進步，是哪一項防守變好"), ("冠軍密碼", "奪冠季在全聯盟排第幾")],
    "每日戰報": [("球季趨勢", "把今天的表現放回 20 季的長期走勢裡看"), ("冠軍密碼", "強隊和冠軍差在哪裡")],
    "冠軍密碼": [("投籃分布", "Q2 的三分趨勢，換成球場上的出手位置來看"), ("戰術使用", "淨效率高，是靠哪些戰術打出來的"),
             ("籤運與傷兵", "Q3 說最強的隊不一定奪冠，那是不是靠運氣")],
    "投籃分布": [("戰術使用", "出手位置背後，是哪一種戰術創造的"), ("冠軍密碼", "三分時代有沒有造就冠軍（Q2）")],
    "戰術使用": [("投籃分布", "戰術最後換成哪些位置的出手"), ("上場陣容", "誰在場上執行這些戰術")],
    "上場陣容": [("跑動距離", "核心五人上場時，球隊跑得多不多"), ("戰術使用", "核心陣容最常打什麼戰術"),
             ("賽程與休息", "上場時間多，背靠背時會不會撐不住")],
    "跑動距離": [("賽程與休息", "跑得多的隊，背靠背時會不會比較吃虧"), ("上場陣容", "誰跑最多，是不是核心五人")],
    "籤運與傷兵": [("賽程與休息", "另一種「運氣」：賽程密度"), ("主場與客場", "季後賽的主場優勢有多大"),
              ("冠軍密碼", "冠軍的實力排名（Q1）")],
    "賽程與休息": [("主場與客場", "另一個賽程因素：在哪裡打"), ("跑動距離", "累不累，也和跑多少有關")],
    "主場與客場": [("賽程與休息", "客場常常也是背靠背，兩個因素一起看"), ("籤運與傷兵", "季後賽主場優勢和對手強弱"),
              ("例行賽與季後賽", "季後賽裡，球星的表現有沒有變")],
    "例行賽與季後賽": [("籤運與傷兵", "季後賽遇到的對手強不強"), ("球員", "看單一球員的逐季與逐場數據"),
                ("主場與客場", "冠軍在季後賽客場打得如何")],
    "得分穩定度": [("例行賽與季後賽", "季後賽裡，球星的平均表現有沒有變"), ("球員", "看單一球員的逐場得分"),
              ("月份趨勢", "整隊的表現，季初和季末穩不穩")],
    "月份趨勢": [("賽程與休息", "季末的背靠背多不多、累不累"), ("例行賽與季後賽", "越打越好，進了季後賽還在嗎"),
             ("得分穩定度", "球星每場的起伏")],
    "節奏與勝率": [("冠軍密碼", "淨效率用每 100 回合算，已經把節奏扣掉"), ("跑動距離", "打得快的隊，是不是也跑得比較多"),
              ("例行賽與季後賽", "季後賽變慢，球星的得分怎麼變")],
    "陣容深度": [("上場陣容", "核心五人同時在場的時間，是不是也一樣集中"), ("得分穩定度", "頭號得分手每場穩不穩"),
             ("例行賽與季後賽", "季後賽裡，球星的得分和命中率怎麼變")],
    "球季趨勢": [("球隊 × 球季", "同一個指標，用熱力圖一次看完"), ("冠軍球季比較", "奪冠那季比平常強多少")],
    "球隊 × 球季": [("球季趨勢", "選幾隊看折線，變化更清楚"), ("冠軍球季比較", "★ 那幾格和其他球季差多少")],
    "冠軍球季比較": [("冠軍密碼", "冠軍在全聯盟排第幾"), ("球員", "奪冠那季是哪些球員撐起來的")],
    "球員": [("冠軍球季比較", "球員的變化對球隊奪冠季的影響"), ("上場陣容", "球員和誰一起上場最久")],
    "數據表": [("球季趨勢", "把表格變成折線圖"), ("球隊 × 球季", "把表格變成熱力圖")],
}
# 資料來源與方法：（用了哪些表, 範圍, 怎麼算）
SOURCES = {
    "誰補上得分": ("star_fill_mv（預先算好的彙總表，docs/sql/2026-11-17_誰補上得分.sql，由 player_game_stats、team_games、games 算）、"
              "league_team_seasons（整季勝率，分出其他強隊）、champions", "2006-07 起、30 隊；只看例行賽；本季不列入",
              "頭號得分手＝例行賽場均得分隊內最高、至少上場 20 場；缺陣＝球隊有打、他沒有上場；隊友每場得分＝那一類比賽隊友一共得幾分 ÷ 球隊場數；"
              "補回比例＝（缺陣時 − 有他時）÷ 他有上場時的場均；各組依缺陣場數加權合計。不知道缺陣原因，也沒有扣掉對手強弱。"),
    "缺陣場的對手": ("star_absence_opp_mv（預先算好的彙總表，docs/sql/2026-11-16_缺陣場的對手.sql，由 player_game_stats、team_games、games、league_team_seasons 算）、champions",
               "2006-07 起、全聯盟 30 隊；例行賽；本季不列入",
               "頭號得分手＝這一季這隊例行賽場均得分最高、至少上場 20 場，季中被交易的只算在隊期間；缺陣＝球隊有比賽、他沒有上場紀錄；"
               "對手強弱＝對手那一季例行賽淨效率；「只和同樣強弱的對手比」＝對手淨效率 < 0 和 ≥ 0 兩組各自相減，再依缺陣場數加權平均；"
               "各組都是先把場數、勝場加總再除（合併計算）。"),
    "輸球時的球星": ("star_wl_mv（預先算好的彙總表，docs/sql/2026-11-15_輸球時的球星.sql，由 player_game_stats、team_games、games 算）、"
               "league_team_seasons（勝率、其他強隊）、champions",
               "2006-07 起；30 隊；例行賽本季不列入",
               "頭號得分手＝這一季在這隊例行賽場均得分最高、至少上場 20 場；只算他有上場（超過 0 分鐘）的比賽；"
               "隊友＝同一場全隊得分 − 他的得分；輸球時少了幾 %＝（贏球場均 − 輸球場均）÷ 贏球場均；"
               "各組先把比賽加總再算（合併計算），單一隊季輸球場數少時不會把平均拉歪。"),
    "頭號得分手缺陣": ("star_absence_mv（由 player_game_stats、team_games 算好的彙總表）、league_team_seasons（勝率）、champions",
                "2006-07 起、例行賽；全聯盟 30 隊；本季不列入",
                "頭號得分手＝這一季在這一隊場均得分最高、至少上場 20 場；缺陣＝球隊有比賽但他沒有上場（0 分鐘也算缺陣）；"
                "季中被交易的球員只算他替這隊上場期間的比賽；各組勝率是把所有比賽加起來算（不是各隊勝率的平均）；"
                "其他強隊＝例行賽勝率六成以上、沒奪冠。缺陣原因（受傷、休息、禁賽）資料庫沒有。"),
    "奪冠前一季": ("league_team_seasons（全聯盟 30 隊每季）、champions", "例行賽；2007-08 起（2006-07 沒有前一季的資料）",
              "每一項在同一季 30 隊中排名（防守效率、失誤率越低越好）；排名進步＝前一季名次 − 奪冠季名次；"
              "進攻／防守進步＝（這隊 − 同季平均）的變化，單位是每 100 回合幾分，防守已經反過來（正數＝守得更好）；"
              "其他強隊＝同一季勝率六成以上、沒有奪冠的隊季；同一支球隊用球隊編號對應（搬家改名也算同一隊）。"),
    "冠軍密碼": ("league_team_seasons（全聯盟 30 隊每季）、champions", "例行賽、上方球季範圍內有冠軍的球季",
             "每項指標在同一季 30 隊中排名（1＝最好；防守效率、失誤率越低越好）；聯盟平均用「全聯盟總數 ÷ 總數」，不是 30 隊平均的平均；"
             "Q3 的實力差距用 30 隊淨效率（或勝率）的標準差。"),
    "投籃分布": ("shots（每一次出手）、shot_zone_league（聯盟各區）、shot_zone_team／shot_zone_player 檢視表",
             "2016-17 起；八支冠軍隊", "區域依 NBA 官方的 zone_basic／zone_area 分類；每次出手得分＝命中率 × 分值（三分區 3、其他 2）。"),
    "戰術使用": ("playtypes_team（30 隊）、league_team_seasons、champions", "2016-17 起",
             "使用率＝這種戰術的回合 ÷ 全部回合；每回合得分（PPP）＝得分 ÷ 回合；聯盟 PPP 用總得分 ÷ 總回合（加權）；"
             "奪冠方程式用效率和勝率的相關係數當權重，權重和分數用同一批資料算，是描述不是預測。"),
    "跑動距離": ("tracking_speed（entity＝team／player）、league_team_seasons（勝率）、champions", "2016-17 起；全聯盟 30 隊與所有球員",
             "NBA 官方追蹤數據的每場平均跑動距離（英里，網站換算成公里，1 英里＝1.609 公里）與平均速度；"
             "「比同季聯盟多多少」＝這隊 − 同季 30 隊平均，用來排除年代差異；相關係數 |r| < 0.1 幾乎沒有關係、0.3 以上算中等。"),
    "賽程與休息": ("team_games（輸贏）、games（日期、球季、比賽類型）、champions", "只限資料庫已載入比賽的球隊（每天增加 2 隊）；例行賽",
              "休息天數＝和同一季前一場相差的天數 − 1（0＝背靠背）；每季第一場沒有前一場，不列入；"
              "只知道自己休息幾天，不知道對手是不是也在背靠背。"),
    "主場與客場": ("team_games（is_home、輸贏）、games（球季、比賽類型）、champions", "只限資料庫已載入比賽的球隊（每天增加 2 隊）",
              "主場優勢＝主場勝率 − 客場勝率（百分點）；季後賽只算冠軍那一季；2019-20 復賽在泡泡園區（沒有真正的主場）、"
              "2020-21 多數場館限制觀眾，這兩季的主場優勢要分開看。"),
    "例行賽與季後賽": ("player_season_stats（由 player_game_stats 加總）、champions", "2006-07 起；只限資料庫已載入球員逐場數據的球隊（每天增加 2 隊）",
                "球星＝例行賽場均得分隊內前 3 名、出賽至少 40 場，季後賽至少 4 場；真實命中率＝得分 ÷［2 ×（投籃出手 ＋ 0.44 × 罰球出手）］；"
                "變化＝季後賽 − 例行賽；季後賽只算同一隊（季中被交易的球員只算季後賽所在的那一隊）。"),
    "得分穩定度": ("player_scoring_spread_mv（由 player_game_stats 每一場算好的彙總表）、player_season_stats、champions",
              "2006-07 起；只限資料庫已載入球員逐場數據的球隊（每天增加 2 隊）",
              "起伏＝每場得分的標準差 ÷ 場均；同得分水準＝所有頭號球星「起伏 vs 場均」的最小平方法直線；"
              "低迷場＝得分不到自己這一季平均的六成；爆發場＝得分到自己平均的 1.5 倍以上；上場 0 分鐘的場次不算。"),
    "月份趨勢": ("team_games（輸贏）、games（日期、球季、比賽類型）、champions", "只限資料庫已載入比賽的球隊（每天增加 2 隊）；例行賽；本季不列入",
             "月份：10、11 月合併成「10–11 月」，4 月以後（含 2019-20 復賽的 7、8 月）合併成「4 月起」；"
             "前半季／後半季＝依這一季自己的場次切一半；其他強隊＝整季勝率六成以上、沒有奪冠的隊季。"),
    "節奏與勝率": ("league_team_seasons（全聯盟 30 隊每季：pace、勝負、例行賽／季後賽）、champions",
              "2006-07 起已經有冠軍的球季；本季不列入",
              "節奏＝每 48 分鐘回合數（NBA 官方）；比同季聯盟＝這隊 − 同季 30 隊平均；第幾快＝同季 30 隊排名（1＝最快）；"
              "相關係數 r 用「比同季平均快幾個回合」和例行賽勝率算；季後賽變化＝季後賽 − 例行賽，只算有打季後賽的隊。"),
    "陣容深度": ("player_season_stats（由 player_game_stats 加總）、league_team_seasons（勝負）、champions",
             "2006-07 起、資料庫已載入的球隊（30 隊）；本季不列入",
             "得分佔比＝球員整季得分 ÷ 全隊所有球員得分合計；有效得分人數＝1 ÷ Σ（得分佔比²）；"
             "其他強隊＝例行賽勝率六成以上、沒有奪冠；季後賽只算有打進季後賽的隊；季中被交易的球員分開算在各隊；"
             "第 2 節用「有效得分人數 − 同季平均」排除年代差異。"),
    "球季趨勢": ("team_season_stats（由 player_game_stats 加總）", "上方選的球隊、球季、比賽類型", "各項指標由整季加總後再算比例（例如三分命中率＝三分命中總數 ÷ 三分出手總數）。"),
    "球隊 × 球季": ("team_season_stats", "上方選的球隊、球季、比賽類型", "顏色由淺紫到深紫代表數值由低到高；★ 是奪冠球季。"),
    "冠軍球季比較": ("team_season_stats、champions", "上方選的球隊、球季、比賽類型", "奪冠球季的數值 − 同一隊其他球季的平均。"),
    "球員": ("player_season_stats、player_game_stats", "上方選的球隊、球季、比賽類型", "場均＝整季加總 ÷ 出賽場數；真實命中率＝得分 ÷［2 ×（出手 ＋ 0.44 × 罰球出手）］。"),
    "數據表": ("team_season_stats", "上方選的球隊、球季、比賽類型", "可排序、下載 Excel；指標算法見表格下方「指標說明」。"),
}
RELATED["贏球與輸球"] = [("冠軍密碼", "冠軍整季強在哪幾項（Q1 的 10 項指標）"),
                    ("投籃分布", "輸球常常是投不進，那冠軍平常從哪裡出手"),
                    ("例行賽與季後賽", "季後賽對手更強，球星的命中率會不會掉")]
SOURCES["贏球與輸球"] = ("team_wl_splits_mv（由 player_game_stats 加總成全隊每場，再分贏球場／輸球場平均；"
                     "docs/sql/2026-11-06_贏球與輸球.sql 建立）、champions",
                     "2006-07 起；只限資料庫已載入球員逐場數據的球隊（每天增加 2 隊）；贏或輸不到 5 場的球季不列入；本季不列入",
                     "差＝（贏球場平均 − 輸球場平均）÷ 這隊這季每場的標準差，失誤、犯規反過來算；"
                     "其他強隊＝整季勝率六成以上、沒奪冠；只有自己隊的數據，不知道對手那一場的表現。")
RELATED["防守端"] = [("冠軍密碼", "防守效率在 10 項指標裡排第幾（Q1）"), ("投籃分布", "換成進攻端：冠軍自己從哪裡出手"),
                    ("贏球與輸球", "輸球時是不是自己投不準")]
SOURCES["防守端"] = ("league_team_seasons（全聯盟 30 隊每季，含對手數據）、champions", "例行賽；所有已載入的球季",
                    "對手有效命中率＝（對手命中 ＋ 0.5 × 對手三分命中）÷ 對手出手；防守回合＝對手得分 ÷ 防守效率 × 100；"
                    "逼對手失誤率＝對手失誤 ÷ 防守回合；排名是同一季 30 隊裡排第幾（1＝最好）；"
                    "相關係數用「和同季平均的差」算，排除年代差異；沒有對手罰球數據，所以沒有「讓對手少罰球」這一項。")
RELATED["季後賽輪次"] = [("籤運與傷兵", "每一輪的對手，是不是剛好比較弱"),
                       ("例行賽與季後賽", "辛苦的那幾輪，球星表現怎麼變"),
                       ("主場與客場", "有沒有主場優勢，影響系列賽打多久")]
SOURCES["季後賽輪次"] = ("team_games（matchup、輸贏）、games（日期、比賽類型）、league_team_seasons（對手例行賽淨效率）、champions",
                        "2006-07 起；只限資料庫已載入比賽的球隊（30 隊都載入後就是全部季後賽）",
                        "同一季連續對同一個對手＝一個系列賽，第幾個系列賽＝第幾輪（附加賽不算）；只看贏下來（4 勝）的系列賽；"
                        "曾經落後＝某一場打完時敗場 > 勝場；其他晉級球隊＝同一輪也贏 4 場、但沒有奪冠；沒有每場得分，所以不看分差。")
OWN_SOURCES = {"每日戰報", "上場陣容", "籤運與傷兵"}   # 這幾頁本來就有自己的「資料來源與方法」


# ----- 奪冠隔年（2026-11-07）：相關頁面、資料來源與方法 -----
RELATED["奪冠隔年"] = [("奪冠前一季", "反過來看：奪冠前一季就很強了嗎"), ("冠軍球季比較", "奪冠那季比同一隊的其他球季強多少"), ("冠軍密碼", "冠軍在全聯盟排第幾")]
SOURCES["奪冠隔年"] = ('league_team_seasons（全聯盟 30 隊每季，例行賽與季後賽）、champions',
                       '例行賽；隔年要打完才算（最近一位冠軍先不列入）',
                       '淨效率比同季平均＝這隊 − 同季 30 隊平均；名次是同季 30 隊排名；其他強隊＝勝率六成以上、沒奪冠；交叉驗證用全部隊季畫「今年 → 隔年」的最小平方法直線，冠軍和直線的差＝比同樣強的球隊多掉幾分。')

# ----- 輸球之後（2026-11-08）：相關頁面、資料來源與方法 -----
RELATED["輸球之後"] = [("贏球與輸球", "冠軍輸球的那幾場，是哪一項數據掉最多"), ("賽程與休息", "輸球是不是因為背靠背"), ("月份趨勢", "整季來看，冠軍是不是越打越好")]
SOURCES["輸球之後"] = ('team_games（輸贏、主客場）、games（日期、球季、比賽類型）、champions',
                       '例行賽；本季還沒打完，先不列入',
                       '反彈＝輸球後下一場勝率 − 整季勝率；最長連敗依日期數連續的 L；預期勝率用兩隊整季勝率的 log5 公式，主場再加上聯盟整體主場多贏的比例；對手＝同一場比賽的另一隊。')

# ---------- 每一輪的球星：頭號得分手在季後賽每一輪怎麼變？（2026-11-18 每日任務）----------
SR_PAGE = "每一輪的球星"
SR_METRICS = {   # 顯示名稱 → (欄位, 單位, 是不是比例)
    "真實命中率": ("ts", "百分點", True),
    "場均得分": ("ppg", "分", False),
    "場均上場分鐘": ("mpg", "分鐘", False),
    "每 36 分鐘得分": ("p36", "分", False),
    "得分佔全隊比例": ("share", "百分點", True),
}
SR_ROUNDS = ["首輪", "次輪", "分區決賽", "總冠軍賽"]
TERMS.update({
    "頭號得分手": ("這一季在這隊例行賽場均得分最高、至少上場 20 場的球員；季後賽每一輪都看同一個人", "依例行賽場均得分排名"),
    "第幾輪": ("同一季的季後賽依日期排好，對手換人就是下一輪；附加賽不算", "1 首輪、2 次輪、3 分區決賽、4 總冠軍賽"),
    "比自己例行賽": ("同一位球員、同一季，這一輪的數字減掉他整季例行賽的數字；正數＝這一輪比平常好",
                "命中率、佔比的差用「百分點」：58% → 55% 是 −3 百分點"),
    "其他晉級球隊": ("同一季、同一輪也贏下系列賽、但最後沒有奪冠的球隊；總冠軍賽的贏家一定是冠軍，所以那一輪沒有對照組",
                "和「季後賽輪次」頁同一個定義"),
})


@st.cache_data(ttl=3600, show_spinner="讀取每一輪的球星彙總表中…")
def _sr_read():
    return fetch_all("star_round_mv", ["season", "team_id", "rnd"])


def sr_load():
    try:
        df = _sr_read()
        return df if not df.empty else None
    except Exception:
        return None


def sr_prep(df):
    """一隊一季一輪一列；算出這一輪和他自己例行賽的數字，以及兩者的差"""
    d = df.copy()
    num = ["rnd", "games", "wins", "reg_g", "reg_pts", "reg_fga", "reg_fta", "reg_min",
           "star_g", "star_pts", "star_fga", "star_fta", "star_min", "team_pts_on"]
    for c in num:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["rnd"].between(1, 4)].copy()
    pos = lambda s: s.where(s > 0)
    d["round"] = d["rnd"].astype(int).map(lambda r: SR_ROUNDS[r - 1])
    d["won"] = d["wins"] >= 4
    # 他在這一輪（只算有上場的比賽）
    d["ppg"] = d["star_pts"] / pos(d["star_g"])
    d["mpg"] = d["star_min"] / pos(d["star_g"])
    d["ts"] = d["star_pts"] / pos(2 * (d["star_fga"] + 0.44 * d["star_fta"]))
    d["p36"] = d["star_pts"] / pos(d["star_min"]) * 36
    d["share"] = d["star_pts"] / pos(d["team_pts_on"])
    # 他自己這一季的例行賽（基準）；例行賽的全隊得分佔比沒有存，所以佔比只比較輪與輪之間
    d["ppg_reg"] = d["reg_pts"] / pos(d["reg_g"])
    d["mpg_reg"] = d["reg_min"] / pos(d["reg_g"])
    d["ts_reg"] = d["reg_pts"] / pos(2 * (d["reg_fga"] + 0.44 * d["reg_fta"]))
    d["p36_reg"] = d["reg_pts"] / pos(d["reg_min"]) * 36
    for c in ["ppg", "mpg", "ts", "p36"]:
        d[f"d_{c}"] = d[c] - d[f"{c}_reg"]
    # 佔比：和他自己「首輪」的佔比比（沒有例行賽全隊得分）
    first = d[d["rnd"] == 1].set_index(["season", "team_id"])["share"]
    d["share_reg"] = [first.get((s_, t_)) for s_, t_ in zip(d["season"], d["team_id"])]
    d["d_share"] = d["share"] - d["share_reg"]
    d["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(d["season"], d["abbreviation"])]
    d["grp"] = d["champion"].map({True: "冠軍", False: "其他晉級球隊"})
    return d[d["star_g"] > 0]


def sr_group(d, col):
    """每一輪、每一組：用他在那一輪上場的場數加權的平均變化（打 7 場的系列賽比打 4 場的重）"""
    x = d.dropna(subset=[f"d_{col}"])
    x = x[x["champion"] | x["won"]]           # 對照組只留「也贏下這一輪」的球隊
    rows = []
    for (rd, grp), g in x.groupby(["rnd", "grp"]):
        w = g["star_g"]
        rows.append({"rnd": int(rd), "round": SR_ROUNDS[int(rd) - 1], "grp": grp,
                     "mean": (g[f"d_{col}"] * w).sum() / w.sum(), "n": len(g), "games": int(w.sum())})
    return pd.DataFrame(rows)


def sr_fmt(v, is_pct, unit):
    if pd.isna(v):
        return "-"
    return f"{v * 100:+.1f} 百分點" if is_pct else f"{v:+.1f} {unit}"


if PAGE == SR_PAGE:
    hypothesis("冠軍的頭號得分手，在季後賽越往後打得越好，還是越來越吃力？",
               "越往後對手越強，所以頭號得分手的真實命中率會一輪比一輪低（總冠軍賽比首輪掉更多）；"
               "但場均得分不會跟著掉，因為上場時間越來越長；"
               "而且和同一輪也晉級的其他球隊比，冠軍的頭號得分手命中率掉得比較少。")
    st.caption("這頁和「例行賽與季後賽」不同：那頁把整個季後賽合起來看，這頁把季後賽拆成四輪；"
               "和「季後賽輪次」也不同：那頁看球隊打得辛不辛苦，這頁看頭號得分手本人。")
    SR_RAW = sr_load()
    if SR_RAW is None:
        st.info("尚未載入資料，請先在 Supabase SQL Editor 執行 docs/sql/2026-11-18_每一輪的球星.sql"
                "（建立 star_round_mv），再按左側「重新讀取最新資料」。")
    else:
        SR = sr_prep(SR_RAW)
        CH = SR[SR["champion"]]
        if CH.empty:
            st.info("資料不足：彙總表裡還沒有冠軍的季後賽紀錄。")
        else:
            sr_m = seg("看哪一項", list(SR_METRICS), "sr_metric")
            col, unit, is_pct = SR_METRICS[sr_m]
            k = 100 if is_pct else 1
            base_txt = "他自己的首輪" if col == "share" else "他自己這一季的例行賽"

            # ===== 1. 冠軍 vs 其他晉級球隊：每一輪變多少 =====
            slot1 = section(f"1　每一輪，頭號得分手的{sr_m}比{base_txt}變多少？",
                            f"紫線＝冠軍、灰線＝同一輪也晉級的其他球隊；0 以上＝這一輪比{base_txt}好。"
                            "每一點是用「上場場數」加權的平均（打 7 場的系列賽比打 4 場的重）；"
                            "總冠軍賽的贏家一定是冠軍，所以灰線只到分區決賽")
            G = sr_group(SR, col)
            fig = go.Figure()
            for grp, colr, w_, dash in [("其他晉級球隊", "#8f889f", 2.2, "dot"), ("冠軍", ACCENT, 3.2, "solid")]:
                g_ = G[G["grp"] == grp].set_index("round").reindex(SR_ROUNDS)
                fig.add_trace(go.Scatter(
                    x=SR_ROUNDS, y=g_["mean"] * k, name=grp, mode="lines+markers+text",
                    line=dict(color=colr, width=w_, dash=dash), marker=dict(size=9, color=colr),
                    text=[("" if pd.isna(v) else f"{v * k:+.1f}") for v in g_["mean"]],
                    textposition="top center", textfont=dict(size=11, color=INK_2), cliponaxis=False,
                    customdata=g_[["n", "games"]].fillna(0).astype(int).values,
                    hovertemplate=grp + "<br>%{x}：%{y:+.1f} " + unit +
                                  "<br>%{customdata[0]} 位頭號得分手、%{customdata[1]} 場<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1))
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=SR_ROUNDS)
            fig.update_yaxes(title=f"比{base_txt}（{unit}）", tickformat="+.1f")
            fig.update_layout(legend=dict(orientation="h", y=1.1, x=0))
            st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})

            def gv(grp, rd, c=col):
                gg = sr_group(SR, c)
                x = gg[(gg["grp"] == grp) & (gg["rnd"] == rd)]
                return x["mean"].iloc[0] if len(x) else float("nan")

            c1, c4 = gv("冠軍", 1), gv("冠軍", 4)
            lines = [f"冠軍頭號得分手的{sr_m}：首輪 {sr_fmt(c1, is_pct, unit)}、總冠軍賽 {sr_fmt(c4, is_pct, unit)}"
                     f"（和{base_txt}比）。"]
            beat = [r_ for r_ in (1, 2, 3) if pd.notna(gv("冠軍", r_)) and pd.notna(gv("其他晉級球隊", r_))
                    and gv("冠軍", r_) > gv("其他晉級球隊", r_)]
            n_cmp = sum(1 for r_ in (1, 2, 3) if pd.notna(gv("冠軍", r_)) and pd.notna(gv("其他晉級球隊", r_)))
            if n_cmp:
                lines.append(f"首輪到分區決賽的 {n_cmp} 輪裡，有 {len(beat)} 輪冠軍比同一輪的其他晉級球隊好。")
            n_ch = CH[["season", "team_id"]].drop_duplicates().shape[0]
            if n_ch < 10:
                lines.append(f"目前只有 {n_ch} 位冠軍，每一輪的平均起伏很大，先不要下結論。")
            lines.append("讀法：先看紫線是不是一路往下（越往後越吃力），再看同一輪紫線是不是在灰線上面"
                         "（冠軍比別人撐得住）。命中率要切到「真實命中率」看、得分和上場時間切到另外兩項看。")
            # 對照假設（固定用三項，不受上面的切換影響）
            t1, t4 = gv("冠軍", 1, "ts"), gv("冠軍", 4, "ts")
            p34 = pd.Series([gv("冠軍", 3, "ppg"), gv("冠軍", 4, "ppg")]).mean()
            m1, m34 = gv("冠軍", 1, "mpg"), pd.Series([gv("冠軍", 3, "mpg"), gv("冠軍", 4, "mpg")]).mean()
            tb = [r_ for r_ in (1, 2, 3) if pd.notna(gv("冠軍", r_, "ts")) and pd.notna(gv("其他晉級球隊", r_, "ts"))]
            tw = [r_ for r_ in tb if gv("冠軍", r_, "ts") > gv("其他晉級球隊", r_, "ts")]
            chk = None
            if pd.notna(t1) and pd.notna(t4):
                chk = (("前段成立" if t4 < t1 else "前段不成立")
                       + f"：真實命中率首輪 {sr_fmt(t1, True, '')}、總冠軍賽 {sr_fmt(t4, True, '')}；"
                       + (("中段成立" if p34 >= -1 and m34 > m1 else "中段不成立")
                          + f"：分區決賽＋總冠軍賽場均得分 {p34:+.1f} 分、上場時間比首輪 {m34 - m1:+.1f} 分鐘；"
                          if pd.notna(p34) and pd.notna(m1) and pd.notna(m34) else "")
                       + (("後段成立" if len(tw) >= 2 else "後段不成立") + f"：{len(tb)} 輪裡有 {len(tw)} 輪命中率比其他晉級球隊好。"
                          if tb else "後段無法判斷：還沒有其他晉級球隊可以比。"))
            insight(lines, where=slot1, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["頭號得分手", "第幾輪", "比自己例行賽", "其他晉級球隊", "真實命中率", "每 36 分鐘得分"],
                           first_note="季後賽越往後，對手越強、防守越專心，命中率「本來就會」掉一點；"
                                      "要看的是冠軍的頭號得分手有沒有掉得比別人少。另外每一輪只有 4～7 場，"
                                      "單一球員的起伏很大，請看各組加權平均。")

            # ===== 2. 每一位冠軍：四輪的路線 =====
            st.divider()
            slot2 = section(f"2　每一位冠軍的頭號得分手：四輪的{sr_m}",
                            f"一列一位冠軍、一欄一輪；格子上面是這一輪的{sr_m}，下面括號是比{base_txt}多或少；"
                            "顏色越深＝數字越高。空白＝那一輪他沒有上場")
            CH = CH.sort_values(["season", "rnd"])
            keys_ = CH[["season", "abbreviation", "player_name"]].drop_duplicates()
            ylab = [f"{s_} {ALL_ZH.get(a_, a_)}　{p_}" for s_, a_, p_ in zip(keys_["season"], keys_["abbreviation"], keys_["player_name"])]
            Z = CH.pivot_table(index=["season", "abbreviation", "player_name"], columns="rnd", values=col, aggfunc="first")
            Zd = CH.pivot_table(index=["season", "abbreviation", "player_name"], columns="rnd", values=f"d_{col}", aggfunc="first")
            idx = list(map(tuple, keys_.values))
            Z = Z.reindex(index=idx, columns=[1, 2, 3, 4])
            Zd = Zd.reindex(index=idx, columns=[1, 2, 3, 4])
            vf = (lambda v: f"{v:.1%}") if is_pct else (lambda v: f"{v:.1f}")
            txt = [[("" if pd.isna(v) else vf(v) + "<br>" + ("" if pd.isna(dv) else f"({dv * k:+.1f})"))
                    for v, dv in zip(r1, r2)] for r1, r2 in zip(Z.values, Zd.values)]
            zv = Z.values.astype(float)
            fig = go.Figure(go.Heatmap(
                z=zv, x=SR_ROUNDS, y=ylab, text=txt, texttemplate="%{text}", textfont=dict(size=11),
                colorscale=[[i / (len(PURPLE_RAMP) - 1), c_] for i, c_ in enumerate(PURPLE_RAMP)],
                showscale=False, xgap=2, ygap=2, hoverongaps=False,
                hovertemplate="%{y}<br>%{x}：%{text}<extra></extra>"))
            fig.update_xaxes(type="category", side="top")
            fig.update_yaxes(type="category", autorange="reversed")
            st.plotly_chart(style(fig, 80 + 44 * len(ylab)), width="stretch", config={"displayModeBar": False})
            if col != "share":
                CD = CH.dropna(subset=[f"d_{col}"])
                worst = CD.loc[CD.groupby(["season", "team_id"])[f"d_{col}"].idxmin()]
                cnt = worst["round"].value_counts().reindex(SR_ROUNDS).fillna(0).astype(int)
                top_r = cnt.idxmax()
                lines = [f"<b>{sr_m}最低的一輪：</b>{len(worst)} 位冠軍頭號得分手裡，有 {cnt[top_r]} 位在「{top_r}」最低"
                         f"（首輪 {cnt['首輪']}、次輪 {cnt['次輪']}、分區決賽 {cnt['分區決賽']}、總冠軍賽 {cnt['總冠軍賽']} 位）。"]
                b_ = CD.loc[CD[f"d_{col}"].idxmax()]
                lines.append(f"<b>單一輪表現最好：</b>{b_['season']} {b_['player_name']}，{b_['round']}"
                             f"（對 {ALL_ZH.get(b_['opp_abbr'], b_['opp_abbr'])}，{sr_fmt(b_[f'd_{col}'], is_pct, unit)}）。")
                insight(lines, where=slot2)
            with st.expander("看每一位冠軍每一輪的數字"):
                nice_table(pd.DataFrame({
                    "球季": CH["season"], "冠軍": [ALL_ZH.get(a, a) for a in CH["abbreviation"]], "_key": CH["abbreviation"],
                    "球員": CH["player_name"], "輪": CH["round"],
                    "對手": [ALL_ZH.get(a, a) for a in CH["opp_abbr"]],
                    "戰績": [f"{int(w)}-{int(g - w)}" for w, g in zip(CH["wins"], CH["games"])],
                    "上場": [f"{int(n)} 場" for n in CH["star_g"]],
                    "場均得分": [fmt(v, ".1f") for v in CH["ppg"]],
                    "上場分鐘": [fmt(v, ".1f") for v in CH["mpg"]],
                    "真實命中率": [fmt(v, ".1%") for v in CH["ts"]],
                    "命中率比例行賽": [sr_fmt(v, True, "").replace(" 百分點", "") for v in CH["d_ts"]],
                }), num_cols=("上場", "場均得分", "上場分鐘", "真實命中率", "命中率比例行賽"),
                    signed_cols=("命中率比例行賽",), dot_col="冠軍", colors=TEAM_COLORS)
                st.caption("命中率比例行賽＝這一輪的真實命中率 − 他自己整季例行賽的真實命中率（百分點）。")

RELATED[SR_PAGE] = [("例行賽與季後賽", "把季後賽合起來看，球星有沒有變好"), ("季後賽輪次", "同樣分四輪，看球隊打得辛不辛苦"),
                    ("籤運與傷兵", "每一輪遇到的對手強不強")]
SOURCES[SR_PAGE] = ("star_round_mv（預先算好的彙總表，docs/sql/2026-11-18_每一輪的球星.sql，由 player_game_stats、team_games、games 算）、champions",
                    "2006-07 起；30 隊；季後賽（附加賽不算）",
                    "頭號得分手＝這一季在這隊例行賽場均得分最高、至少上場 20 場；第幾輪＝依日期排好、對手換人就是下一輪；"
                    "對手＝同一場比賽的另一隊；每一輪只算他有上場的比賽；變化＝這一輪 − 他自己整季例行賽（得分佔比改和他自己的首輪比，"
                    "因為彙總表沒有例行賽全隊得分）；各組平均用他在那一輪上場的場數加權；對照組只留同一輪也贏下系列賽的球隊。")


RELATED["對手防守與球星"] = [("每一輪的球星", "四輪的命中率、得分、上場時間怎麼變"), ("防守端", "冠軍自己的防守強在哪裡"),
                         ("籤運與傷兵", "冠軍遇到的對手是不是比較弱")]
SOURCES["對手防守與球星"] = ("star_round_mv（2026-11-18 的 SQL 建立，一隊一季一輪一列）、league_team_seasons（對手例行賽防守效率）、champions",
                         "季後賽；2006-07 起；每一輪至少上場 2 場（第 1 節散點圖至少 3 場）",
                         "頭號得分手＝例行賽場均得分隊內最高、至少上場 20 場；命中率變化＝這一輪真實命中率 − 他自己這一季例行賽（百分點）；"
                         "對手防守＝對手那一季例行賽防守效率，排名 1＝最會守、「比聯盟好幾分」＝同季平均 − 對手；"
                         "平均都依出手次數（出手 ＋ 0.44 × 罰球）加權；扣掉對手防守＝和全部資料的最小平方法直線比。"
                         "限制：沒有扣掉包夾、傷病；對手防守用整季數字，不知道那一輪對手有沒有缺人。")


# ----- 系列賽主場優勢（2026-11-22）：相關頁面、資料來源與方法 -----
RELATED["系列賽主場優勢"] = [("季後賽輪次", "冠軍哪一輪打得最辛苦"), ("主場與客場", "例行賽的主場優勢有多大"), ("籤運與傷兵", "冠軍的季後賽對手強不強")]
SOURCES["系列賽主場優勢"] = ('team_games（輸贏、主客場）、games（日期、比賽類型）、champions',
                       '季後賽（附加賽不算）',
                       '系列賽＝同一季同一個對手的季後賽比賽；有主場優勢的一方＝第 1 戰在主場的那一隊；第幾輪＝這一隊這一季的第幾個系列賽；交叉驗證只看同一個系列賽裡主場與客場的單場勝率，2019-20 泡泡園區不列入。')

# ----- 季末輪休（2026-11-23）：相關頁面、資料來源與方法 -----
RELATED["季末輪休"] = [("月份趨勢", "季末勝率掉，是不是因為輪休"), ("頭號得分手缺陣", "少了頭號得分手還贏得了嗎"), ("賽程與休息", "背靠背和休息天數")]
SOURCES["季末輪休"] = ('rest_end_mv（預先算好的彙總表，docs/sql/2026-11-23_季末輪休.sql，由 player_game_stats、team_games、games 算）、champions',
                       '例行賽；只算已經打完的球季',
                       '前 3 號主力＝這一季替這隊上場總分鐘最多的 3 人（至少 20 場）；缺陣＝球隊有比賽、他沒有上場紀錄（或 0 分鐘），加入球隊以前、被交易走以後的比賽不算；最後 10 場＝依日期倒數 10 場；各組合計用加總再相除。')

def finish_page():
    if PAGE == HOME:
        return
    if PAGE_FINDINGS and SUMMARY_SLOT is not None:
        items = "".join(f"<li>{x}</li>" for x in list(dict.fromkeys(PAGE_FINDINGS))[:3])
        SUMMARY_SLOT.markdown(f'<div class="summary"><div class="summary-k">摘要</div><ol>{items}</ol></div>',
                              unsafe_allow_html=True)
    if PAGE in SOURCES and PAGE not in OWN_SOURCES:
        tables, scope, method = SOURCES[PAGE]
        with st.expander("資料來源與方法"):
            st.markdown(f'<div class="howread"><b>用到的資料表：</b>{tables}<br><b>範圍：</b>{scope}<br>'
                        f'<b>怎麼算：</b>{method}<br>資料由 NBA 官方數據（nba_api）抓取，存進 Supabase，網站每 15 分鐘重新讀取。</div>',
                        unsafe_allow_html=True)
    rel = [(p_, why) for p_, why in RELATED.get(PAGE, []) if p_ in PAGE_INFO]
    if rel:
        st.markdown('<div class="foot-k">相關頁面</div>', unsafe_allow_html=True)
        rcols = st.columns(3)
        for col_, (p_, why) in zip(rcols, rel):
            with col_:
                st.button(f"{p_}　→", key=f"rel_{p_}", width="stretch", on_click=goto, args=(p_,))
                st.markdown(f'<div class="foot-why">{why}</div>', unsafe_allow_html=True)
    order = [p[1] for p in PAGES]
    i = order.index(PAGE)
    c1, _, c2 = st.columns([2, 3, 2])
    if i > 0:
        c1.button(f"←　上一頁：{order[i - 1]}", key="prev_page", width="stretch", on_click=goto, args=(order[i - 1],))
    if i < len(order) - 1:
        c2.button(f"下一頁：{order[i + 1]}　→", key="next_page", width="stretch", on_click=goto, args=(order[i + 1],))




# ---------- 二號與三號得分手：季後賽越往後，誰站出來？（2026-11-20）----------
SUP_SQL = "docs/sql/2026-11-20_二號與三號得分手.sql"
SUP_ROUND = ["首輪", "次輪", "分區決賽", "總冠軍賽"]
SUP_VIEW = {   # 顯示名稱 → (欄位, 單位, 是不是比例)
    "得分佔全隊比例": ("share", "百分點", True),
    "真實命中率": ("ts", "百分點", True),
    "場均得分": ("ppg", "分", False),
    "場均上場分鐘": ("mpg", "分鐘", False),
}
SUP_LINES = [   # （組名, 冠軍嗎, 第幾號, 顏色, 線型）
    ("冠軍・頭號得分手", True, "頭號", "#b9a6f0", "solid"),
    ("冠軍・第 2、3 號", True, "第 2、3 號", ACCENT, "solid"),
    ("其他晉級球隊・頭號得分手", False, "頭號", "#c9c4d4", "dash"),
    ("其他晉級球隊・第 2、3 號", False, "第 2、3 號", "#5f5873", "dash"),
]
SUP_NEED = {"season", "team_id", "abbreviation", "rnd", "games", "wins", "team_pts", "scorer_rk", "player_name",
            "g", "min", "pts", "fga", "fta", "reg_g", "reg_min", "reg_pts", "reg_fga", "reg_fta", "team_reg_pts"}


@st.cache_data(ttl=3600, show_spinner="讀取每一輪的前三號得分手中…")
def _read_sup():
    """讀 support_round_mv（一隊一季一輪一位得分手一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("support_round_mv", ["season", "team_id", "rnd", "scorer_rk"])


def load_sup():
    """讀不到、是空的、或欄位不對（例如還沒執行今天的 SQL）時回傳 None，頁面改顯示提示"""
    try:
        df = _read_sup()
    except Exception:
        return None
    if df.empty or not SUP_NEED.issubset(df.columns):
        return None
    return df


def sup_wmean(v, w):
    """加權平均；全部是空值時回傳 NaN（不會除以 0）"""
    ok = v.notna() & w.notna() & (w > 0)
    return (v[ok] * w[ok]).sum() / w[ok].sum() if ok.any() else float("nan")


def sup_prep(df, champs_):
    """算出每一列「這一輪」和「自己例行賽」的四項數字，以及兩者的差"""
    d = df.copy()
    for c in SUP_NEED - {"season", "abbreviation", "player_name"}:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["rnd"].between(1, 4) & d["scorer_rk"].between(1, 3)].copy()
    pos = lambda s: s.where(s > 0)
    d["tsa"] = 2 * (d["fga"] + 0.44 * d["fta"])
    d["ppg"], d["ppg_reg"] = d["pts"] / pos(d["g"]), d["reg_pts"] / pos(d["reg_g"])
    d["mpg"], d["mpg_reg"] = d["min"] / pos(d["g"]), d["reg_min"] / pos(d["reg_g"])
    d["ts"] = d["pts"] / pos(d["tsa"])
    d["ts_reg"] = d["reg_pts"] / pos(2 * (d["reg_fga"] + 0.44 * d["reg_fta"]))
    d["share"], d["share_reg"] = d["pts"] / pos(d["team_pts"]), d["reg_pts"] / pos(d["team_reg_pts"])
    for c in ["ppg", "mpg", "ts", "share"]:
        d[f"d_{c}"] = d[c] - d[f"{c}_reg"]
    # 以「球隊場數」算的每場得分：他缺陣的比賽算 0 分，第 3 節用來看「少掉的分數誰補上」
    d["d_pts_tg"] = d["pts"] / pos(d["games"]) - d["ppg_reg"]
    champ_ids = set(zip(champs_["season"], pd.to_numeric(champs_["team_id"], errors="coerce")))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    d["won"] = d["wins"] >= 4
    d["role"] = d["scorer_rk"].map(lambda r: "頭號" if r == 1 else "第 2、3 號")
    d["round"] = d["rnd"].map(lambda r: SUP_ROUND[int(r) - 1])
    return d


def sup_weight(col):
    """每一項用不同的權重：命中率看出手數、得分佔比看球隊場數、其他看他上場幾場"""
    return {"ts": "tsa", "share": "games"}.get(col, "g")


def sup_lines(d, col):
    """四條線 × 四輪的加權平均（只留冠軍和贏下這一輪的球隊，對照組才公平）"""
    rows = []
    x = d[d["champion"] | d["won"]]
    for name, is_champ, role, _, _ in SUP_LINES:
        g_ = x[(x["champion"] == is_champ) & (x["role"] == role)]
        for r in range(1, 5):
            gg = g_[g_["rnd"] == r]
            rows.append({"line": name, "rnd": r, "mean": sup_wmean(gg[f"d_{col}"], gg[sup_weight(col)]),
                         "n": gg[["season", "team_id"]].drop_duplicates().shape[0]})
    return pd.DataFrame(rows)


def sup_sg(v):
    """帶正負號、一位小數；−0.03 這種不要印成「-0.0」"""
    return "-" if pd.isna(v) else f"{(0.0 if abs(v) < 0.05 else v):+.1f}"


def sup_val(L, line, r):
    x = L[(L["line"] == line) & (L["rnd"] == r)]["mean"]
    return x.iloc[0] if len(x) else float("nan")


if PAGE == "二號與三號得分手":
    hypothesis("季後賽越往後，對手越會包夾頭號得分手；那第 2、第 3 號得分手會站出來嗎？",
               "前段：冠軍的第 2、3 號得分手，越往後得分佔全隊比例越高（總冠軍賽比首輪平均每人多 1 個百分點以上）；"
               "中段：前三輪裡，冠軍第 2、3 號的真實命中率比其他晉級球隊的第 2、3 號好（至少多 1 個百分點）；"
               "後段（交叉驗證）：頭號得分手這一輪少得越多，第 2、3 號就多得越多（r ≤ −0.3）。")
    st.markdown('<div class="howread" style="margin-top:-4px">接著「每一輪的球星」（只看頭號得分手）往下問：他被守住的時候，誰補上？'
                '第 1～3 號得分手＝這一季這隊例行賽場均得分前 3 名（至少上場 20 場），季後賽也看同一批人；'
                '每一輪都和他自己這一季的例行賽比。</div>', unsafe_allow_html=True)
    SUP = load_sup()
    if SUP is None:
        st.info(f"尚未載入資料：請先在 Supabase 的 SQL Editor 執行 {SUP_SQL}（建立 support_round_mv），"
                "再按左側「重新讀取最新資料」。")
    else:
        D = sup_prep(SUP, champs)
        D = D[D["season"].isin(set(champs["season"]))]
        if D.empty or not D["champion"].any():
            st.info("資料不足：support_round_mv 裡還沒有冠軍的季後賽資料。")
        else:
            view = seg("看哪一項", list(SUP_VIEW), "sup_view")
            col, unit, is_pct = SUP_VIEW[view]
            k = 100 if is_pct else 1

            # ===== 1. 每一輪比自己例行賽變多少 =====
            slot1 = section(f"1　越往後，誰站出來？（{view}，比自己例行賽變多少）",
                            "紫色實線＝冠軍、灰色虛線＝同一輪也晉級的其他球隊；淺色＝頭號得分手、深色＝第 2、3 號；"
                            "0 以上＝這一輪比他自己例行賽高。總冠軍賽的贏家一定是冠軍，所以那一輪沒有對照組", anchor="sup1")
            L = sup_lines(D, col)
            fig = go.Figure()
            for name, _, _, c_, dash in SUP_LINES:
                g_ = L[L["line"] == name].sort_values("rnd")
                fig.add_trace(go.Scatter(x=[SUP_ROUND[int(r) - 1] for r in g_["rnd"]], y=g_["mean"] * k, name=name,
                                         mode="lines+markers", connectgaps=False,
                                         line=dict(color=c_, width=3 if "冠軍" in name else 2, dash=dash),
                                         marker=dict(size=9 if "冠軍" in name else 7, color=c_, line=dict(width=1, color=SURFACE)),
                                         customdata=g_[["n"]].values,
                                         hovertemplate=name + "<br>%{x}：%{y:+.1f} " + unit + "（%{customdata[0]:.0f} 隊）<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1))
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=SUP_ROUND)
            fig.update_yaxes(title=f"比自己例行賽變多少（{unit}）", tickformat="+.1f")
            fig.update_layout(legend=dict(orientation="h", y=1.1, x=0))
            st.plotly_chart(style(fig, 400), width="stretch", config={"displayModeBar": False})

            c1, c4 = sup_val(L, "冠軍・第 2、3 號", 1), sup_val(L, "冠軍・第 2、3 號", 4)
            s1, s4 = sup_val(L, "冠軍・頭號得分手", 1), sup_val(L, "冠軍・頭號得分手", 4)
            lines = [f"冠軍的第 2、3 號得分手，{view}在首輪比例行賽 {sup_sg(c1 * k)}、總冠軍賽 {sup_sg(c4 * k)} {unit}；"
                     f"頭號得分手是 {sup_sg(s1 * k)} → {sup_sg(s4 * k)} {unit}。"]
            # 對照假設：固定用「得分佔比」和「真實命中率」判斷，不受上面切換影響
            Ls, Lt = sup_lines(D, "share"), sup_lines(D, "ts")
            up = (sup_val(Ls, "冠軍・第 2、3 號", 4) - sup_val(Ls, "冠軍・第 2、3 號", 1)) * 100
            front = ("前段算不出來（總冠軍賽或首輪沒有資料）" if pd.isna(up) else
                     ("前段成立" if up >= 1 else "前段不成立") + f"：第 2、3 號的得分佔比，總冠軍賽比首輪平均每人 {up:+.1f} 個百分點（門檻 +1）")
            gaps = [(sup_val(Lt, "冠軍・第 2、3 號", r) - sup_val(Lt, "其他晉級球隊・第 2、3 號", r)) * 100 for r in (1, 2, 3)]
            gaps = [x for x in gaps if pd.notna(x)]
            if gaps:
                gm = sum(gaps) / len(gaps)
                mid = (("中段成立" if gm >= 1 else "中段不成立") + f"：前三輪冠軍第 2、3 號的命中率變化平均比其他晉級球隊 {gm:+.1f} 個百分點（門檻 +1）；"
                       f"{sum(1 for x in gaps if x > 0)} / {len(gaps)} 輪比較好")
            else:
                mid = "中段算不出來（前三輪沒有對照組資料）"
            lines.append("讀法：先看深紫色線是不是越往右越高（第 2、3 號越後面越重要），再看它在前三輪是不是高過深灰色虛線（比其他晉級球隊的第 2、3 號撐得住）；"
                         "切到「場均上場分鐘」可以看得分增加是不是只是打比較久。")
            insight(lines, where=slot1, check=front + "；" + mid + "。")
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                for k_, v_ in {
                    "第 1～3 號得分手（本頁）": ("這一季這隊例行賽場均得分前 3 名（至少上場 20 場）；季後賽也看同一批人，不會因為季後賽得分變多就換人",
                                         "依例行賽場均得分排名"),
                    "得分佔全隊比例": ("這一輪全隊的得分裡，他一個人得了幾成；缺陣的比賽算 0 分", "他這一輪的總得分 ÷ 全隊這一輪的總得分"),
                    "比自己例行賽變多少": ("每一輪都和他自己這一季的例行賽比，場均 30 分和 15 分的人才能放在一起看", "這一輪的數字 − 他這一季例行賽的數字"),
                    "其他晉級球隊": ("同一輪也贏下系列賽的球隊；被淘汰的球隊投不進本來就是輸的原因之一，和冠軍比不公平", "這一輪贏 4 場的球隊（不含冠軍）"),
                }.items():
                    TERMS.setdefault(k_, v_)
                term_table(["第 1～3 號得分手（本頁）", "得分佔全隊比例", "比自己例行賽變多少", "其他晉級球隊", "真實命中率", "相關係數 r"],
                           first_note="季後賽每一輪只有 4～7 場，單一球員起伏很大；所以每一條線都是很多隊的加權平均（命中率依出手數、得分佔比依場數、其他依上場場數）。")

            # ===== 2. 交叉驗證：頭號少得的分，第 2、3 號補上了嗎？ =====
            st.divider()
            slot2 = section("2　交叉驗證：頭號得分手少得的分，第 2、3 號補上了嗎？",
                            "每個點是一隊打的一輪（所有季後賽球隊），橫軸＝頭號得分手這一輪每場比例行賽多（右）或少（左）幾分、"
                            "縱軸＝第 2、3 號合計每場多幾分；★ 是冠軍。每場都用「球隊場數」算，缺陣的比賽算 0 分，所以頭號受傷缺陣也看得到", anchor="sup2")
            P = D.pivot_table(index=["season", "team_id", "abbreviation", "rnd", "champion", "games"],
                              columns="role", values="d_pts_tg", aggfunc="sum").reset_index()
            nm = D[D["scorer_rk"] == 1].set_index(["season", "team_id", "rnd"])["player_name"]
            if {"頭號", "第 2、3 號"}.issubset(P.columns):
                P = P.dropna(subset=["頭號", "第 2、3 號"])
                P = P[P["games"] >= 4]
            else:
                P = P.iloc[0:0]
            if len(P) < 5:
                insight(["資料不足：可以畫的系列賽不到 5 個。"], where=slot2)
            else:
                P["star"] = [nm.get((s_, t_, r_), "") for s_, t_, r_ in zip(P["season"], P["team_id"], P["rnd"])]
                P["lab"] = [f"{s_} {ALL_ZH.get(a_, a_)}　{SUP_ROUND[int(r_) - 1]}" for s_, a_, r_ in zip(P["season"], P["abbreviation"], P["rnd"])]
                xm, ym = P["頭號"].mean(), P["第 2、3 號"].mean()
                den = ((P["頭號"] - xm) ** 2).sum()
                b = ((P["頭號"] - xm) * (P["第 2、3 號"] - ym)).sum() / den if den > 0 else float("nan")
                a = ym - b * xm
                r_all = P["頭號"].corr(P["第 2、3 號"])
                fig = go.Figure()
                for is_c, nm_, c_, sym, sz in [(False, "其他球隊", "#c9c4d4", "circle", 7), (True, "冠軍", ACCENT, "star", 14)]:
                    q = P[P["champion"] == is_c]
                    fig.add_trace(go.Scatter(x=q["頭號"], y=q["第 2、3 號"], mode="markers", name=nm_,
                                             marker=dict(size=sz, symbol=sym, color=c_, line=dict(width=1, color=SURFACE)),
                                             customdata=q[["lab", "star"]].values,
                                             hovertemplate="%{customdata[0]}<br>頭號 %{customdata[1]}：每場 %{x:+.1f} 分"
                                                           "<br>第 2、3 號合計：每場 %{y:+.1f} 分<extra></extra>"))
                if pd.notna(b):
                    xs = [P["頭號"].min(), P["頭號"].max()]
                    fig.add_trace(go.Scatter(x=xs, y=[a + b * v for v in xs], mode="lines", name="趨勢線",
                                             line=dict(color=INK_2, width=1.5, dash="dot"), hoverinfo="skip"))
                fig.add_hline(y=0, line=dict(color=MUTED, width=1))
                fig.add_vline(x=0, line=dict(color=MUTED, width=1))
                fig.update_xaxes(title="頭號得分手：每場比例行賽多幾分", tickformat="+.0f", showgrid=True, gridcolor=GRID)
                fig.update_yaxes(title="第 2、3 號合計：每場多幾分", tickformat="+.0f")
                fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
                st.plotly_chart(style(fig, 440), width="stretch", config={"displayModeBar": False})
                Cn = P[P["champion"]]
                left = P[P["頭號"] < -3]
                more = "多" if pd.isna(b) or b <= 0 else "也少"
                lines = [f"{len(P)} 個「一隊一輪」裡，頭號得分手每場少 1 分，第 2、3 號合計平均{more} {abs(b):.2f} 分"
                         f"（r ＝ {r_all:+.2f}，{corr_word(r_all)}）。"]
                if len(left):
                    lines.append(f"頭號得分手每場少 3 分以上的 {len(left)} 輪裡，第 2、3 號合計平均每場 {left['第 2、3 號'].mean():+.1f} 分"
                                 f"（冠軍 {len(Cn[Cn['頭號'] < -3])} 輪）。")
                lines.append("讀法：點如果由左上往右下排，代表「頭號少、配角多」——有人補位；點如果貼著水平線，代表少掉的分沒人補。"
                             "斜率不到 −1 是正常的：頭號少得的分，也可能由第 4 號以後的球員或板凳補上。")
                back = (("後段成立" if r_all <= -0.3 else "後段不成立") + f"：r ＝ {r_all:+.2f}（門檻 −0.3）") if pd.notna(r_all) else "後段算不出來"
                insight(lines, where=slot2, check=back + "。")

            # ===== 3. 每一位冠軍：每一輪是誰得最多分 =====
            st.divider()
            slot3 = section("3　每一位冠軍：每一輪是誰得最多分？",
                            "一列一位冠軍、一欄一輪；格子寫這一輪前三號裡得分最多的人和他的每場得分。"
                            "淺紫＝頭號得分手自己、中紫＝第 2 號、深紫＝第 3 號", anchor="sup3")
            C = D[D["champion"]].copy()
            C["ppg_tg"] = C["pts"] / C["games"].where(C["games"] > 0)
            lead = (C.sort_values(["season", "rnd", "pts", "scorer_rk"], ascending=[True, True, False, True])
                    .drop_duplicates(["season", "rnd"]))
            seasons_c = sorted(lead["season"].unique())
            ab_by = lead.drop_duplicates("season").set_index("season")["abbreviation"]
            rows_lab = [f"{s_} {ALL_ZH.get(ab_by[s_], ab_by[s_])}" for s_ in seasons_c]
            Z = lead.pivot(index="season", columns="rnd", values="scorer_rk").reindex(index=seasons_c, columns=[1, 2, 3, 4])
            T = lead.assign(t=[f"{str(n).split(' ')[-1]}<br>{v:.1f}" for n, v in zip(lead["player_name"], lead["ppg_tg"])]) \
                .pivot(index="season", columns="rnd", values="t").reindex(index=seasons_c, columns=[1, 2, 3, 4]).fillna("")
            fig = go.Figure(go.Heatmap(
                z=Z.values, x=SUP_ROUND, y=rows_lab, zmin=1, zmax=3, showscale=False,
                colorscale=[[0, "#e1d6fa"], [0.5, "#8a63d9"], [1, "#4c2a96"]],
                text=T.values, texttemplate="%{text}", textfont=dict(size=11),
                xgap=2, ygap=2, hovertemplate="%{y}　%{x}<br>得分最多：%{text}<extra></extra>"))
            fig.update_xaxes(type="category", side="top")
            fig.update_yaxes(type="category", autorange="reversed")
            st.plotly_chart(style(fig, 80 + 34 * len(rows_lab)), width="stretch", config={"displayModeBar": False})
            n_all, n_sup = len(lead), int((lead["scorer_rk"] > 1).sum())
            by_r = lead[lead["scorer_rk"] > 1].groupby("rnd").size()
            lines = [f"{len(seasons_c)} 位冠軍、{n_all} 輪裡，有 <b>{n_sup}</b> 輪（{n_sup / max(n_all, 1):.0%}）得最多分的不是頭號得分手。"]
            if len(by_r):
                rr = int(by_r.idxmax())
                lines.append(f"最常由第 2、3 號帶頭的是「{SUP_ROUND[rr - 1]}」（{int(by_r.max())} 次）；"
                             f"有 {lead[lead['scorer_rk'] > 1]['season'].nunique()} 位冠軍至少一輪由第 2 或第 3 號得最多分。")
            insight(lines, where=slot3)
            with st.expander("看每一位冠軍每一輪的數字"):
                C = C.sort_values(["season", "rnd", "scorer_rk"])
                nice_table(pd.DataFrame({
                    "球季": C["season"], "冠軍": [ALL_ZH.get(a_, a_) for a_ in C["abbreviation"]], "_key": C["abbreviation"],
                    "輪": C["round"], "對手": [ALL_ZH.get(o_, o_) if isinstance(o_, str) else "-" for o_ in C.get("opp_abbr", pd.Series("-", index=C.index))],
                    "戰績": [f"{int(w_)}-{int(n_ - w_)}" for w_, n_ in zip(C["wins"], C["games"])],
                    "第幾號": [f"第 {int(r_)}" for r_ in C["scorer_rk"]], "球員": C["player_name"],
                    "上場": [f"{int(g_)} 場" for g_ in C["g"]],
                    "場均得分": [f"{fmt(a_, '.1f')}（例 {fmt(b_, '.1f')}）" for a_, b_ in zip(C["ppg"], C["ppg_reg"])],
                    "得分佔比": [f"{fmt(a_, '.0%')}（例 {fmt(b_, '.0%')}）" for a_, b_ in zip(C["share"], C["share_reg"])],
                    "命中率差": [fmt_d(v_, ".1%").replace(" 百分點", "") for v_ in C["d_ts"]],
                }), num_cols=("場均得分", "得分佔比", "命中率差"), signed_cols=("命中率差",), dot_col="冠軍", colors=TEAM_COLORS)


RELATED["二號與三號得分手"] = [("每一輪的球星", "只看頭號得分手，四輪怎麼變"), ("對手防守與球星", "頭號得分手掉，是不是因為對手會守"),
                        ("誰補上得分", "例行賽頭號得分手缺陣時，誰補上")]
SOURCES["二號與三號得分手"] = (
    "support_round_mv（預先算好的彙總表，docs/sql/2026-11-20_二號與三號得分手.sql，由 player_game_stats、team_games、games 算）、champions",
    "2006-07 起；季後賽四輪；全聯盟 30 隊",
    "第 1～3 號得分手＝這一季這隊例行賽場均得分前 3 名（至少上場 20 場）；第幾輪＝同一季季後賽依日期排好、對手換人就 +1；"
    "每一輪都和他自己這一季例行賽比；第 1 節只留冠軍和贏下這一輪的球隊，命中率依出手數、得分佔比依場數、其他依上場場數加權；"
    "第 2 節每場得分用球隊場數算（缺陣算 0 分），趨勢線是最小平方法直線。限制：一輪只有 4～7 場；看不出對手是不是真的包夾頭號得分手。")


RELATED["奪冠列車"] = [("冠軍密碼", "冠軍的標準從哪裡來：淨效率最關鍵"), ("防守端", "冠軍的防守強在哪裡"), ("焦點人物", "本季值得看的球員")]
SOURCES["奪冠列車"] = (
    "recap_team_games（本季每場 × 每隊，每天 15:30 更新）、league_team_seasons＋champions（歷屆冠軍的標準）",
    "本季例行賽；歷屆冠軍＝資料庫裡所有冠軍的例行賽",
    "回合數＝投籃出手 − 進攻籃板 ＋ 失誤 ＋ 0.44 × 罰球出手；進攻效率＝得分 ÷ 回合 × 100；防守效率＝對手得分 ÷ 對手回合 × 100；"
    "籃板＝進攻籃板率與防守籃板率的平均；助攻比例＝助攻 ÷ 投籃命中；失誤率＝失誤 ÷ 回合。六項各換成百分等級（0～100，"
    "贏過聯盟幾 % 的球隊），冠軍指數＝100 − 六項「落後歷屆冠軍平均的分數」的平均（不落後就是 0）；最像的冠軍＝六項百分等級的距離最近。")
RELATED["焦點人物"] = [("頭號得分手缺陣", "歷屆冠軍少了頭號得分手時勝率掉多少"), ("得分穩定度", "冠軍球星比較不會爆冷嗎"),
                    ("奪冠列車", "這些球員的球隊離冠軍多遠")]
SOURCES["焦點人物"] = (
    "recap_player_games（本季每場 × 每位球員）、recap_team_games（球隊勝負、全隊出手）、pbp_events（關鍵時刻得分）",
    "本季例行賽；夠格球員＝出賽至少本季場數的 4 成、場均 15 分鐘以上",
    "爆發中＝最近 5 場平均得分 − 本季平均；不可或缺＝他上場時球隊勝率 − 他缺陣時（從他本季第一次上場後算，場均 25 分鐘以上、"
    "至少缺陣 3 場）；關鍵時刻＝第四節或延長賽最後 5 分鐘、得分前分差 5 分以內；雷達圖六項是場均數據在夠格球員裡的百分等級（失誤越少越好）；"
    "使用率＝（投籃出手 ＋ 0.44 × 罰球出手 ＋ 失誤）×（全隊分鐘 ÷ 5）÷［上場分鐘 ×（全隊出手 ＋ 0.44 × 全隊罰球 ＋ 全隊失誤）］。")

finish_page()
st.markdown('<div class="footnote">DATA · NBA STATS API　｜　STORAGE · SUPABASE　｜　BUILT WITH STREAMLIT</div>',
            unsafe_allow_html=True)
