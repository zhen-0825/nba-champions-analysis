"""
本季數據的計算（奪冠列車、焦點人物、首頁本季故事共用）

只用 pandas，不用 Streamlit；網站 app.py 讀完資料庫後把表格丟進來，這裡負責算。
所有數字都來自資料庫裡每天更新的 recap_team_games、recap_player_games、pbp_events，
歷屆冠軍的標準來自 league_team_seasons 和 champions。
"""

import numpy as np
import pandas as pd

# 雷達圖的六個角：（名稱, 欄位, 數字越大越好?）
TEAM_AXES = [
    ("進攻", "off_rating", True),     # 每 100 回合得幾分
    ("防守", "def_rating", False),    # 每 100 回合讓對手得幾分（越低越好）
    ("三分", "fg3_pct", True),        # 三分命中率
    ("籃板", "reb_pct", True),        # 進攻籃板率與防守籃板率的平均
    ("助攻", "ast_ratio", True),      # 投進的球裡，有幾成是助攻來的
    ("失誤", "tov_pct", False),       # 每回合失誤比例（越低越好）
]
PLAYER_AXES = [
    ("進攻", "pts", True),            # 場均得分
    ("防守", "stocks", True),         # 場均抄截＋阻攻
    ("三分", "fg3m", True),           # 場均三分命中
    ("籃板", "reb", True),
    ("助攻", "ast", True),
    ("失誤", "tov", False),           # 場均失誤（越少越好）
]
NUM = ["pts", "fgm", "fga", "fg3m", "fg3a", "ftm", "fta", "oreb", "dreb", "reb", "ast", "stl", "blk",
       "tov", "pf", "plus_minus", "min"]


def _num(df, cols):
    d = df.copy()
    for c in cols:
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    return d


def percentile(s, higher_better=True):
    """聯盟百分等級 0～100：100＝這一項全聯盟最好，0＝最差（同分給一樣的分數）"""
    s = pd.to_numeric(s, errors="coerce")
    n = s.notna().sum()
    if n <= 1:
        return pd.Series(50.0, index=s.index)
    r = s.rank(ascending=higher_better, method="average")
    return (r - 1) / (n - 1) * 100


def rank_of(s, higher_better=True):
    """聯盟第幾名（1＝最好）"""
    return pd.to_numeric(s, errors="coerce").rank(ascending=not higher_better, method="min")


# ---------------------------------------------------------------------
# 球隊
# ---------------------------------------------------------------------
def team_table(tg):
    """本季每隊一列：戰績、攻守效率、六角數據與聯盟排名。tg＝recap_team_games（一場 × 一隊一列）"""
    if tg is None or tg.empty:
        return pd.DataFrame()
    d = _num(tg, NUM + ["opp_pts"])
    d = d[d["season_type"] == "Regular Season"] if "season_type" in d else d
    keep = ["game_id", "team_id", "fga", "fta", "oreb", "dreb", "tov"]
    opp = d[keep].rename(columns={c: f"o_{c}" for c in keep if c != "game_id"})
    m = d.merge(opp, on="game_id")
    m = m[m["team_id"] != m["o_team_id"]]
    m["win"] = (m["wl"] == "W").astype(int)
    cols = ["win", "pts", "opp_pts", "fgm", "fga", "fg3m", "fg3a", "fta", "oreb", "dreb", "ast", "tov",
            "o_fga", "o_fta", "o_oreb", "o_dreb", "o_tov"]
    t = m.groupby("abbreviation", as_index=False).agg(g=("game_id", "nunique"), **{c: (c, "sum") for c in cols})
    t["l"] = t["g"] - t["win"]
    poss = t["fga"] - t["oreb"] + t["tov"] + 0.44 * t["fta"]          # 回合數（常用估算公式）
    o_poss = t["o_fga"] - t["o_oreb"] + t["o_tov"] + 0.44 * t["o_fta"]
    t["off_rating"] = t["pts"] / poss * 100
    t["def_rating"] = t["opp_pts"] / o_poss * 100
    t["net_rating"] = t["off_rating"] - t["def_rating"]
    t["fg3_pct"] = t["fg3m"] / t["fg3a"].where(t["fg3a"] > 0)
    t["reb_pct"] = (t["oreb"] / (t["oreb"] + t["o_dreb"]) + t["dreb"] / (t["dreb"] + t["o_oreb"])) / 2
    t["ast_ratio"] = t["ast"] / t["fgm"].where(t["fgm"] > 0)
    t["tov_pct"] = t["tov"] / poss
    t["win_pct"] = t["win"] / t["g"]
    for name, col, hb in TEAM_AXES + [("淨效率", "net_rating", True)]:
        t[f"p_{col}"] = percentile(t[col], hb)
        t[f"rk_{col}"] = rank_of(t[col], hb)
    # 最近 10 場的淨勝分 vs 整季
    m = m.sort_values("game_date")
    m["margin"] = m["pts"] - m["opp_pts"]
    last = m.groupby("abbreviation").tail(10).groupby("abbreviation")["margin"].mean()
    t["margin"] = (t["pts"] - t["opp_pts"]) / t["g"]
    t["margin_l10"] = t["abbreviation"].map(last)
    t["trend"] = t["margin_l10"] - t["margin"]
    return t


