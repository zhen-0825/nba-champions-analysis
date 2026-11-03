"""
比賽預測的計算（網站 app.py 和每天存預測的 save_predictions.py 共用同一套算法）

只用 pandas，不用 Streamlit，所以排程程式也能 import。
"""

import math

import pandas as pd

HOME_EDGE = 2.5      # 主場優勢：NBA 主隊平均多贏約 2～3 分
B2B_PENALTY = 1.5    # 背靠背（前一天才打過）少約 1.5 分
STAR_PENALTY = 2.0   # 主力上一場沒上場，若持續缺陣少約 2 分
GAME_SD = 12.0       # NBA 一場比賽的分差，和預測相比大約會差 ±12 分（標準差）
SHRINK = 8           # 開季場數少，數字不穩：打 n 場只相信 n/(n+8)，其餘拉回聯盟平均


def win_prob(margin):
    """預測分差 → 勝率：假設實際分差＝預測分差＋常態分布的誤差（標準差 12 分）"""
    return 0.5 * (1 + math.erf(margin / (GAME_SD * math.sqrt(2))))


def team_ratings(games):
    """每隊到目前為止的平均：淨勝分、得分、失分；場數少的往聯盟平均拉"""
    reg = games[games["season_type"] == "Regular Season"]
    if reg.empty:
        return {}, 112.0
    lg = float(reg["pts"].mean())
    out = {}
    for abbr, g in reg.groupby("abbreviation"):
        n = len(g)
        w = n / (n + SHRINK)
        out[abbr] = {"n": n, "pm": w * g["plus_minus"].mean(),
                     "off": w * g["pts"].mean() + (1 - w) * lg,
                     "def": w * g["opp_pts"].mean() + (1 - w) * lg,
                     "last": g["game_date"].max()}
    return out, lg


def predict_game(home, away, game_day, ratings, lg, missing=None):
    """一場比賽的預測：回傳主隊勝率、預測比分、影響因素（每個因素都寫出加減幾分）"""
    missing = missing or {}
    h, a = ratings.get(home), ratings.get(away)
    if not h or not a:
        return None
    margin = h["pm"] - a["pm"] + HOME_EDGE
    factors = [f"實力：{home} 場均淨勝 {h['pm']:+.1f}、{away} {a['pm']:+.1f}", f"{home} 主場 +{HOME_EDGE}"]
    for abbr, r, sign in [(home, h, -1), (away, a, 1)]:
        if (game_day - r["last"]).days == 1:
            margin += sign * B2B_PENALTY
            factors.append(f"{abbr} 背靠背 −{B2B_PENALTY}")
        if abbr in missing:
            margin += sign * STAR_PENALTY
            factors.append(f"{abbr} {missing[abbr]} 上一場缺陣 −{STAR_PENALTY:g}")
    home_pts = (h["off"] + a["def"]) / 2
    away_pts = (a["off"] + h["def"]) / 2
    mid = (home_pts + away_pts) / 2
    return {"p_home": win_prob(margin), "margin": margin,
            "home_pts": mid + margin / 2, "away_pts": mid - margin / 2, "factors": factors}


def project_players(team, opp, pl, sa, ratings, lg, n=3):
    """球員下一場預估：近 10 場佔 6 成、本季平均佔 4 成；得分再依對手防守（平常失幾分）微調"""
    if pl.empty or sa.empty:
        return []
    season = sa[(sa["abbreviation"] == team) & (sa["gp"] >= 2)]
    opp_r = ratings.get(opp)
    factor = 1.0
    if opp_r:
        factor = max(0.92, min(1.08, opp_r["def"] / lg))
    team_games = pl[pl["abbreviation"] == team]["game_id"].unique()
    last_game = pl[pl["abbreviation"] == team].sort_values("game_date")["game_id"].iloc[-1] if len(team_games) else None
    out = []
    for r in season.itertuples():
        rec = pl[(pl["player_id"] == r.player_id) & (pl["abbreviation"] == team)].sort_values("game_date").tail(10)
        if rec.empty:
            continue
        gp = r.gp
        proj = {}
        for k in ["pts", "reb", "ast"]:
            proj[k] = 0.6 * rec[k].mean() + 0.4 * getattr(r, k) / gp
        proj["pts"] *= factor
        sd = rec["pts"].std()
        spread = max(3.0, float(sd)) if len(rec) >= 3 and pd.notna(sd) else 6.0
        out.append({"player_id": int(r.player_id), "name": r.player_name, "pts": proj["pts"], "reb": proj["reb"], "ast": proj["ast"],
                    "lo": max(0, proj["pts"] - spread), "hi": proj["pts"] + spread,
                    "out": last_game is not None and not ((pl["game_id"] == last_game) & (pl["player_id"] == r.player_id)).any()})
    return sorted(out, key=lambda x: -x["pts"])[:n]


