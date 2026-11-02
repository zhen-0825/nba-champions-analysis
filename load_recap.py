"""
每日戰報資料：抓「這一季」全聯盟 30 隊每一場比賽的球隊比分與球員數據，寫進 Supabase

  recap_team_games    每場比賽 × 每支球隊一筆（比分、勝負、命中、失誤…）
  recap_player_games  每場比賽 × 每位球員一筆（得分、籃板、助攻、三分…）
  recap_schedule      接下來 7 天的賽程（誰打誰），給「下一場預測」用

只要呼叫 NBA 幾次（每種比賽類型：球隊一次、球員一次），每天跑也很快。
平常由 daily_update.py 自動執行；也可以手動：
  python load_recap.py                 抓這一季
  python load_recap.py --season 2025-26  抓指定球季
  python load_recap.py --dry-run       試跑：只抓資料、算筆數，不寫進資料庫

需要先在 Supabase 的 SQL Editor 執行過 schema_recap.sql、schema_schedule.sql
"""

import argparse
import time
import warnings
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


SCHEDULE_DAYS = 7   # 抓今天起幾天的賽程


def team_maps():
    from nba_api.stats.static import teams
    t = teams.get_teams()
    return {x["id"]: x["abbreviation"] for x in t}


def find_col(df, *names):
    """NBA 不同資料端點的欄位名稱寫法不一樣，依序找第一個存在的"""
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None


SCHEDULE_CDN = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json"


