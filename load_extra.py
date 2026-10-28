"""
抓取進階數據並寫進 Supabase（2016-17 球季起）

  shots      投籃分布：8 支冠軍隊每一次出手的位置與結果，加上聯盟各區域平均
  playtypes  戰術使用：全聯盟 30 隊（進攻、防守）與全部球員（進攻）的 Synergy 戰術數據
  lineups    陣容組合：8 支冠軍隊的 5 人陣容同時在場時間與效率
  tracking   跑動距離：全聯盟球員與球隊的每場跑動距離、速度

用法（在 VS Code 終端機輸入）
  python load_extra.py --only tracking --dry-run   先試跑最小的一種，不寫進資料庫
  python load_extra.py --only tracking             一次只做一種（建議）
  python load_extra.py --only lineups
  python load_extra.py --only playtypes            呼叫次數最多，大約 30 分鐘
  python load_extra.py --only shots                資料量最大，大約 20～30 分鐘
  python load_extra.py                             四種全部（約 1 小時以上）

需要先做好
  1. .env 裡有 SUPABASE_URL 和 SUPABASE_SECRET_KEY
  2. 在 Supabase 的 SQL Editor 執行過 schema_extra.sql
抓過且已結束的球季會存在 data/extra，下次直接讀取，不重抓。
"""

import argparse
import os
import time
from datetime import date

import pandas as pd

from fetch_nba import MAX_RETRIES, REQUEST_DELAY, TIMEOUT, season_is_finished, seasons_between
from load_to_supabase import CHAMPION_TEAMS, connect, upsert

# ===== 設定區 =====
FIRST_SEASON_START = date(2016, 10, 1)            # 2016-17 球季起
SEASON_TYPES = ["Regular Season", "Playoffs"]
PLAY_TYPES = ["Isolation", "Transition", "PRBallHandler", "PRRollman", "Postup",
              "Spotup", "Handoff", "Cut", "OffScreen", "OffRebound", "Misc"]
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "extra")
# ==================

SHOT_COLS = {"GAME_ID": "game_id", "GAME_EVENT_ID": "game_event_id", "GAME_DATE": "game_date",
             "TEAM_ID": "team_id", "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
             "PERIOD": "period", "MINUTES_REMAINING": "minutes_remaining",
             "SECONDS_REMAINING": "seconds_remaining", "ACTION_TYPE": "action_type",
             "SHOT_TYPE": "shot_type", "SHOT_ZONE_BASIC": "zone_basic", "SHOT_ZONE_AREA": "zone_area",
             "SHOT_ZONE_RANGE": "zone_range", "SHOT_DISTANCE": "shot_distance",
             "LOC_X": "loc_x", "LOC_Y": "loc_y", "SHOT_MADE_FLAG": "made"}
ZONE_COLS = {"SHOT_ZONE_BASIC": "zone_basic", "SHOT_ZONE_AREA": "zone_area",
             "SHOT_ZONE_RANGE": "zone_range", "FGA": "fga", "FGM": "fgm", "FG_PCT": "fg_pct"}
PT_COLS = {"TEAM_ID": "team_id", "PLAYER_ID": "player_id", "PLAYER_NAME": "player_name",
           "PLAY_TYPE": "play_type", "GP": "gp", "POSS": "poss", "POSS_PCT": "poss_pct", "PPP": "ppp",
           "PTS": "pts", "FG_PCT": "fg_pct", "EFG_PCT": "efg_pct", "TOV_POSS_PCT": "tov_poss_pct",
           "SCORE_POSS_PCT": "score_poss_pct", "PERCENTILE": "percentile"}
LU_BASE = {"GROUP_ID": "group_id", "GROUP_NAME": "group_name", "TEAM_ID": "team_id", "GP": "gp",
           "W": "w", "L": "l", "MIN": "min", "PTS": "pts", "FGA": "fga", "FG3A": "fg3a", "FG3M": "fg3m",
           "AST": "ast", "TOV": "tov", "REB": "reb", "PLUS_MINUS": "plus_minus"}
LU_ADV = {"OFF_RATING": "off_rating", "DEF_RATING": "def_rating", "NET_RATING": "net_rating",
          "PACE": "pace", "POSS": "poss"}
TR_COLS = {"GP": "gp", "MIN": "min", "DIST_MILES": "dist_miles", "DIST_MILES_OFF": "dist_miles_off",
           "DIST_MILES_DEF": "dist_miles_def", "AVG_SPEED": "avg_speed",
           "AVG_SPEED_OFF": "avg_speed_off", "AVG_SPEED_DEF": "avg_speed_def"}


