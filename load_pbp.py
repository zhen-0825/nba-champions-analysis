"""
逐回合紀錄（play-by-play）：抓每一場比賽「每一次得分」的時間、誰得分、比分，寫進 Supabase，
並替每一場算好走勢摘要（領先互換、平手、最大領先、最大逆轉、最長連續得分、是不是關鍵時刻比賽）。

  pbp_events     每一次得分一筆（一場約 120 筆）
  pbp_game_flow  每一場比賽一筆（走勢摘要）

要抓哪些比賽：看 recap_team_games（load_recap.py 抓的本季全聯盟比賽），還沒抓過的才抓。
平常由 daily_update.py 自動執行（只補最近幾天）；也可以手動：
  python load_pbp.py                 補最近 3 天還沒抓的比賽
  python load_pbp.py --days 7        補最近 7 天
  python load_pbp.py --all           補這一季所有還沒抓的比賽（第一次用；一場約 3 秒，100 場約 5 分鐘）
  python load_pbp.py --game 0022600123   只抓一場（測試用，會重抓）
  python load_pbp.py --dry-run       試跑：只抓、只算，不寫進資料庫

需要先在 Supabase 的 SQL Editor 執行過 schema_recap.sql、schema_pbp.sql
"""

import argparse
import re
import time
from datetime import date, timedelta

import pandas as pd

from fetch_nba import MAX_RETRIES, REQUEST_DELAY, TIMEOUT, season_of
from load_to_supabase import connect, upsert

CLUTCH_SEC = 300      # 關鍵時刻：第四節或延長賽最後 5 分鐘（300 秒）
CLUTCH_MARGIN = 5     # 而且進球前分差在 5 分以內


# ---------------------------------------------------------------------
# 讀資料庫：要抓哪些比賽
# ---------------------------------------------------------------------
def read_all(client, table, cols, filters, page=1000):
    rows, start = [], 0
    while True:
        q = client.table(table).select(cols)
        for op, c, v in filters:
            q = getattr(q, op)(c, v)
        part = q.range(start, start + page - 1).execute().data
        rows += part
        if len(part) < page:
            return pd.DataFrame(rows)
        start += page


def games_to_load(client, season, days, everything):
    """recap_team_games 裡的比賽（一場兩筆：主隊、客隊），整理成一場一筆，去掉已經抓過的"""
    filters = [("eq", "season", season)]
    if not everything:
        filters.append(("gte", "game_date", (date.today() - timedelta(days=days)).isoformat()))
    tg = read_all(client, "recap_team_games",
                  "game_id,team_id,season_type,game_date,abbreviation,is_home,pts", filters)
    if tg.empty:
        return pd.DataFrame()
    try:
        fl = read_all(client, "pbp_game_flow", "game_id", [("eq", "season", season)])
    except Exception as e:
        raise SystemExit(f"讀不到 pbp_game_flow 資料表：{str(e)[:200]}\n"
                         "如果訊息裡有 does not exist 或 schema cache，請先在 Supabase SQL Editor 執行 schema_pbp.sql")
    done = set(fl["game_id"]) if "game_id" in fl else set()     # 第一次執行時表格是空的
    return pair_games(tg[~tg["game_id"].isin(done)])


def pair_games(tg):
    out = []
    for gid, g in tg.groupby("game_id"):
        h, a = g[g["is_home"] == True], g[g["is_home"] == False]   # noqa: E712
        if h.empty or a.empty:
            continue
        h, a = h.iloc[0], a.iloc[0]
        out.append({"game_id": gid, "season_type": h["season_type"], "game_date": h["game_date"],
                    "home_id": int(h["team_id"]), "away_id": int(a["team_id"]),
                    "home_abbr": h["abbreviation"], "away_abbr": a["abbreviation"],
                    "home_pts": h["pts"], "away_pts": a["pts"]})
    return pd.DataFrame(out).sort_values(["game_date", "game_id"]) if out else pd.DataFrame()


# ---------------------------------------------------------------------
# 向 NBA 要一場比賽的逐回合紀錄
# ---------------------------------------------------------------------
def download_pbp(game_id):
    from nba_api.stats.endpoints import playbyplayv3

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            return playbyplayv3.PlayByPlayV3(game_id=game_id, timeout=TIMEOUT).get_data_frames()[0]
        except Exception as e:
            wait = REQUEST_DELAY * attempt * 2
            print(f"    第 {attempt} 次失敗：{type(e).__name__}，{wait} 秒後重試")
            time.sleep(wait)
    return None


def clock_to_sec(s):
    """NBA 的時間格式 PT11M45.00S（這一節還剩 11 分 45 秒）→ 705 秒；也接受 11:45"""
    s = str(s or "")
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", s)
    if m and (m.group(1) or m.group(2)):
        return int(m.group(1) or 0) * 60 + float(m.group(2) or 0)
    m = re.match(r"(\d+):([\d.]+)", s)
    return int(m.group(1)) * 60 + float(m.group(2)) if m else None