def champion_profiles(league, champs):
    """歷屆冠軍在例行賽的六角百分等級（每季和當季 30 隊比）。回傳 (每位冠軍一列, 冠軍平均)"""
    if league is None or league.empty or champs is None or champs.empty:
        return pd.DataFrame(), pd.Series(dtype=float)
    lg = league[league["season_type"] == "Regular Season"].copy()
    for c in ["off_rating", "def_rating", "net_rating", "fg3m", "fg3a", "oreb_pct", "dreb_pct", "ast", "fgm",
              "tm_tov_pct"]:
        lg[c] = pd.to_numeric(lg[c], errors="coerce")
    lg["fg3_pct"] = lg["fg3m"] / lg["fg3a"].where(lg["fg3a"] > 0)
    lg["reb_pct"] = (lg["oreb_pct"] + lg["dreb_pct"]) / 2
    lg["ast_ratio"] = lg["ast"] / lg["fgm"].where(lg["fgm"] > 0)
    lg["tov_pct"] = lg["tm_tov_pct"]
    for _, col, hb in TEAM_AXES + [("淨效率", "net_rating", True)]:
        lg[f"p_{col}"] = lg.groupby("season")[col].transform(lambda s, hb=hb: percentile(s, hb))
        lg[f"rk_{col}"] = lg.groupby("season")[col].rank(ascending=not hb, method="min")
    ch = lg.merge(champs[["season", "team_id"]], on=["season", "team_id"])
    pcols = [f"p_{c}" for _, c, _ in TEAM_AXES]
    return ch, ch[pcols].mean()


def champion_index(t, champ_avg):
    """冠軍指數 0～100：六項裡，每一項只要不輸給「歷屆冠軍平均」就不扣分；輸多少扣多少，六項平均"""
    if t.empty or champ_avg.empty:
        return pd.Series(np.nan, index=t.index)
    short = pd.DataFrame({c: (champ_avg[f"p_{c}"] - t[f"p_{c}"]).clip(lower=0) for _, c, _ in TEAM_AXES})
    return (100 - short.mean(axis=1)).round(0)


def most_like(row, champs_p):
    """六角輪廓最接近哪一位冠軍（歐氏距離最小）。回傳 (球季, 球隊縮寫, 距離)"""
    if champs_p.empty:
        return None
    pcols = [f"p_{c}" for _, c, _ in TEAM_AXES]
    v = row[pcols].astype(float).values
    dist = np.sqrt(((champs_p[pcols].astype(float).values - v) ** 2).sum(axis=1))
    i = int(np.nanargmin(dist))
    r = champs_p.iloc[i]
    return r["season"], r.get("abbreviation", ""), float(dist[i])