def schedule_from_cdn():
    """方法零（最穩）：NBA 官網賽程頁用的公開 JSON 檔，一次拿回整季賽程（不用經過 nba_api）"""
    import requests

    r = requests.get(SCHEDULE_CDN, timeout=TIMEOUT, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nba.com/"})
    r.raise_for_status()
    rows = []
    for gd in r.json()["leagueSchedule"]["gameDates"]:
        for g in gd.get("games", []):
            d = g.get("gameDateEst") or gd.get("gameDate")
            rows.append({"game_id": str(g["gameId"]).zfill(10),
                         "game_date": pd.to_datetime(str(d)[:10], errors="coerce"),
                         "home_team_id": (g.get("homeTeam") or {}).get("teamId"),
                         "away_team_id": (g.get("awayTeam") or {}).get("teamId"),
                         "status": g.get("gameStatusText")})
    df = pd.DataFrame(rows)
    df["home_team_id"] = pd.to_numeric(df["home_team_id"], errors="coerce")
    df["away_team_id"] = pd.to_numeric(df["away_team_id"], errors="coerce")
    return df


def schedule_from_season(season):
    """方法一：整季賽程表（ScheduleLeagueV2），一次拿回全部比賽"""
    from nba_api.stats.endpoints import scheduleleaguev2

    frames = scheduleleaguev2.ScheduleLeagueV2(league_id="00", season=season, timeout=TIMEOUT).get_data_frames()
    df = frames[0]
    gid = find_col(df, "gameId")
    gdate = find_col(df, "gameDateEst", "gameDate")
    hid, aid = find_col(df, "homeTeam_teamId"), find_col(df, "awayTeam_teamId")
    status = find_col(df, "gameStatusText")
    if not all([gid, gdate, hid, aid]):
        raise ValueError(f"賽程表欄位和預期不同：{list(df.columns)[:12]}")
    return pd.DataFrame({"game_id": df[gid].astype(str).str.zfill(10),
                         "game_date": pd.to_datetime(df[gdate], errors="coerce"),
                         "home_team_id": pd.to_numeric(df[hid], errors="coerce"),
                         "away_team_id": pd.to_numeric(df[aid], errors="coerce"),
                         "status": df[status] if status else None})


def _find_games(obj):
    """在 NBA 回傳的資料裡找出「games」那一串（不同版本放的位置不一樣）"""
    if isinstance(obj, dict):
        if isinstance(obj.get("games"), list):
            return obj["games"]
        for v in obj.values():
            g = _find_games(v)
            if g is not None:
                return g
    return None


def schedule_from_scoreboard_v3(days):
    """方法二：一天一天問「這天有哪些比賽」（ScoreboardV3，NBA 建議取代 V2 的新版）"""
    from nba_api.stats.endpoints import scoreboardv3

    rows = []
    for d in days:
        time.sleep(REQUEST_DELAY)
        data = scoreboardv3.ScoreboardV3(game_date=d.strftime("%Y-%m-%d"), league_id="00", timeout=TIMEOUT).get_dict()
        for g in _find_games(data) or []:
            rows.append({"game_id": str(g.get("gameId")).zfill(10), "game_date": pd.Timestamp(d),
                         "home_team_id": (g.get("homeTeam") or {}).get("teamId"),
                         "away_team_id": (g.get("awayTeam") or {}).get("teamId"),
                         "status": g.get("gameStatusText")})
    df = pd.DataFrame(rows, columns=["game_id", "game_date", "home_team_id", "away_team_id", "status"])
    df["home_team_id"] = pd.to_numeric(df["home_team_id"], errors="coerce")
    df["away_team_id"] = pd.to_numeric(df["away_team_id"], errors="coerce")
    return df


def schedule_from_scoreboard(days):
    """方法四（最後備案）：一天一天問「這天有哪些比賽」（ScoreboardV2）"""
    warnings.filterwarnings("ignore", category=DeprecationWarning)   # V2 的過時警告很長，不顯示
    from nba_api.stats.endpoints import scoreboardv2

    rows = []
    for d in days:
        time.sleep(REQUEST_DELAY)
        gh = scoreboardv2.ScoreboardV2(game_date=d.strftime("%Y-%m-%d"), timeout=TIMEOUT).get_data_frames()[0]
        for _, r in gh.iterrows():
            rows.append({"game_id": str(r["GAME_ID"]).zfill(10), "game_date": pd.Timestamp(d),
                         "home_team_id": r["HOME_TEAM_ID"], "away_team_id": r["VISITOR_TEAM_ID"],
                         "status": r.get("GAME_STATUS_TEXT")})
    return pd.DataFrame(rows)


def load_schedule(client, season):
    """抓接下來 7 天的賽程。美國日期比台灣晚一天左右，所以從「昨天」開始抓"""
    start = pd.Timestamp(date.today()) - pd.Timedelta(days=1)
    days = [start + pd.Timedelta(days=i) for i in range(SCHEDULE_DAYS + 1)]
    print(f"  賽程 {days[0]:%m/%d}～{days[-1]:%m/%d}")
    sched = None
    for name, fn in [("NBA 官網賽程檔", schedule_from_cdn), ("逐日查詢（新版 V3）", lambda: schedule_from_scoreboard_v3(days)),
                     ("整季賽程表", lambda: schedule_from_season(season)),
                     ("逐日查詢（舊版 V2）", lambda: schedule_from_scoreboard(days))]:
        try:
            got = fn()
            got = got[(got["game_date"] >= days[0]) & (got["game_date"] <= days[-1])]
            if got.empty:
                print(f"    {name}：這段期間沒有比賽，換下一種方法")
                continue
            print(f"    {name}：讀到 {len(got)} 場")
            sched = got
            break
        except Exception as e:
            print(f"    {name}讀取失敗（{type(e).__name__}：{str(e)[:120]}），換下一種方法")
    if sched is None:
        print("    四種方法都失敗，這次先略過賽程（比分資料不受影響）")
        return
    if sched is None or sched.empty:
        print("    這段期間沒有比賽")
        return
    abbr = team_maps()
    sched = sched.dropna(subset=["game_date", "home_team_id", "away_team_id"]).copy()
    sched["home_team_id"] = sched["home_team_id"].astype("int64")
    sched["away_team_id"] = sched["away_team_id"].astype("int64")
    sched["home_abbr"] = sched["home_team_id"].map(abbr)
    sched["away_abbr"] = sched["away_team_id"].map(abbr)
    sched = sched.dropna(subset=["home_abbr", "away_abbr"])     # 明星賽等非正式球隊不要
    sched["game_date"] = sched["game_date"].dt.strftime("%Y-%m-%d")
    sched.insert(1, "season", season)
    upsert(client, "recap_schedule", sched.drop_duplicates("game_id"), "game_id")


def main():
    parser = argparse.ArgumentParser(description="抓全聯盟本季逐場比分與球員數據（每日戰報用）")
    parser.add_argument("--season", default=season_of(date.today()), help="球季，例如 2026-27（預設：這一季）")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料、算筆數，不寫進資料庫")
    args = parser.parse_args()

    client = None if args.dry_run else connect()
    print(f"===== 每日戰報資料：{args.season} =====" + ("　【試跑模式】" if args.dry_run else ""))
    load_recap(client, args.season)
    if args.season == season_of(date.today()):      # 只有進行中的球季才需要未來賽程
        try:
            load_schedule(client, args.season)
        except Exception as e:                        # 賽程表還沒建立等狀況：不影響比分資料
            print(f"    賽程寫入失敗，略過：{str(e)[:120]}")
    print("\n全部完成！")


if __name__ == "__main__":
    main()
