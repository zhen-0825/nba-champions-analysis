"""
NBA 球隊球員逐場數據抓取工具（預設：金州勇士 GSW）

功能
  1. 輸入任何日期範圍，自動判斷橫跨哪幾個球季，一季一季抓回來
  2. 抓過的球季會存在電腦裡（data/raw），下次查詢直接讀取，不用重抓
  3. 已經打完的球季只抓一次；進行中的球季超過 12 小時會自動更新
  4. 依你指定的日期範圍篩選，匯出 Excel（逐場數據 + 球員彙總）

用法（在 VS Code 終端機輸入）
  python fetch_nba.py --start 2026-01-01 --end 2026-01-31
  python fetch_nba.py --start 2023-10-01 --end 2026-06-30
  python fetch_nba.py --team LAL --start 2025-10-01 --end 2026-06-30
  python fetch_nba.py --start 2025-10-01 --refresh        （強制重新下載）
  python fetch_nba.py --start 2025-10-01 --preseason      （加上季前賽）
"""

import argparse
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

# ===== 設定區：想調整就改這裡 =====
BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "data" / "raw"        # 原始資料存放位置
REPORT_DIR = BASE_DIR / "reports"          # Excel 報表存放位置

SEASON_TYPES = ["Regular Season", "PlayIn", "Playoffs"]   # 例行賽、附加賽、季後賽
REQUEST_DELAY = 2           # 每次向 NBA 要資料之間停幾秒（避免被擋）
MAX_RETRIES = 3             # 失敗時最多重試幾次
TIMEOUT = 60                # 每次最多等幾秒
REFRESH_HOURS = 12          # 進行中的球季，存檔超過幾小時就重新抓
# ==================================


def season_of(d):
    """把日期換算成 NBA 球季。NBA 球季大約 10 月開打、隔年 6 月結束，
    所以 2026-01-15 屬於 2025-26 球季，2025-11-01 也屬於 2025-26 球季。"""
    start_year = d.year if d.month >= 8 else d.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def seasons_between(start, end):
    """列出開始到結束日期之間的所有球季"""
    first = int(season_of(start)[:4])
    last = int(season_of(end)[:4])
    return [f"{y}-{str(y + 1)[-2:]}" for y in range(first, last + 1)]


def season_is_finished(season):
    """球季是否已經結束（結束年的 7 月 1 日之後就當作打完了）"""
    end_year = int(season[:4]) + 1
    return date.today() >= date(end_year, 7, 1)


def get_team(abbr):
    """用球隊縮寫（如 GSW、LAL）找出球隊編號"""
    from nba_api.stats.static import teams
    team = teams.find_team_by_abbreviation(abbr.upper())
    if team is None:
        raise SystemExit(f"找不到球隊縮寫 {abbr}，請確認拼字（例如 GSW、LAL、BOS）")
    return team


def download_season(team_id, season, season_type):
    """向 NBA 官網要一整季的球員逐場數據，失敗會自動重試"""
    from nba_api.stats.endpoints import playergamelogs

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            result = playergamelogs.PlayerGameLogs(
                team_id_nullable=team_id,
                season_nullable=season,
                season_type_nullable=season_type,
                timeout=TIMEOUT,
            )
            return result.get_data_frames()[0]
        except Exception as e:
            print(f"    第 {attempt} 次失敗：{type(e).__name__}，{REQUEST_DELAY * attempt * 2} 秒後重試")
            time.sleep(REQUEST_DELAY * attempt * 2)
    return None


def cache_path(team_abbr, season, season_type):
    return RAW_DIR / team_abbr / f"{season}_{season_type.replace(' ', '_')}.csv"


def read_cache(path):
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def load_season(team, season, season_type, refresh=False):
    """先看電腦裡有沒有存過；沒有、或需要更新，才向 NBA 要資料"""
    path = cache_path(team["abbreviation"], season, season_type)

    if path.exists() and not refresh:
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if season_is_finished(season) or age_hours < REFRESH_HOURS:
            print(f"  {season} {season_type}：讀取已存檔資料")
            return read_cache(path)

    print(f"  {season} {season_type}：向 NBA 官網下載中…")
    df = download_season(team["id"], season, season_type)

    if df is None:
        if path.exists():
            print("    下載失敗，改用舊的存檔資料")
            return read_cache(path)
        print("    下載失敗，這一段先跳過")
        return pd.DataFrame()

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"    完成，共 {len(df)} 筆")
    return df