# ---------------------------------------------------------------------
# 球員
# ---------------------------------------------------------------------
def player_table(pg, tg, min_games=None):
    """本季每位球員一列：傳統數據（場均）、進階數據、六角百分等級。pg＝recap_player_games"""
    if pg is None or pg.empty:
        return pd.DataFrame()
    d = _num(pg, NUM)
    d = d[d["season_type"] == "Regular Season"] if "season_type" in d else d
    d = d[d["min"] > 0]
    d = d.sort_values("game_date")
    g = d.groupby("player_id")
    p = g[NUM].sum()
    p["gp"] = g["game_id"].nunique()
    p["player_name"] = g["player_name"].last()
    p["abbreviation"] = g["abbreviation"].last()
    p["last_game"] = g["game_date"].max()
    # 使用率要用「他上場那幾場」的全隊數字
    if tg is not None and not tg.empty:
        tt = _num(tg, ["fga", "fta", "tov", "min"])[["game_id", "team_id", "fga", "fta", "tov", "min"]]
        tt = tt.rename(columns={"fga": "t_fga", "fta": "t_fta", "tov": "t_tov", "min": "t_min"})
        dd = d.merge(tt, on=["game_id", "team_id"], how="left")
        tsum = dd.groupby("player_id")[["t_fga", "t_fta", "t_tov", "t_min"]].sum()
        p = p.join(tsum)
    p = p.reset_index()
    gp = p["gp"]
    for c in NUM:
        p[f"{c}_g"] = p[c] / gp
    p["mpg"] = p["min"] / gp
    p["stocks"] = (p["stl"] + p["blk"]) / gp
    for c in ["pts", "reb", "ast", "tov", "fg3m"]:
        p[c + "_avg"] = p[f"{c}_g"]
    tsa = 2 * (p["fga"] + 0.44 * p["fta"])
    p["ts"] = p["pts"] / tsa.where(tsa > 0)
    p["efg"] = (p["fgm"] + 0.5 * p["fg3m"]) / p["fga"].where(p["fga"] > 0)
    p["fg_pct"] = p["fgm"] / p["fga"].where(p["fga"] > 0)
    p["fg3_pct"] = p["fg3m"] / p["fg3a"].where(p["fg3a"] > 0)
    p["ft_pct"] = p["ftm"] / p["fta"].where(p["fta"] > 0)
    p["tpar"] = p["fg3a"] / p["fga"].where(p["fga"] > 0)
    p["ftr"] = p["fta"] / p["fga"].where(p["fga"] > 0)
    p["ast_to"] = p["ast"] / p["tov"].where(p["tov"] > 0)
    for c in ["pts", "reb", "ast", "stl", "blk", "fg3m", "tov"]:
        p[f"{c}_36"] = p[c] / p["min"].where(p["min"] > 0) * 36
    if "t_fga" in p:
        den = p["min"] * (p["t_fga"] + 0.44 * p["t_fta"] + p["t_tov"])
        p["usg"] = (p["fga"] + 0.44 * p["fta"] + p["tov"]) * (p["t_min"] / 5) / den.where(den > 0)
    # 最近 5 場
    l5 = d.groupby("player_id").tail(5).groupby("player_id")[["pts", "reb", "ast", "min"]].mean()
    p = p.merge(l5.add_suffix("_l5"), left_on="player_id", right_index=True, how="left")
    # 夠格的球員才排名：出賽至少本季球隊場數的 40%（最少 5 場）、場均 15 分鐘以上
    team_g = d.groupby("abbreviation")["game_id"].nunique().max() if len(d) else 0
    need = min_games or max(5, int(round(team_g * 0.4)))
    p["qualified"] = (p["gp"] >= need) & (p["mpg"] >= 15)
    q = p["qualified"]
    for name, col, hb in PLAYER_AXES:
        src = p[col] if col == "stocks" else p[f"{col}_g"]
        p[f"p_{col}"] = np.nan
        p.loc[q, f"p_{col}"] = percentile(src[q], hb)
        p.loc[q, f"rk_{col}"] = rank_of(src[q], hb)
    return p


def player_games(pg, player_id):
    """某位球員本季每一場（畫最近走勢用）"""
    d = _num(pg[pg["player_id"] == player_id], NUM)
    return d[d["min"] > 0].sort_values("game_date")