# ---------------------------------------------------------------------
# 共用：呼叫 NBA、存快取、挑欄位
# ---------------------------------------------------------------------
def call(endpoint, label, **params):
    """呼叫 NBA 的某個資料端點，失敗自動重試；回傳全部表格（list）"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            return endpoint(timeout=TIMEOUT, **params).get_data_frames()
        except Exception as e:
            wait = REQUEST_DELAY * attempt * 2
            print(f"    {label} 第 {attempt} 次失敗：{type(e).__name__}，{wait} 秒後重試")
            time.sleep(wait)
    print(f"    {label} 放棄，下次執行會再試")
    return None


def read_csv_safe(path):
    """讀存檔；空的表格（那一季沒有這種資料）存成檔案後會沒有欄位，讀回來當作空表"""
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def cached(name, season, fetch):
    """打完的球季讀存檔；沒存過或球季進行中才呼叫 NBA"""
    folder = os.path.join(CACHE, name)
    first = os.path.join(folder, "0.csv")
    if os.path.exists(first) and season_is_finished(season):
        files = sorted(f for f in os.listdir(folder) if f.endswith(".csv"))
        return [read_csv_safe(os.path.join(folder, f)) for f in files]
    frames = fetch()
    if frames is None:
        return None
    os.makedirs(folder, exist_ok=True)
    for i, df in enumerate(frames):
        df.to_csv(os.path.join(folder, f"{i}.csv"), index=False)
    return frames


def pick(df, cols):
    """只留需要的欄位並改成小寫名稱；NBA 少給的欄位就略過"""
    keep = {k: v for k, v in cols.items() if k in df.columns}
    return df[list(keep)].rename(columns=keep)


def as_int(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").round().astype("Int64")
    return df


def all_seasons():
    return seasons_between(FIRST_SEASON_START, date.today())


def team_ids(abbrs):
    from nba_api.stats.static import teams
    return {t["abbreviation"]: t["id"] for t in teams.get_teams() if t["abbreviation"] in abbrs}


# ---------------------------------------------------------------------
# 1. 投籃分布
# ---------------------------------------------------------------------
def load_shots(client, abbrs):
    from nba_api.stats.endpoints import shotchartdetail

    print("\n===== 投籃分布（每一次出手）=====")
    ids, done_zones = team_ids(abbrs), set()
    for abbr, tid in ids.items():
        for season in all_seasons():
            for st in SEASON_TYPES:
                label = f"{abbr} {season} {st}"
                frames = cached(f"shots/{abbr}_{season}_{st.replace(' ', '_')}", season, lambda: call(
                    shotchartdetail.ShotChartDetail, label, team_id=tid, player_id=0,
                    season_nullable=season, season_type_all_star=st,
                    context_measure_simple="FGA"))        # FGA = 全部出手（預設只給進球）
                if not frames or frames[0].empty:
                    continue
                shots = pick(frames[0], SHOT_COLS)
                shots["game_date"] = pd.to_datetime(shots["game_date"].astype(str), format="%Y%m%d",
                                                    errors="coerce").dt.strftime("%Y-%m-%d")
                shots = as_int(shots, ["game_event_id", "team_id", "player_id", "period", "minutes_remaining",
                                       "seconds_remaining", "shot_distance", "loc_x", "loc_y"])
                shots["made"] = pd.to_numeric(shots["made"], errors="coerce") == 1
                shots["game_id"] = shots["game_id"].astype(str).str.zfill(10)   # 補回開頭的 00
                shots.insert(2, "season", season)
                shots.insert(3, "season_type", st)
                shots = shots.drop_duplicates(["game_id", "game_event_id"])
                print(f"  {label}")
                upsert(client, "shots", shots, "game_id,game_event_id")

                # 聯盟各區域平均：每季每種比賽類型只要存一次
                if (season, st) not in done_zones and len(frames) > 1 and not frames[1].empty:
                    zones = pick(frames[1], ZONE_COLS)
                    zones.insert(0, "season", season)
                    zones.insert(1, "season_type", st)
                    zones = zones.drop_duplicates(["zone_basic", "zone_area", "zone_range"])
                    upsert(client, "shot_zone_league", zones, "season,season_type,zone_basic,zone_area,zone_range")
                    done_zones.add((season, st))


# ---------------------------------------------------------------------
# 2. 戰術使用（Synergy）
# ---------------------------------------------------------------------
def load_playtypes(client):
    from nba_api.stats.endpoints import synergyplaytypes

    print("\n===== 戰術使用（Synergy）=====")
    jobs = [("T", st, grouping) for st in SEASON_TYPES for grouping in ["offensive", "defensive"]]
    jobs.append(("P", "Regular Season", "offensive"))      # 球員只抓進攻端、例行賽
    for season in all_seasons():
        for who, st, grouping in jobs:
            rows = []
            for play in PLAY_TYPES:
                label = f"{season} {st} {'球隊' if who == 'T' else '球員'} {grouping} {play}"
                frames = cached(f"playtypes/{who}_{season}_{st.replace(' ', '_')}_{grouping}_{play}", season,
                                lambda: call(synergyplaytypes.SynergyPlayTypes, label, league_id="00",
                                             per_mode_simple="Totals", player_or_team_abbreviation=who,
                                             season=season, season_type_all_star=st,
                                             play_type_nullable=play, type_grouping_nullable=grouping))
                if frames and not frames[0].empty:
                    df = pick(frames[0], PT_COLS)
                    df["play_type"] = play
                    rows.append(df)
            if not rows:
                continue
            df = pd.concat(rows, ignore_index=True)
            df.insert(0, "season", season)
            df.insert(1, "season_type", st)
            df = as_int(df, ["team_id", "player_id"])
            print(f"  {season} {st} {'球隊' if who == 'T' else '球員'} {grouping}")
            if who == "T":
                df = df.drop(columns=[c for c in ["player_id", "player_name"] if c in df.columns])
                df["type_grouping"] = grouping
                df = df.drop_duplicates(["team_id", "play_type", "type_grouping"])
                upsert(client, "playtypes_team", df, "season,season_type,team_id,play_type,type_grouping")
            else:
                df = df.drop_duplicates(["player_id", "team_id", "play_type"])
                upsert(client, "playtypes_player", df, "season,season_type,player_id,team_id,play_type")


# ---------------------------------------------------------------------
# 3. 5 人陣容組合
# ---------------------------------------------------------------------
def load_lineups(client, abbrs):
    from nba_api.stats.endpoints import leaguedashlineups

    print("\n===== 5 人陣容組合 =====")
    keep_ids = set(team_ids(abbrs).values())
    for season in all_seasons():
        for st in SEASON_TYPES:
            parts = {}
            for measure in ["Base", "Advanced"]:
                label = f"{season} {st} {measure}"
                frames = cached(f"lineups/{season}_{st.replace(' ', '_')}_{measure}", season, lambda: call(
                    leaguedashlineups.LeagueDashLineups, label, group_quantity=5,
                    measure_type_detailed_defense=measure, per_mode_detailed="Totals",
                    season=season, season_type_all_star=st))
                parts[measure] = frames[0] if frames else pd.DataFrame()
            base = parts["Base"]
            if base.empty:
                continue
            df = pick(base, LU_BASE)
            if not parts["Advanced"].empty:
                adv = pick(parts["Advanced"], {"GROUP_ID": "group_id", "TEAM_ID": "team_id", **LU_ADV})
                df = df.merge(adv, on=["group_id", "team_id"], how="left")
            df = as_int(df, ["team_id"])
            df = df[df["team_id"].isin(keep_ids)].drop_duplicates(["team_id", "group_id"])
            df.insert(0, "season", season)
            df.insert(1, "season_type", st)
            print(f"  {season} {st}")
            upsert(client, "lineups", df, "season,season_type,team_id,group_id")


# ---------------------------------------------------------------------
# 4. 跑動距離與速度
# ---------------------------------------------------------------------
def load_tracking(client):
    from nba_api.stats.endpoints import leaguedashptstats

    print("\n===== 跑動距離與速度 =====")
    for season in all_seasons():
        for st in SEASON_TYPES:
            rows = []
            for entity in ["Player", "Team"]:
                label = f"{season} {st} {entity}"
                frames = cached(f"tracking/{season}_{st.replace(' ', '_')}_{entity}", season, lambda: call(
                    leaguedashptstats.LeagueDashPtStats, label, pt_measure_type="SpeedDistance",
                    player_or_team=entity, per_mode_simple="PerGame",
                    season=season, season_type_all_star=st))
                if not frames or frames[0].empty:
                    continue
                raw = frames[0]
                df = pick(raw, TR_COLS)
                if entity == "Player":
                    df.insert(0, "id", raw["PLAYER_ID"])
                    df.insert(1, "name", raw.get("PLAYER_NAME"))
                    df.insert(2, "team_id", raw.get("TEAM_ID"))
                else:
                    df.insert(0, "id", raw["TEAM_ID"])
                    df.insert(1, "name", raw.get("TEAM_NAME"))
                    df.insert(2, "team_id", raw["TEAM_ID"])
                df.insert(0, "entity", entity.lower())
                rows.append(df)
            if not rows:
                continue
            df = pd.concat(rows, ignore_index=True)
            df = as_int(df, ["id", "team_id"]).drop_duplicates(["entity", "id"])
            df.insert(0, "season", season)
            df.insert(1, "season_type", st)
            print(f"  {season} {st}")
            upsert(client, "tracking_speed", df, "season,season_type,entity,id")


def main():
    parser = argparse.ArgumentParser(description="抓取投籃分布、戰術、陣容、跑動數據寫進 Supabase")
    parser.add_argument("--only", choices=["shots", "playtypes", "lineups", "tracking"], help="只做其中一種")
    parser.add_argument("--teams", nargs="+", default=CHAMPION_TEAMS, help="投籃與陣容要抓的球隊")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料、算筆數，不寫進資料庫")
    args = parser.parse_args()

    client = None if args.dry_run else connect()
    if args.dry_run:
        print("【試跑模式】不會寫進資料庫")
    print(f"球季：{', '.join(all_seasons())}")

    start = time.time()
    if args.only in (None, "tracking"):
        load_tracking(client)
    if args.only in (None, "lineups"):
        load_lineups(client, args.teams)
    if args.only in (None, "playtypes"):
        load_playtypes(client)
    if args.only in (None, "shots"):
        load_shots(client, args.teams)
    print(f"\n全部完成！花了 {(time.time() - start) / 60:.0f} 分鐘")


if __name__ == "__main__":
    main()