def period_len(p):
    return 720 if p <= 4 else 300          # 一節 12 分鐘；延長賽 5 分鐘


def scoring_events(raw, game):
    """只留下「得分」的動作，自己從 0 開始累加比分（不依賴官方每列的比分欄位）"""
    df = raw.copy()
    df.columns = [c[0].lower() + c[1:] for c in df.columns]          # 統一成 camelCase
    at = df.get("actionType", pd.Series("", index=df.index)).astype(str).str.lower()
    res = df.get("shotResult", pd.Series("", index=df.index)).astype(str).str.lower()
    desc = df.get("description", pd.Series("", index=df.index)).astype(str)
    isfg = df.get("isFieldGoal", pd.Series(0, index=df.index)).astype(str)
    made_fg = at.eq("made shot") | (isfg.isin(["1", "True"]) & res.eq("made") & ~at.eq("free throw"))
    made_ft = at.eq("free throw") & (res.eq("made") | (~desc.str.upper().str.contains("MISS") & res.eq("")))
    df = df[made_fg | made_ft].copy()
    if df.empty:
        return df
    sv = pd.to_numeric(df.get("shotValue"), errors="coerce")
    df["points"] = 1
    fg = made_fg.loc[df.index]
    df.loc[fg, "points"] = sv[fg].where(sv[fg].isin([2, 3]), 2)
    df["action_type"] = df["points"].map({1: "FT", 2: "2PT", 3: "3PT"})
    df.loc[~fg, "action_type"] = "FT"
    df.loc[~fg, "points"] = 1
    df["period"] = pd.to_numeric(df["period"], errors="coerce").astype(int)
    df["clock_sec"] = df["clock"].map(clock_to_sec)
    before = df["period"].map(lambda p: sum(period_len(i) for i in range(1, p)))
    df["elapsed_sec"] = before + df["period"].map(period_len) - df["clock_sec"].fillna(0)
    df["actionNumber"] = pd.to_numeric(df["actionNumber"], errors="coerce").astype(int)
    df = df.sort_values(["period", "elapsed_sec", "actionNumber"]).reset_index(drop=True)
    tid = pd.to_numeric(df["teamId"], errors="coerce")
    df["side"] = tid.map({game["home_id"]: "H", game["away_id"]: "A"})
    if df["side"].isna().any() and "location" in df:                     # 備案：官方的 h / v 欄位
        df["side"] = df["side"].fillna(df["location"].astype(str).str.lower().map({"h": "H", "v": "A"}))
    df = df.dropna(subset=["side"])
    df["score_home"] = (df["points"] * (df["side"] == "H")).cumsum()
    df["score_away"] = (df["points"] * (df["side"] == "A")).cumsum()
    margin_before = (df["score_home"] - df["score_away"]) - df["points"] * df["side"].map({"H": 1, "A": -1})
    df["is_clutch"] = (df["period"] >= 4) & (df["clock_sec"] <= CLUTCH_SEC) & (margin_before.abs() <= CLUTCH_MARGIN)
    df["team_id"] = df["side"].map({"H": game["home_id"], "A": game["away_id"]})
    df["team_abbr"] = df["side"].map({"H": game["home_abbr"], "A": game["away_abbr"]})
    return df


def flow_summary(ev, game):
    """一場比賽的走勢摘要"""
    m = (ev["score_home"] - ev["score_away"]).tolist()
    changes, ties, last_sign = 0, 0, 0
    for v in m:
        s = (v > 0) - (v < 0)
        if s == 0:
            ties += 1
        elif last_sign and s != last_sign:
            changes += 1
        if s:
            last_sign = s
    # 最長連續得分（對手 0 分）
    best = (None, 0, None)
    cur_side, cur_pts, cur_period = None, 0, None
    for side, pts, per in zip(ev["side"], ev["points"], ev["period"]):
        if side == cur_side:
            cur_pts += pts
        else:
            cur_side, cur_pts, cur_period = side, pts, per
        if cur_pts > best[1]:
            best = (cur_side, cur_pts, cur_period)
    hp, ap = int(ev["score_home"].iloc[-1]), int(ev["score_away"].iloc[-1])
    home_won = hp > ap
    comeback = max(0, -min(m + [0])) if home_won else max(0, max(m + [0]))
    late = ev[(ev["period"] >= 4) & (ev["clock_sec"] <= CLUTCH_SEC)]
    per = ev.groupby(["period", "side"])["points"].sum().unstack(fill_value=0)
    abbr = {"H": game["home_abbr"], "A": game["away_abbr"]}
    official_ok = (pd.notna(game["home_pts"]) and int(game["home_pts"]) == hp
                   and pd.notna(game["away_pts"]) and int(game["away_pts"]) == ap)
    return {"game_id": game["game_id"], "season_type": game["season_type"], "game_date": game["game_date"],
            "home_abbr": game["home_abbr"], "away_abbr": game["away_abbr"], "home_pts": hp, "away_pts": ap,
            "lead_changes": changes, "times_tied": ties,
            "home_max_lead": max(0, max(m)), "away_max_lead": max(0, -min(m)),
            "comeback_team": abbr["H" if home_won else "A"], "comeback_pts": int(comeback),
            "best_run_team": abbr.get(best[0]), "best_run_pts": int(best[1]), "best_run_period": best[2],
            "clutch_game": bool(len(late) and late["is_clutch"].any()),
            "home_periods": ",".join(str(int(per.get("H", pd.Series()).get(p, 0))) for p in per.index),
            "away_periods": ",".join(str(int(per.get("A", pd.Series()).get(p, 0))) for p in per.index),
            "score_check": bool(official_ok)}


