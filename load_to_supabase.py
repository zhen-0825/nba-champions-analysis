"""
把 NBA 球隊的球員逐場數據寫進 Supabase 資料庫

預設：2022～2026 五支冠軍隊（勇士、金塊、塞爾提克、雷霆、尼克）
      日期範圍 2012-10-01 ~ 2026-06-30
      （涵蓋 2022 勇士奪冠前 10 年，一直到最近一季）

用法（在 VS Code 終端機輸入）
  python load_to_supabase.py --dry-run          先試跑：只抓資料、算筆數，不寫進資料庫
  python load_to_supabase.py                    正式寫入（預設五隊、預設日期）
  python load_to_supabase.py --teams GSW --start 2025-10-01 --end 2026-06-30
                                                只更新勇士最新一季

需要先做好
  1. pip install supabase python-dotenv
  2. 在專案資料夾建立 .env 檔，寫入 SUPABASE_URL 和 SUPABASE_SECRET_KEY
  3. 在 Supabase 的 SQL Editor 執行過 schema.sql
"""

import argparse
import os

import pandas as pd

from fetch_nba import SEASON_TYPES, fetch_games

# ===== 設定區 =====
CHAMPION_TEAMS = ["GSW", "DEN", "BOS", "OKC", "NYK"]   # 2022～2026 冠軍
DEFAULT_START = "2012-10-01"
DEFAULT_END = "2026-06-30"
BATCH = 500   # 每次寫入幾筆（太多會被資料庫拒絕）

# 範圍內每一季的冠軍（用來在網頁上標示奪冠球季）
CHAMPIONS = {
    "2012-13": "MIA", "2013-14": "SAS", "2014-15": "GSW", "2015-16": "CLE",
    "2016-17": "GSW", "2017-18": "GSW", "2018-19": "TOR", "2019-20": "LAL",
    "2020-21": "MIL", "2021-22": "GSW", "2022-23": "DEN", "2023-24": "BOS",
    "2024-25": "OKC", "2025-26": "NYK",
}

INT_COLS = ["PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB",
            "REB", "AST", "STL", "BLK", "TOV", "PF", "PLUS_MINUS"]
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
    parser = argparse.ArgumentParser(description="把 NBA 球隊數據寫進 Supabase")
    parser.add_argument("--teams", nargs="+", default=CHAMPION_TEAMS, help="球隊縮寫，可多個，例如 GSW BOS")
    parser.add_argument("--start", default=DEFAULT_START, help="開始日期，格式 2012-10-01")
    parser.add_argument("--end", default=DEFAULT_END, help="結束日期，格式 2026-06-30")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料、算筆數，不寫進資料庫")
    args = parser.parse_args()

    client = None if args.dry_run else connect()
    if args.dry_run:
        print("【試跑模式】不會寫進資料庫\n")

    load_reference(client)

    for abbr in args.teams:
        print(f"\n===== {abbr.upper()} =====")
        data = fetch_games(abbr, args.start, args.end, SEASON_TYPES)
        if data.empty:
            continue
        players, games, team_games, stats = build_tables(data)
        print("  寫入資料庫")
        # 順序很重要：先寫球員和比賽，後面的表才能對應得到
        upsert(client, "players", players, "player_id")
        upsert(client, "games", games, "game_id")
        upsert(client, "team_games", team_games, "game_id,team_id")
        upsert(client, "player_game_stats", stats, "game_id,player_id")

    print("\n全部完成！")


if __name__ == "__main__":
    main()