def with_without(pg, tg, p, min_off=5):
    """有他 vs 沒他的球隊勝率：從他第一次上場之後算，他沒上場的球隊比賽＝缺陣
    min_off：至少缺陣幾場才列入（1127-2：由 3 場改成 5 場，3 場的勝率太靠運氣）"""
    if p.empty or tg is None or tg.empty:
        return pd.DataFrame()
    tgr = tg[tg["season_type"] == "Regular Season"] if "season_type" in tg else tg
    tgr = tgr[["game_id", "game_date", "abbreviation", "wl"]]
    played = pg[pd.to_numeric(pg["min"], errors="coerce") > 0][["game_id", "player_id"]]
    rows = []
    for r in p[p["qualified"] & (p["mpg"] >= 25)].itertuples():
        team = tgr[tgr["abbreviation"] == r.abbreviation]
        mine = set(played[played["player_id"] == r.player_id]["game_id"])
        first = team[team["game_id"].isin(mine)]["game_date"].min()
        team = team[team["game_date"] >= first]
        on = team[team["game_id"].isin(mine)]
        off = team[~team["game_id"].isin(mine)]
        if len(on) >= 5 and len(off) >= min_off:
            w_on, w_off = (on["wl"] == "W").mean(), (off["wl"] == "W").mean()
            rows.append({"player_id": r.player_id, "player_name": r.player_name, "abbreviation": r.abbreviation,
                         "g_on": len(on), "g_off": len(off), "w_on": w_on, "w_off": w_off, "drop": w_on - w_off})
    return pd.DataFrame(rows).sort_values("drop", ascending=False) if rows else pd.DataFrame()


def clutch_table(ev):
    """本季關鍵時刻（第四節或延長賽最後 5 分鐘、分差 5 分以內）每位球員的得分"""
    if ev is None or ev.empty:
        return pd.DataFrame()
    e = ev.copy()
    e["points"] = pd.to_numeric(e["points"], errors="coerce").fillna(0)
    out = e.groupby(["player_id", "player_name", "team_abbr"], as_index=False).agg(
        pts=("points", "sum"), games=("game_id", "nunique"))
    return out.sort_values("pts", ascending=False)


def hot_players(p, n=5):
    """爆發中：最近 5 場比本季平均多得幾分（夠格、最近 10 天有上場）"""
    if p.empty:
        return pd.DataFrame()
    q = p[p["qualified"]].copy()
    if q.empty:
        return q
    recent = q["last_game"] >= q["last_game"].max() - pd.Timedelta(days=10)
    q = q[recent]
    q["hot"] = q["pts_l5"] - q["pts_avg"]
    return q.sort_values("hot", ascending=False).head(n)


# ---------------------------------------------------------------------
# 本季故事（2026-11-24 起，每天一則；每一則都對照一頁冠軍故事）
# ---------------------------------------------------------------------
def bounce_table(tg):
    """輸球之後（11/24）：每隊輸球後下一場的勝率、比整季高多少（反彈）、最長連敗、目前連勝／連敗。
    對照冠軍故事「輸球之後」。只看例行賽。"""
    if tg is None or tg.empty:
        return pd.DataFrame()
    d = tg[tg["season_type"] == "Regular Season"] if "season_type" in tg else tg
    d = d.dropna(subset=["wl"]).sort_values(["abbreviation", "game_date", "game_id"])
    rows = []
    for abbr, x in d.groupby("abbreviation"):
        win = (x["wl"] == "W").astype(int).tolist()
        after = [w for prev, w in zip(win[:-1], win[1:]) if prev == 0]   # 上一場輸 → 這一場
        best = cur = 0
        for w in win:
            cur = 0 if w else cur + 1
            best = max(best, cur)
        run = 1
        while run < len(win) and win[-1 - run] == win[-1]:
            run += 1
        rows.append({"abbreviation": abbr, "g": len(win), "win_pct": float(np.mean(win)) if win else np.nan,
                     "n_after": len(after), "after_loss": float(np.mean(after)) if after else np.nan,
                     "max_losing": best, "streak": f"{run} 連{'勝' if win and win[-1] else '敗'}" if win else ""})
    out = pd.DataFrame(rows)
    out["bounce"] = (out["after_loss"] - out["win_pct"]) * 100      # 百分點
    return out


