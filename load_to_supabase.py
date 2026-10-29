"""
把 NBA 數據寫進 Supabase 資料庫（兩種資料）

1. 球員逐場數據：2019～2026 八支冠軍隊（暴龍、湖人、公鹿、勇士、金塊、塞爾提克、雷霆、尼克）
2. 全聯盟球隊每季數據：30 隊的基本、進階（攻守效率）、對手數據

預設日期範圍：2006-10-01 ~ 今天（近 20 季，含進行中的球季）

用法（在 VS Code 終端機輸入）
  python load_to_supabase.py --dry-run          先試跑：只抓資料、算筆數，不寫進資料庫
  python load_to_supabase.py                    正式寫入（球員逐場 + 全聯盟球隊）
  python load_to_supabase.py --only league      只更新全聯盟球隊數據
  python load_to_supabase.py --only players     只更新八隊球員逐場數據
  python load_to_supabase.py --start 2026-10-01 只更新當季（每日自動更新用這個）
  python load_to_supabase.py --teams GSW --start 2025-10-01 --end 2026-06-30
  python load_to_supabase.py --next 2           再加入 2 支「還沒載入」的球隊（2006 年起完整球員逐場）
  python load_to_supabase.py --progress         看看 30 隊已經載入幾隊、下一批是誰

關於 --next：
  八支冠軍隊以外的 22 隊，每次挑「下一批」載入，成功後記在 data/added_teams.txt。
  之後每天的更新（--start 本季）會自動包含這些已加入的球隊，讓它們的資料也保持最新。
  順序：先載入 2007～2018 的其他冠軍（SAS、MIA、DAL、CLE），再依英文縮寫排列。

需要先做好
  1. pip install supabase python-dotenv
  2. .env 檔裡有 SUPABASE_URL 和 SUPABASE_SECRET_KEY
  3. 在 Supabase 的 SQL Editor 執行過 schema.sql 和 schema_league.sql
"""

import argparse
import os
import time
from datetime import date, datetime

import pandas as pd

from fetch_nba import (MAX_RETRIES, REQUEST_DELAY, SEASON_TYPES, TIMEOUT,
                       fetch_games, season_is_finished, seasons_between)

# ===== 設定區 =====
CHAMPION_TEAMS = ["TOR", "LAL", "MIL", "GSW", "DEN", "BOS", "OKC", "NYK"]   # 2019～2026 冠軍
DEFAULT_START = "2006-10-01"     # 近 20 季
DEFAULT_END = None               # None = 今天
LEAGUE_TYPES = ["Regular Season", "Playoffs"]
BATCH = 500   # 每次寫入幾筆（太多會被資料庫拒絕）

# 每一季的冠軍（用來在網頁上標示奪冠球季）
CHAMPIONS = {
    "2006-07": "SAS", "2007-08": "BOS", "2008-09": "LAL", "2009-10": "LAL",
    "2010-11": "DAL", "2011-12": "MIA", "2012-13": "MIA", "2013-14": "SAS",
    "2014-15": "GSW", "2015-16": "CLE", "2016-17": "GSW", "2017-18": "GSW",
    "2018-19": "TOR", "2019-20": "LAL", "2020-21": "MIL", "2021-22": "GSW",
    "2022-23": "DEN", "2023-24": "BOS", "2024-25": "OKC", "2025-26": "NYK",
}

INT_COLS = ["PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB",
            "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS"]

# 全聯盟球隊數據要留下的欄位：NBA 欄位名稱 → 資料庫欄位名稱
LEAGUE_BASE = {"GP": "gp", "W": "w", "L": "l", "PTS": "pts", "FGM": "fgm", "FGA": "fga",
               "FG3M": "fg3m", "FG3A": "fg3a", "FTM": "ftm", "FTA": "fta", "OREB": "oreb",
               "DREB": "dreb", "REB": "reb", "AST": "ast", "TOV": "tov", "STL": "stl",
               "BLK": "blk", "PLUS_MINUS": "plus_minus"}
