"""
每日戰報資料：抓「這一季」全聯盟 30 隊每一場比賽的球隊比分與球員數據，寫進 Supabase

  recap_team_games    每場比賽 × 每支球隊一筆（比分、勝負、命中、失誤…）
  recap_player_games  每場比賽 × 每位球員一筆（得分、籃板、助攻、三分…）

只要呼叫 NBA 幾次（每種比賽類型：球隊一次、球員一次），每天跑也很快。
平常由 daily_update.py 自動執行；也可以手動：
  python load_recap.py                 抓這一季
  python load_recap.py --season 2025-26  抓指定球季
  python load_recap.py --dry-run       試跑：只抓資料、算筆數，不寫進資料庫

需要先在 Supabase 的 SQL Editor 執行過 schema_recap.sql
"""

import argparse
import time
from datetime import date

import pandas as pd

from fetch_nba import MAX_RETRIES, REQUEST_DELAY, TIMEOUT, season_of
from load_to_supabase import connect, upsert

SEASON_TYPES = ["Regular Season", "PlayIn", "Playoffs"]
STAT_COLS = ["FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA", "OREB", "DREB", "REB",
             "AST", "STL", "BLK", "TOV", "PF", "PTS", "PLUS_MINUS"]


def game_log(season, season_type, who):
    """who = 'T'（球隊）或 'P'（球員）；一次拿回整季全聯盟的逐場數據"""
    from nba_api.stats.endpoints import leaguegamelog

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            return leaguegamelog.LeagueGameLog(
                season=season, season_type_all_star=season_type,
                player_or_team_abbreviation=who, timeout=TIMEOUT,
            ).get_data_frames()[0]
        except Exception as e:
            wait = REQUEST_DELAY * attempt * 2
            print(f"    第 {attempt} 次失敗：{type(e).__name__}，{wait} 秒後重試")
            time.sleep(wait)
    print("    放棄，下次執行會再試")
    return None


def tidy(df, season, season_type):
    """統一欄位：小寫名稱、日期格式、數字型態、主客場"""
    df = df.copy()
    for c in STAT_COLS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")
    df["MIN"] = pd.to_numeric(df.get("MIN"), errors="coerce").round(2)
    df["GAME_DATE"] = pd.to_datetime(df["GAME_DATE"]).dt.strftime("%Y-%m-%d")
    df["GAME_ID"] = df["GAME_ID"].astype(str).str.zfill(10)
    df["IS_HOME"] = df["MATCHUP"].str.contains("vs.", regex=False)
    df.insert(0, "SEASON", season)
    df.insert(1, "SEASON_TYPE", season_type)
    return df.rename(columns={"TEAM_ABBREVIATION": "ABBREVIATION"})


def load_recap(client, season):
    for st in SEASON_TYPES:
        print(f"  {season} {st}")
        teams = game_log(season, st, "T")
        if teams is None or teams.empty:
            print("    還沒有比賽，略過")
            continue
        t = tidy(teams, season, st)
        t["OPP_PTS"] = t["PTS"] - t["PLUS_MINUS"]          # 對手得分 = 自己得分 − 淨勝分
        keep = ["SEASON", "SEASON_TYPE", "GAME_ID", "GAME_DATE", "TEAM_ID", "ABBREVIATION", "MATCHUP",
                "IS_HOME", "WL", "MIN", "OPP_PTS"] + STAT_COLS
        t = t[[c for c in keep if c in t.columns]].rename(columns=str.lower)
        t = t.drop_duplicates(["game_id", "team_id"])
        upsert(client, "recap_team_games", t, "game_id,team_id")

        players = game_log(season, st, "P")
        if players is None or players.empty:
            continue
        p = tidy(players, season, st)
        keep = ["SEASON", "SEASON_TYPE", "GAME_ID", "GAME_DATE", "PLAYER_ID", "PLAYER_NAME", "TEAM_ID",
                "ABBREVIATION", "MATCHUP", "WL", "MIN"] + STAT_COLS
        p = p[[c for c in keep if c in p.columns]].rename(columns=str.lower)
        p = p.drop_duplicates(["game_id", "player_id"])
        upsert(client, "recap_player_games", p, "game_id,player_id")


def main():
    parser = argparse.ArgumentParser(description="抓全聯盟本季逐場比分與球員數據（每日戰報用）")
    parser.add_argument("--season", default=season_of(date.today()), help="球季，例如 2026-27（預設：這一季）")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料、算筆數，不寫進資料庫")
    args = parser.parse_args()

    client = None if args.dry_run else connect()
    print(f"===== 每日戰報資料：{args.season} =====" + ("　【試跑模式】" if args.dry_run else ""))
    load_recap(client, args.season)
    print("\n全部完成！")


if __name__ == "__main__":
    main()
