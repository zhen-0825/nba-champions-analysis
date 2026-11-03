"""
把「下一個比賽日」的預測存進 Supabase，隔天比賽打完就能對答案（每日戰報的「預測準不準」）

  recap_predictions         每場比賽的預測：勝率、預估比分、影響因素
  recap_player_predictions  每場兩隊各 2 位球員的預估：得分（含合理範圍）、籃板、助攻

算法和網站上的預測卡完全一樣（都用 predict.py），所以存下來的就是你在網站上看到的那一份。
同一場比賽只存第一次（比賽開打前那份），之後重跑不會改掉，避免「事後偷改答案」。

平常由 daily_update.py 自動執行；也可以手動：
  python save_predictions.py              存下一個比賽日的預測
  python save_predictions.py --backfill   把本季已經打完的每一天也補算一次（只用「那天以前」的資料，標記為事後回推）
  python save_predictions.py --dry-run    試跑：只計算、印出結果，不寫進資料庫

需要先在 Supabase 的 SQL Editor 執行過 schema_predictions.sql
"""

import argparse
from datetime import date

import pandas as pd

from fetch_nba import season_of
from load_to_supabase import connect, upsert
from predict import predict_day, season_avg

LIVE, BACKFILL = "當天存下", "事後回推"


def read(client, table, filters, order, page=1000):
    rows, start = [], 0
    while True:
        q = client.table(table).select("*")
        for op, col, val in filters:
            q = getattr(q, op)(col, val)
        for c in order:
            q = q.order(c)
        part = q.range(start, start + page - 1).execute().data
        rows += part
        if len(part) < page:
            break
        start += page
    df = pd.DataFrame(rows)
    if not df.empty and "game_date" in df:
        df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def already_saved(client, season):
    try:
        df = read(client, "recap_predictions", [("eq", "season", season)], ["game_id"])
    except Exception as e:
        raise SystemExit(f"讀不到 recap_predictions（{str(e)[:100]}）。請先在 Supabase 執行 schema_predictions.sql")
    return set(df["game_id"]) if not df.empty else set()


def games_from_results(tg, day):
    """過去某天的對戰組合：從比分資料找出主客隊"""
    d = tg[(tg["game_date"] == day) & (tg["season_type"] == "Regular Season")]
    rows = []
    for gid, g in d.groupby("game_id"):
        if len(g) != 2 or not g["is_home"].astype(bool).any():
            continue
        rows.append({"game_id": gid, "home_abbr": g[g["is_home"].astype(bool)]["abbreviation"].iloc[0],
                     "away_abbr": g[~g["is_home"].astype(bool)]["abbreviation"].iloc[0]})
    return pd.DataFrame(rows)


def save(client, season, gdf, pdf, source, saved, dry):
    if gdf.empty:
        return 0
    gdf = gdf[~gdf["game_id"].isin(saved)]
    if gdf.empty:
        return 0
    pdf = pdf[pdf["game_id"].isin(gdf["game_id"])] if not pdf.empty else pdf
    gdf = gdf.assign(season=season, source=source)
    if dry:
        for r in gdf.itertuples():
            fav = r.home_abbr if r.p_home >= 0.5 else r.away_abbr
            print(f"    {r.game_date} {r.away_abbr} {r.away_pts:.0f} : {r.home_pts:.0f} {r.home_abbr}　看好 {fav}（主隊勝率 {r.p_home:.0%}）")
        print(f"    （試跑）球員預測 {len(pdf)} 筆")
    else:
        upsert(client, "recap_predictions", gdf, "game_id")
        if not pdf.empty:
            upsert(client, "recap_player_predictions", pdf.assign(season=season, source=source), "game_id,player_id")
    return len(gdf)


def main():
    parser = argparse.ArgumentParser(description="存下一個比賽日的預測（隔天對答案用）")
    parser.add_argument("--season", default=season_of(date.today()))
    parser.add_argument("--backfill", action="store_true", help="把本季已經打完的每一天也補算一次")
    parser.add_argument("--dry-run", action="store_true", help="只計算、印出結果，不寫進資料庫")
    args = parser.parse_args()
    season = args.season

    client = connect()          # 試跑也要讀資料庫，所以一樣要連線（只是不寫入）
    print(f"===== 存預測：{season} =====" + ("　【試跑模式】" if args.dry_run else ""))
    tg = read(client, "recap_team_games", [("eq", "season", season)], ["game_date", "game_id", "team_id"])
    if tg.empty:
        print("  本季還沒有比分資料，略過")
        return
    saved = already_saved(client, season)
    last_done = tg["game_date"].max()

    # 1. 下一個比賽日（網站上正在顯示的那一份）
    sched = read(client, "recap_schedule", [("eq", "season", season), ("gt", "game_date", last_done.strftime("%Y-%m-%d"))],
                 ["game_date", "game_id"])
    if sched.empty:
        print("  沒有接下來的賽程，略過")
    else:
        day = sched["game_date"].min()
        since = (last_done - pd.Timedelta(days=21)).strftime("%Y-%m-%d")
        pl = read(client, "recap_player_games", [("eq", "season", season), ("gte", "game_date", since)],
                  ["game_date", "game_id", "player_id"])
        sa = read(client, "recap_player_season", [("eq", "season", season)], ["player_id", "team_id"])
        gdf, pdf = predict_day(tg, pl, sa, day, sched[sched["game_date"] == day])
        n = save(client, season, gdf, pdf, LIVE, saved, args.dry_run)
        print(f"  {day:%m/%d}（美國時間）：新存 {n} 場" + ("" if n else "（已經存過，或兩隊本季還沒打過）"))

    # 2. 補算過去每一天（選用）
    if args.backfill:
        pl_all = read(client, "recap_player_games", [("eq", "season", season)], ["game_date", "game_id", "player_id"])
        total = 0
        for day in sorted(tg.loc[tg["season_type"] == "Regular Season", "game_date"].unique()):
            day = pd.Timestamp(day)
            games = games_from_results(tg, day)
            if games.empty or games["game_id"].isin(saved).all():
                continue
            sa = season_avg(pl_all[pl_all["game_date"] < day])
            gdf, pdf = predict_day(tg, pl_all, sa, day, games)
            total += save(client, season, gdf, pdf, BACKFILL, saved, args.dry_run)
        print(f"  補算過去：新存 {total} 場（標記為「{BACKFILL}」）")
    print("\n完成！")


if __name__ == "__main__":
    main()