LEAGUE_ADV = {"OFF_RATING": "off_rating", "DEF_RATING": "def_rating", "NET_RATING": "net_rating",
              "PACE": "pace", "TS_PCT": "ts_pct", "EFG_PCT": "efg_pct", "AST_TO": "ast_to",
              "TM_TOV_PCT": "tm_tov_pct", "OREB_PCT": "oreb_pct", "DREB_PCT": "dreb_pct"}
LEAGUE_OPP = {"OPP_PTS": "opp_pts", "OPP_FGM": "opp_fgm", "OPP_FGA": "opp_fga",
              "OPP_FG3M": "opp_fg3m", "OPP_FG3A": "opp_fg3a", "OPP_TOV": "opp_tov"}
LEAGUE_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "league")
ADDED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "added_teams.txt")
# ==================


def connect():
    """用 .env 裡的網址和金鑰連上 Supabase"""
    from dotenv import load_dotenv
    from supabase import create_client

    load_dotenv()
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise SystemExit("找不到 SUPABASE_URL 或 SUPABASE_SECRET_KEY，請檢查 .env 檔")
    return create_client(url, key)


def clean(value):
    """把 pandas 的空值、數字型態換成資料庫看得懂的樣子"""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value


def to_rows(df):
    return [{k: clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def upsert(client, table, df, conflict):
    """寫入資料；已經存在的（主鍵相同）就更新，不會重複"""
    rows = to_rows(df)
    if client is not None:
        for i in range(0, len(rows), BATCH):
            client.table(table).upsert(rows[i:i + BATCH], on_conflict=conflict).execute()
    print(f"    {table}：{len(rows)} 筆")


# ---------------------------------------------------------------------
# 1. 球員逐場數據
# ---------------------------------------------------------------------
def build_tables(data):
    """把 NBA 抓回來的一大張表，拆成資料庫的幾張表"""
    data = data.copy()
    for c in INT_COLS:
        data[c] = pd.to_numeric(data[c], errors="coerce").round().astype("Int64")
    data["MIN"] = pd.to_numeric(data["MIN"], errors="coerce").round(2)
    data["GAME_DATE"] = pd.to_datetime(data["GAME_DATE"]).dt.strftime("%Y-%m-%d")

    players = (data[["PLAYER_ID", "PLAYER_NAME"]]
               .drop_duplicates("PLAYER_ID")
               .rename(columns=str.lower))

    games = (data[["GAME_ID", "GAME_DATE", "SEASON", "SEASON_TYPE"]]
             .drop_duplicates("GAME_ID")
             .rename(columns=str.lower))

    team_games = data[["GAME_ID", "TEAM_ID", "MATCHUP", "WL"]].drop_duplicates(["GAME_ID", "TEAM_ID"])
    team_games["IS_HOME"] = team_games["MATCHUP"].str.contains("vs.", regex=False)
    team_games = team_games.rename(columns=str.lower)

    stats = (data[["GAME_ID", "PLAYER_ID", "TEAM_ID", "MIN"] + INT_COLS]
             .drop_duplicates(["GAME_ID", "PLAYER_ID"])
             .rename(columns=str.lower))

    return players, games, team_games, stats


def load_players(client, team_list, start, end):
    """回傳 {球隊: 抓到幾季的例行賽}，用來判斷這隊是不是完整載入"""
    got = {}
    for abbr in team_list:
        print(f"\n===== {abbr.upper()} 球員逐場 =====")
        data = fetch_games(abbr, start, end, SEASON_TYPES)
        if data.empty:
            got[abbr] = 0
            continue
        got[abbr] = data.loc[data["SEASON_TYPE"] == "Regular Season", "SEASON"].nunique()
        players, games, team_games, stats = build_tables(data)
        print("  寫入資料庫")
        # 順序很重要：先寫球員和比賽，後面的表才能對應得到
        upsert(client, "players", players, "player_id")
        upsert(client, "games", games, "game_id")
        upsert(client, "team_games", team_games, "game_id,team_id")
        upsert(client, "player_game_stats", stats, "game_id,player_id")
    return got


# ---------------------------------------------------------------------
# 1b. 慢慢加入其他 22 隊（每次 --next N 隊）
# ---------------------------------------------------------------------
def read_added():
    """已經完整載入的非冠軍球隊（存在 data/added_teams.txt，一行一隊）"""
    if not os.path.exists(ADDED_FILE):
        return []
    with open(ADDED_FILE, encoding="utf-8") as f:
        return [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]


def mark_added(abbr):
    os.makedirs(os.path.dirname(ADDED_FILE), exist_ok=True)
    with open(ADDED_FILE, "a", encoding="utf-8") as f:
        f.write(abbr + "\n")


def team_queue():
    """還沒載入的球隊，依順序排好：先其他年代的冠軍，再依英文縮寫"""
    from nba_api.stats.static import teams
    all_abbr = sorted(t["abbreviation"] for t in teams.get_teams())
    done = set(CHAMPION_TEAMS) | set(read_added())
    old_champs = [a for a in dict.fromkeys(CHAMPIONS.values()) if a in all_abbr]
    order = old_champs + [a for a in all_abbr if a not in old_champs]
    return [a for a in order if a not in done]


def load_next(client, n):
    queue = team_queue()
    if not queue:
        print("\n30 隊都已經載入完成，不需要再加了！")
        return True
    batch = queue[:n]
    print(f"\n===== 今天加入：{'、'.join(batch)}（還剩 {len(queue) - len(batch)} 隊）=====")
    # 應該要有幾季：2006-07 到現在這一季；進行中的球季剛開打時可能還沒比賽，所以下面允許少 1 季
    expected = len(seasons_between(datetime.strptime(DEFAULT_START, "%Y-%m-%d").date(), date.today()))
    got = load_players(client, batch, DEFAULT_START, None)
    ok = True
    for abbr in batch:
        seasons_ok = got.get(abbr, 0)
        if client is not None and seasons_ok >= expected - 1:
            mark_added(abbr)
            print(f"  {abbr}：完成（{seasons_ok} 季例行賽），已記錄到 data/added_teams.txt")
        elif client is None:
            print(f"  {abbr}：試跑模式，不記錄")
        else:
            ok = False
            print(f"  {abbr}：只抓到 {seasons_ok} / {expected} 季，先不記錄，明天會再試一次"
                  "（抓過的球季有存檔，不會重抓）")
    return ok


def refresh_stats(client):
    """寫完球員逐場數據後，叫資料庫重新計算「預先算好的彙總表」，網站才看得到新資料"""
    if client is None:
        return
    try:
        client.rpc("refresh_season_stats").execute()
        print("  已更新彙總表（team_season_stats_mv、player_season_stats_mv）")
    except Exception as e:
        print(f"  彙總表沒有更新：{type(e).__name__}。如果還沒執行 docs/sql/2026-10-30_預先算好的彙總表.sql，"
              "請先到 Supabase SQL Editor 執行；網站會暫時改讀原本的檢視表。")


def show_progress():
    added = read_added()
    queue = team_queue()
    print(f"已載入：八支冠軍隊 + {len(added)} 隊（{'、'.join(added) or '還沒有'}）")
    print(f"還沒載入：{len(queue)} 隊（下一批：{'、'.join(queue[:2]) or '無'}）")


# ---------------------------------------------------------------------
# 2. 全聯盟球隊每季數據
# ---------------------------------------------------------------------
def download_league(season, season_type, measure):
    """向 NBA 要某一季、全部 30 隊的球隊數據；measure = Base / Advanced / Opponent"""
    from nba_api.stats.endpoints import leaguedashteamstats

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            return leaguedashteamstats.LeagueDashTeamStats(
                season=season,
                season_type_all_star=season_type,
                measure_type_detailed_defense=measure,
                per_mode_detailed="Totals",
                timeout=TIMEOUT,
            ).get_data_frames()[0]
        except Exception as e:
            print(f"    第 {attempt} 次失敗：{type(e).__name__}，{REQUEST_DELAY * attempt * 2} 秒後重試")
            time.sleep(REQUEST_DELAY * attempt * 2)
    return None


def load_league_season(season, season_type):
    """一季一種比賽類型：抓三種數據合併；打完的球季存檔，下次不重抓"""
    path = os.path.join(LEAGUE_CACHE, f"{season}_{season_type.replace(' ', '_')}.csv")
    if os.path.exists(path) and season_is_finished(season):
        print(f"  {season} {season_type}：讀取已存檔資料")
        return pd.read_csv(path)

    print(f"  {season} {season_type}：向 NBA 官網下載中…")
    parts = {}
    for measure, cols in [("Base", LEAGUE_BASE), ("Advanced", LEAGUE_ADV), ("Opponent", LEAGUE_OPP)]:
        df = download_league(season, season_type, measure)
        if df is None or df.empty:
            print(f"    {measure} 沒有資料，跳過這一季")
            return pd.DataFrame()
        keep = {k: v for k, v in cols.items() if k in df.columns}
        parts[measure] = df[["TEAM_ID"] + list(keep)].rename(columns=keep)

    merged = parts["Base"].merge(parts["Advanced"], on="TEAM_ID").merge(parts["Opponent"], on="TEAM_ID")
    merged.insert(0, "season", season)
    merged.insert(1, "season_type", season_type)
    merged = merged.rename(columns={"TEAM_ID": "team_id"})
    os.makedirs(LEAGUE_CACHE, exist_ok=True)
    merged.to_csv(path, index=False)
    print(f"    完成，{len(merged)} 隊")
    return merged


def load_league(client, start, end):
    start_d = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
    print("\n===== 全聯盟球隊每季數據 =====")
    frames = []
    for season in seasons_between(start_d, end_d):
        for st in LEAGUE_TYPES:
            df = load_league_season(season, st)
            if not df.empty:
                frames.append(df)
    if not frames:
        return
    league = pd.concat(frames, ignore_index=True)
    int_cols = [c for c in list(LEAGUE_BASE.values()) + list(LEAGUE_OPP.values()) if c in league.columns]
    for c in int_cols:
        league[c] = pd.to_numeric(league[c], errors="coerce").round().astype("Int64")
    print("  寫入資料庫")
    upsert(client, "league_team_seasons", league, "season,season_type,team_id")


# ---------------------------------------------------------------------
def load_reference(client):
    """寫入 30 支球隊和歷年冠軍"""
    from nba_api.stats.static import teams

    all_teams = pd.DataFrame(teams.get_teams())
    team_table = all_teams[["id", "abbreviation", "full_name", "city"]].rename(columns={"id": "team_id"})
    abbr_to_id = dict(zip(all_teams["abbreviation"], all_teams["id"]))
    champs = pd.DataFrame([{"season": s, "team_id": abbr_to_id[a]} for s, a in CHAMPIONS.items()])

    print("基本資料")
    upsert(client, "teams", team_table, "team_id")
    upsert(client, "champions", champs, "season")


def main():
    parser = argparse.ArgumentParser(description="把 NBA 數據寫進 Supabase")
    parser.add_argument("--teams", nargs="+", default=CHAMPION_TEAMS + read_added(),
                        help="球隊縮寫，可多個，例如 GSW BOS（預設：八支冠軍隊＋已用 --next 加入的球隊）")
    parser.add_argument("--start", default=DEFAULT_START, help="開始日期，格式 2006-10-01")
    parser.add_argument("--end", default=DEFAULT_END, help="結束日期，不填就是今天")
    parser.add_argument("--only", choices=["players", "league"], help="只更新其中一種資料")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料、算筆數，不寫進資料庫")
    parser.add_argument("--next", type=int, metavar="N", help="再加入 N 支還沒載入的球隊（完整 20 季球員逐場）")
    parser.add_argument("--progress", action="store_true", help="顯示 30 隊的載入進度")
    args = parser.parse_args()

    if args.progress:
        show_progress()
        return

    client = None if args.dry_run else connect()
    if args.dry_run:
        print("【試跑模式】不會寫進資料庫\n")

    load_reference(client)
    if args.next:
        ok = load_next(client, args.next)
        refresh_stats(client)
        print(f"\n全部完成！（{datetime.now():%Y-%m-%d %H:%M}）")
        raise SystemExit(0 if ok else 1)
    if args.only != "league":
        load_players(client, args.teams, args.start, args.end)
        refresh_stats(client)
    if args.only != "players":
        load_league(client, args.start, args.end)

    print(f"\n全部完成！（{datetime.now():%Y-%m-%d %H:%M}）")


if __name__ == "__main__":
    main()