def fetch_games(team_abbr="GSW", start="2025-10-01", end=None,
                season_types=SEASON_TYPES, refresh=False):
    """主功能：抓回指定球隊、指定日期範圍的球員逐場數據"""
    start_d = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date() if end else date.today()
    if start_d > end_d:
        raise SystemExit("開始日期不能晚於結束日期")

    team = get_team(team_abbr)
    seasons = seasons_between(start_d, end_d)
    print(f"{team['full_name']}｜{start_d} ~ {end_d}｜涵蓋球季：{', '.join(seasons)}")

    frames = []
    for season in seasons:
        for season_type in season_types:
            df = load_season(team, season, season_type, refresh)
            if not df.empty:
                df["SEASON"] = season
                df["SEASON_TYPE"] = season_type
                frames.append(df)

    if not frames:
        print("沒有抓到任何資料")
        return pd.DataFrame()

    data = pd.concat(frames, ignore_index=True)
    data["GAME_DATE"] = pd.to_datetime(data["GAME_DATE"]).dt.date
    data = data[(data["GAME_DATE"] >= start_d) & (data["GAME_DATE"] <= end_d)]
    data = data.drop_duplicates(subset=["GAME_ID", "PLAYER_ID"])
    data = data.sort_values(["GAME_DATE", "PLAYER_NAME"]).reset_index(drop=True)
    return data


def player_summary(data):
    """依球員加總，計算命中率、三分命中率、真實命中率"""
    cols = ["MIN", "PTS", "FGM", "FGA", "FG3M", "FG3A", "FTM", "FTA",
            "REB", "AST", "STL", "BLK", "TOV"]
    cols = [c for c in cols if c in data.columns]
    s = data.groupby("PLAYER_NAME")[cols].sum()
    s.insert(0, "GP", data.groupby("PLAYER_NAME")["GAME_ID"].nunique())

    s["FG%"] = (s["FGM"] / s["FGA"]).round(3)
    s["3P%"] = (s["FG3M"] / s["FG3A"]).round(3)
    s["TS%"] = (s["PTS"] / (2 * (s["FGA"] + 0.44 * s["FTA"]))).round(3)
    s["PPG"] = (s["PTS"] / s["GP"]).round(1)
    return s.sort_values("PTS", ascending=False).reset_index()


def main():
    parser = argparse.ArgumentParser(description="抓取 NBA 球隊球員逐場數據")
    parser.add_argument("--team", default="GSW", help="球隊縮寫，預設 GSW（勇士）")
    parser.add_argument("--start", required=True, help="開始日期，格式 2026-01-01")
    parser.add_argument("--end", default=None, help="結束日期，不填就是今天")
    parser.add_argument("--no-playoffs", action="store_true", help="只抓例行賽")
    parser.add_argument("--preseason", action="store_true", help="加上季前賽")
    parser.add_argument("--refresh", action="store_true", help="忽略存檔，全部重新下載")
    args = parser.parse_args()

    types = ["Regular Season"] if args.no_playoffs else list(SEASON_TYPES)
    if args.preseason:
        types = ["Pre Season"] + types
    data = fetch_games(args.team, args.start, args.end, types, args.refresh)
    if data.empty:
        return

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    end_label = args.end or date.today().isoformat()
    out = REPORT_DIR / f"{args.team.upper()}_{args.start}_{end_label}.xlsx"
    with pd.ExcelWriter(out) as writer:
        player_summary(data).to_excel(writer, sheet_name="球員彙總", index=False)
        data.to_excel(writer, sheet_name="逐場數據", index=False)

    games = data["GAME_ID"].nunique()
    print(f"\n完成！{games} 場比賽、{len(data)} 筆球員數據")
    print(f"報表已存到：{out}")


if __name__ == "__main__":
    main()