EVENT_COLS = ["game_id", "action_number", "season", "season_type", "game_date", "period", "clock_sec",
              "elapsed_sec", "team_id", "team_abbr", "player_id", "player_name", "action_type", "points",
              "score_home", "score_away", "is_clutch", "description"]


def load_games(client, season, games):
    ok, bad = 0, []
    for i, (_, g) in enumerate(games.iterrows(), 1):
        print(f"  [{i}/{len(games)}] {g['game_date']} {g['away_abbr']} @ {g['home_abbr']}（{g['game_id']}）")
        raw = download_pbp(g["game_id"])
        if raw is None or raw.empty:
            print("    抓不到逐回合紀錄（可能還沒打完或 NBA 擋連線），下次再試")
            bad.append(g["game_id"])
            continue
        ev = scoring_events(raw, g)
        if ev.empty:
            print("    沒有得分紀錄，略過")
            bad.append(g["game_id"])
            continue
        out = ev.rename(columns={"actionNumber": "action_number", "personId": "player_id",
                                 "playerName": "player_name"})
        out["game_id"], out["season"] = g["game_id"], season
        out["season_type"], out["game_date"] = g["season_type"], g["game_date"]
        for c in EVENT_COLS:
            if c not in out:
                out[c] = None
        out["player_id"] = pd.to_numeric(out["player_id"], errors="coerce").astype("Int64")
        out["clock_sec"] = out["clock_sec"].round(1)
        out["elapsed_sec"] = out["elapsed_sec"].round(1)
        out = out[EVENT_COLS].drop_duplicates(["game_id", "action_number"])
        summ = flow_summary(ev, g)
        summ["season"] = season
        if not summ["score_check"]:
            print(f"    注意：逐回合加總 {summ['away_pts']}–{summ['home_pts']}，和官方比分 "
                  f"{g['away_pts']}–{g['home_pts']} 不同，照樣存進去（網站會標示）")
        upsert(client, "pbp_events", out, "game_id,action_number")
        upsert(client, "pbp_game_flow", pd.DataFrame([summ]), "game_id")   # 最後才寫摘要：寫了就代表這場完成
        ok += 1
    return ok, bad


def main():
    parser = argparse.ArgumentParser(description="抓逐回合得分紀錄（每日戰報的比賽走勢、關鍵時刻、戰報稿）")
    parser.add_argument("--season", default=season_of(date.today()), help="球季，例如 2026-27（預設：這一季）")
    parser.add_argument("--days", type=int, default=3, help="補最近幾天還沒抓的比賽（預設 3）")
    parser.add_argument("--all", action="store_true", help="補這一季所有還沒抓的比賽")
    parser.add_argument("--game", help="只抓一場（測試用，會重抓）")
    parser.add_argument("--dry-run", action="store_true", help="只抓、只算，不寫進資料庫")
    args = parser.parse_args()

    client = connect()                                   # 要讀 recap_team_games，所以試跑也要連線
    print(f"===== 逐回合紀錄：{args.season} =====" + ("　【試跑模式】" if args.dry_run else ""))
    if args.game:
        tg = read_all(client, "recap_team_games", "game_id,team_id,season_type,game_date,abbreviation,is_home,pts",
                      [("eq", "game_id", args.game)])
        games = pair_games(tg)
    else:
        games = games_to_load(client, args.season, args.days, args.all)
    if games.empty:
        print("  沒有需要抓的比賽（都抓過了，或 recap_team_games 還沒有資料：先執行 python load_recap.py）")
        return
    print(f"  要抓 {len(games)} 場")
    ok, bad = load_games(None if args.dry_run else client, args.season, games)
    print(f"\n完成 {ok} 場" + (f"；{len(bad)} 場這次沒抓到，下次會自動再試" if bad else "") + "。")


if __name__ == "__main__":
    main()