def schedule_load(sched, tg, days=7):
    """賽程來了（11/25）：未來 days 天每隊幾場、幾組背靠背、幾場客場。
    sched＝recap_schedule（一場一列）；tg 用來找每隊最後一場已打完的日期。對照冠軍故事「賽程與休息」。
    回傳 (每隊一列, 每隊每場一列)"""
    if sched is None or sched.empty or tg is None or tg.empty:
        return pd.DataFrame(), pd.DataFrame()
    s = sched.copy()
    s["game_date"] = pd.to_datetime(s["game_date"])
    start = pd.to_datetime(tg["game_date"]).max()
    end = start + pd.Timedelta(days=days)
    s = s[(s["game_date"] > start) & (s["game_date"] <= end)].drop_duplicates("game_id")
    if s.empty:
        return pd.DataFrame(), pd.DataFrame()
    home = pd.DataFrame({"abbreviation": s["home_abbr"], "game_date": s["game_date"], "is_home": True, "opp": s["away_abbr"]})
    away = pd.DataFrame({"abbreviation": s["away_abbr"], "game_date": s["game_date"], "is_home": False, "opp": s["home_abbr"]})
    g = pd.concat([home, away]).dropna(subset=["abbreviation"]).sort_values(["abbreviation", "game_date"])
    last = pd.to_datetime(tg["game_date"]).groupby(tg["abbreviation"]).max()
    g["prev"] = g.groupby("abbreviation")["game_date"].shift(1)
    g["prev"] = g["prev"].fillna(g["abbreviation"].map(last))
    g["b2b"] = (g["game_date"] - g["prev"]).dt.days == 1
    out = g.groupby("abbreviation").agg(games=("game_date", "size"), b2b=("b2b", "sum"),
                                        away=("is_home", lambda x: int((~x.astype(bool)).sum()))).reset_index()
    out = out.sort_values(["b2b", "games", "away"], ascending=False).reset_index(drop=True)
    return out, g.reset_index(drop=True)


def b2b_record(tg):
    """本季到目前：背靠背第二場 vs 有休息（休息 1 天以上）的勝率。回傳 (背靠背勝率, 場數, 有休息勝率, 場數)"""
    if tg is None or tg.empty:
        return None
    d = tg[tg["season_type"] == "Regular Season"] if "season_type" in tg else tg
    d = d.dropna(subset=["wl"]).sort_values(["abbreviation", "game_date"]).copy()
    d["rest"] = (d["game_date"] - d.groupby("abbreviation")["game_date"].shift(1)).dt.days - 1
    b, r = d[d["rest"] == 0], d[d["rest"] >= 1]
    if len(b) == 0 or len(r) == 0:
        return None
    return (b["wl"] == "W").mean(), len(b), (r["wl"] == "W").mean(), len(r)


def steady_scorers(pg, p, min_pts=18, min_gp=8):
    """穩定得分手（11/26）：夠格、場均 min_pts 分以上的主力，每場得分的起伏（標準差 ÷ 場均）與低迷場
    （不到自己場均六成）。對照冠軍故事「得分穩定度」。只看例行賽。"""
    if pg is None or pg.empty or p is None or p.empty:
        return pd.DataFrame()
    q = p[p["qualified"] & (p["pts_g"] >= min_pts) & (p["gp"] >= min_gp)]
    if q.empty:
        return pd.DataFrame()
    d = _num(pg, ["pts", "min"])
    d = d[d["season_type"] == "Regular Season"] if "season_type" in d else d
    d = d[(d["min"] > 0) & d["player_id"].isin(q["player_id"])]
    g = d.groupby("player_id")["pts"]
    out = pd.DataFrame({"sd": g.std(ddof=0), "ppg": g.mean(), "gp": g.size(), "lo": g.min(), "hi": g.max()})
    low = d.merge(out["ppg"], left_on="player_id", right_index=True)
    out["low_games"] = (low["pts"] < 0.6 * low["ppg"]).groupby(low["player_id"]).sum()
    out = out.join(q.set_index("player_id")[["player_name", "abbreviation"]]).reset_index()
    out["cv"] = out["sd"] / out["ppg"]
    out["rk_cv"] = out["cv"].rank(method="min")
    return out.sort_values("cv").reset_index(drop=True)


def champ_top_scorer_cv(spread, champs, min_gp=40):
    """歷屆冠軍頭號得分手（例行賽場均最高、出賽 40 場以上）的得分起伏中位數。spread＝player_scoring_spread_mv"""
    if spread is None or spread.empty or champs is None or champs.empty:
        return None
    s = _num(spread, ["gp", "ppg", "sd_pts"])
    s = s[(s["season_type"] == "Regular Season") & (s["gp"] >= min_gp) & (s["ppg"] > 0)]
    s = s.merge(champs[["season", "team_id"]], on=["season", "team_id"])
    if s.empty:
        return None
    top = s.sort_values("ppg", ascending=False).drop_duplicates(["season", "team_id"])
    return {"champ": float((top["sd_pts"] / top["ppg"]).median()), "n": len(top)}