def missing_stars(pl, sa):
    """每隊本季上場時間最多的球員，如果上一場沒有上場，記下來（預測時扣分）"""
    out = {}
    if pl.empty or sa.empty:
        return out
    for abbr, g in pl.groupby("abbreviation"):
        s_ = sa[(sa["abbreviation"] == abbr) & (sa["gp"] >= 2)].copy()
        if s_.empty:
            continue
        s_["mpg"] = s_["min"] / s_["gp"]
        star = s_.sort_values("mpg").iloc[-1]
        last = g.sort_values("game_date")["game_id"].iloc[-1]
        if not ((g["game_id"] == last) & (g["player_id"] == star.player_id)).any():
            out[abbr] = star.player_name
    return out


def season_avg(pl):
    """球員本季累計（和資料庫的 recap_player_season 檢視表一樣）；回推過去某天時，只用那天以前的比賽"""
    reg = pl[pl["season_type"] == "Regular Season"]
    if reg.empty:
        return pd.DataFrame(columns=["player_id", "team_id", "player_name", "abbreviation", "gp", "min", "pts", "reb", "ast"])
    return (reg.groupby(["player_id", "team_id"])
               .agg(player_name=("player_name", "max"), abbreviation=("abbreviation", "max"), gp=("game_id", "count"),
                    min=("min", "sum"), pts=("pts", "sum"), reb=("reb", "sum"), ast=("ast", "sum"))
               .reset_index())


def predict_day(tg, pl, sa, day, games, n_players=2):
    """某一個比賽日的全部預測（只用 tg、pl 裡「這天以前」的資料）
    回傳兩張表：每場比賽一筆、每位被預測的球員一筆"""
    day = pd.Timestamp(day)
    before = tg[tg["game_date"] < day]
    pl_b = pl[pl["game_date"] < day] if not pl.empty else pl
    ratings, lg = team_ratings(before)
    missing = missing_stars(pl_b, sa)
    g_rows, p_rows = [], []
    for g in games.itertuples():
        p = predict_game(g.home_abbr, g.away_abbr, day, ratings, lg, missing)
        if p is None:
            continue
        g_rows.append({"game_id": g.game_id, "game_date": day.strftime("%Y-%m-%d"),
                       "home_abbr": g.home_abbr, "away_abbr": g.away_abbr,
                       "p_home": round(p["p_home"], 4), "margin": round(p["margin"], 2),
                       "home_pts": round(p["home_pts"], 1), "away_pts": round(p["away_pts"], 1),
                       "factors": "・".join(p["factors"])})
        for abbr, opp in [(g.away_abbr, g.home_abbr), (g.home_abbr, g.away_abbr)]:
            for r in project_players(abbr, opp, pl_b, sa, ratings, lg, n=n_players):
                p_rows.append({"game_id": g.game_id, "player_id": r["player_id"], "game_date": day.strftime("%Y-%m-%d"),
                               "player_name": r["name"], "abbreviation": abbr, "opp_abbr": opp,
                               "pts": round(r["pts"], 1), "reb": round(r["reb"], 1), "ast": round(r["ast"], 1),
                               "pts_lo": round(r["lo"], 1), "pts_hi": round(r["hi"], 1), "was_out": bool(r["out"])})
    return pd.DataFrame(g_rows), pd.DataFrame(p_rows)