def second_stars(pg, p, t=None):
    """第二主角（11/27）：每隊本季場均得分第 2 名（夠格球員），他的得分佔全隊幾 %、是頭號得分手的幾成。
    對照冠軍故事「二號與三號得分手」。只看例行賽、夠格球員（出賽至少本季場數 4 成、場均 15 分鐘以上）。
    t＝team_table 的結果（有的話接上冠軍指數 champ_idx，依列車順序排）。"""
    if pg is None or pg.empty or p is None or p.empty:
        return pd.DataFrame()
    d = _num(pg, ["pts", "min"])
    d = d[d["season_type"] == "Regular Season"] if "season_type" in d else d
    team_pts = d.groupby("abbreviation")["pts"].sum()                   # 全隊本季總得分
    q = p[p["qualified"]].copy()
    # 季中被交易的球員：player_table 只記最後一隊；他在這隊的得分要用「替這隊打的比賽」算
    own = d[d["min"] > 0].groupby(["player_id", "abbreviation"])["pts"].sum().rename("pts_team")
    q = q.merge(own, left_on=["player_id", "abbreviation"], right_index=True, how="left")
    q["rk_team"] = q.groupby("abbreviation")["pts_g"].rank(ascending=False, method="first")
    one = q[q["rk_team"] == 1].set_index("abbreviation")
    two = q[q["rk_team"] == 2].set_index("abbreviation")
    if two.empty:
        return pd.DataFrame()
    out = pd.DataFrame({
        "abbreviation": two.index,
        "player_name": two["player_name"].values, "player_id": two["player_id"].values,
        "ppg": two["pts_g"].values, "gp": two["gp"].values,
        "share": (two["pts_team"] / two.index.map(team_pts)).values,      # 得分佔全隊比例
        "star_name": two.index.map(one["player_name"]), "star_ppg": two.index.map(one["pts_g"]),
    })
    out["star_share"] = out["abbreviation"].map(one["pts_team"]) / out["abbreviation"].map(team_pts)
    out["ratio"] = out["ppg"] / out["star_ppg"]                            # 是頭號得分手的幾成
    out["rk_share"] = out["share"].rank(ascending=False, method="min")     # 30 位二號得分手裡第幾
    if t is not None and not t.empty and "champ_idx" in t:
        out = out.merge(t[["abbreviation", "champ_idx", "win", "l"]], on="abbreviation", how="left")
        out = out.sort_values("champ_idx", ascending=False)
    return out.reset_index(drop=True)


def champ_second_share(sup, champs):
    """歷屆冠軍的二號得分手：例行賽得分佔全隊比例、場均、是頭號的幾成（中位數）。
    sup＝support_round_mv（一隊一季一輪一位得分手一列；例行賽數字每一輪都一樣，所以先去重）"""
    if sup is None or sup.empty or champs is None or champs.empty:
        return None
    s = _num(sup, ["scorer_rk", "reg_g", "reg_pts", "team_reg_pts"])
    s = s.merge(champs[["season", "team_id"]], on=["season", "team_id"])
    s = s.drop_duplicates(["season", "team_id", "scorer_rk"])
    s["ppg"] = s["reg_pts"] / s["reg_g"].where(s["reg_g"] > 0)
    s["share"] = s["reg_pts"] / s["team_reg_pts"].where(s["team_reg_pts"] > 0)
    one = s[s["scorer_rk"] == 1].set_index(["season", "team_id"])
    two = s[s["scorer_rk"] == 2].set_index(["season", "team_id"])
    two = two.join(one[["ppg"]].rename(columns={"ppg": "star_ppg"}), how="inner")
    if two.empty:
        return None
    ratio = two["ppg"] / two["star_ppg"]
    return {"share": float(two["share"].median()), "ppg": float(two["ppg"].median()),
            "ratio": float(ratio.median()), "n": len(two),
            "share_lo": float(two["share"].min()), "share_hi": float(two["share"].max())}


def team_scorers(pg, tg, abbr):
    """球隊關鍵人物（11/27 使用者要求）：一支球隊本季每位球員一列——得分佔全隊幾 %、當過幾場全隊得分王、
    其中幾場球隊贏球。看這隊是「很多人都能跳出來」還是「一人球隊」。只看例行賽。
    回傳 (每位球員一列, 球隊摘要 dict)"""
    if pg is None or pg.empty or tg is None or tg.empty:
        return pd.DataFrame(), {}
    d = _num(pg, ["pts", "min"])
    d = d[(d["abbreviation"] == abbr) & (d["min"] > 0)]
    d = d[d["season_type"] == "Regular Season"] if "season_type" in d else d
    if d.empty:
        return pd.DataFrame(), {}
    wl = tg[tg["abbreviation"] == abbr].drop_duplicates("game_id").set_index("game_id")["wl"]
    d = d.assign(win=d["game_id"].map(wl).eq("W"))
    # 全隊得分王：那一場得分最多的人（同分就都算）
    d["lead"] = d["pts"] == d.groupby("game_id")["pts"].transform("max")
    g = d.groupby("player_id")
    out = pd.DataFrame({"player_name": g["player_name"].last(), "gp": g["game_id"].nunique(),
                        "pts": g["pts"].sum(), "ppg": g["pts"].mean(),
                        "lead_g": g["lead"].sum(), "lead_w": d[d["lead"] & d["win"]].groupby("player_id").size()})
    out["lead_w"] = out["lead_w"].fillna(0)
    out["share"] = out["pts"] / out["pts"].sum()
    out = out.sort_values("pts", ascending=False).reset_index()
    n_games = d["game_id"].nunique()
    top = out.iloc[0]
    summary = {
        "games": n_games, "wins": int(wl.eq("W").sum()),
        "top_name": top["player_name"], "top_share": float(top["share"]),
        "eff_n": float(1 / (out["share"] ** 2).sum()),                        # 有效得分人數：等於幾個人平分
        "n_leaders": int((out["lead_g"] >= 1).sum()),                          # 當過全隊得分王的人數
        "n_leaders2": int((out["lead_g"] >= 2).sum()),
        "not_top_lead": float(1 - top["lead_g"] / n_games) if n_games else np.nan,   # 頭號以外的人當得分王的比例
    }
    return out, summary


def league_scorer_spread(pg):
    """全聯盟 30 隊的頭號得分佔比、有效得分人數（給「聯盟第幾」用）。只看例行賽"""
    if pg is None or pg.empty:
        return pd.DataFrame()
    d = _num(pg, ["pts", "min"])
    d = d[d["season_type"] == "Regular Season"] if "season_type" in d else d
    d = d[d["min"] > 0]
    pp = d.groupby(["abbreviation", "player_id"])["pts"].sum()
    sh = pp / pp.groupby(level=0).transform("sum")
    out = pd.DataFrame({"top_share": sh.groupby(level=0).max(), "eff_n": 1 / (sh ** 2).groupby(level=0).sum()})
    out["rk_top"] = out["top_share"].rank(ascending=False, method="min")     # 1＝最依賴頭號
    out["rk_eff"] = out["eff_n"].rank(ascending=False, method="min")         # 1＝得分最分散
    return out.reset_index()


def champ_scorer_spread(player_seasons, champs):
    """歷屆冠軍（例行賽）的頭號得分佔比、有效得分人數，和冠軍故事「陣容深度」同一個定義。
    player_seasons＝player_season_stats（一位球員一隊一季一種比賽一列）"""
    if player_seasons is None or player_seasons.empty or champs is None or champs.empty:
        return pd.DataFrame()
    p = _num(player_seasons, ["pts"])
    p = p[p["season_type"] == "Regular Season"].merge(champs[["season", "team_id"]], on=["season", "team_id"])
    if p.empty:
        return pd.DataFrame()
    tot = p.groupby(["season", "team_id"])["pts"].transform("sum")
    p = p.assign(share=p["pts"] / tot.where(tot > 0))
    g = p.sort_values("share", ascending=False).groupby(["season", "team_id"])
    out = g.agg(abbreviation=("abbreviation", "first"), top_name=("player_name", "first"),
                top_share=("share", "max"), eff_n=("share", lambda s: 1 / (s ** 2).sum())).reset_index()
    return out.sort_values("top_share", ascending=False).reset_index(drop=True)
