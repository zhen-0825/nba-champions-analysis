# -*- coding: utf-8 -*-
"""
patch_2026-11-17.py　把「誰補上得分」頁加進你電腦裡的 app.py

用法（在 VS Code 終端機，提示字元 (basketball) PS C:\basketball_research> 不用複製）：
    python patch_2026-11-17.py

會做的事：
  1. 先把 app.py 備份成 app_備份_2026-11-17.py
  2. 在左側選單「冠軍故事」最後面加一頁「誰補上得分」
  3. 加上這頁的程式、名詞小辭典、相關頁面、資料來源與方法
不論有沒有跑過 11/06～11/16 的補丁都可以用；已經加過就不會重複加。
這頁要先在 Supabase 執行 docs/sql/2026-11-17_誰補上得分.sql（沒執行時頁面只會顯示提示，不會壞）。
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")
BACKUP = os.path.join(HERE, "app_備份_2026-11-17.py")
NAME = "誰補上得分"

PAGE_ENTRY = (
    '    ("冠軍故事", "誰補上得分", "少了頭號得分手，誰補上得分？",\n'
    '     "頭號得分手缺陣時，第 2 號、第 3 號得分手和其他隊友每場多得幾分、補回幾成；冠軍和其他強隊比。", set()),\n'
)
TERMS_ADD = (
    '    "頭號得分手（本頁）": ("這一季在這隊例行賽場均得分最高、至少上場 20 場的球員（和「頭號得分手缺陣」頁同一個人）", "依例行賽場均得分排名"),\n'
    '    "缺陣（本頁）": ("球隊有打這一場，但他沒有出賽紀錄或上場 0 分鐘；不知道是受傷、休息還是禁賽", "季中被交易的球員只算他在隊期間"),\n'
    '    "補回比例": ("缺陣時隊友每場多得的分數，佔他平常場均得分的幾 %；100% ＝全部補回來", "隊友多得的分數 ÷ 他有上場時的場均"),\n'
    '    "第 2 號、第 3 號得分手": ("扣掉頭號得分手，隊上場均得分第 1、第 2 高的人（至少出賽 10 場）", "用他有上場的那些比賽排名"),\n'
)
RELATED_ADD = (
    '    "誰補上得分": [("頭號得分手缺陣", "少了他之後勝率掉多少"), ("缺陣場的對手", "缺陣的那幾場，對手是不是比較弱"),\n'
    '              ("陣容深度", "平常的得分就分散在幾個人身上")],\n'
)
SOURCES_ADD = (
    '    "誰補上得分": ("star_fill_mv（預先算好的彙總表，docs/sql/2026-11-17_誰補上得分.sql，由 player_game_stats、team_games、games 算）、"\n'
    '              "league_team_seasons（整季勝率，分出其他強隊）、champions", "2006-07 起、30 隊；只看例行賽；本季不列入",\n'
    '              "頭號得分手＝例行賽場均得分隊內最高、至少上場 20 場；缺陣＝球隊有打、他沒有上場；隊友每場得分＝那一類比賽隊友一共得幾分 ÷ 球隊場數；"\n'
    '              "補回比例＝（缺陣時 − 有他時）÷ 他有上場時的場均；各組依缺陣場數加權合計。不知道缺陣原因，也沒有扣掉對手強弱。"),\n'
)
BLOCK = '''

# ---------- 誰補上得分：頭號得分手缺陣時，得分由誰補上？（2026-11-17）----------
FILL_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
FILL_PARTS = [("第 2 號得分手", ACCENT), ("第 3 號得分手", "#a78bfa"), ("其他隊友", "#c9c3d6")]
FILL_NUM = ["team_id", "player_id", "star_id", "team_g_with", "team_w_with", "team_g_without", "team_w_without",
            "g_with", "min_with", "pts_with", "fga_with", "fta_with",
            "g_without", "min_without", "pts_without", "fga_without", "fta_without"]


@st.cache_data(ttl=3600, show_spinner="讀取「缺陣時誰補上得分」彙總表中…")
def _read_fill():
    """讀 star_fill_mv（一隊一季一位球員一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("star_fill_mv", ["season", "team_id", "player_id"])


def load_fill():
    try:
        df = _read_fill()
        return df if not df.empty else None
    except Exception as e:
        VIEW_ERRORS["star_fill_mv"] = f"{type(e).__name__}: {e}"[:300]
        return None


def _fill_pos(s):
    """分母是 0 時變成空值，不除以 0"""
    return s.where(s > 0)


def _fill_ts(pts, fga, fta):
    return pts / _fill_pos(2 * (fga + 0.44 * fta))


def prep_fill(df, league_tbl, strong=0.6):
    """一隊一季一列：頭號得分手有上場 vs 缺陣時，第 2 號、第 3 號得分手和其他隊友「每場」多得幾分。
    隊友的每場都用「球隊打了幾場」當分母（他那場沒上場就算 0 分），三段加起來剛好＝全部隊友多得的分數。"""
    d = df.copy()
    for c in FILL_NUM:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    d["is_star"] = d["is_star"].astype(str).str.lower().isin(["true", "t", "1"])
    keys = ["season", "team_id"]
    mates = d[~d["is_star"]].copy()
    # 隊內得分排名（不含頭號得分手）：用「他有上場的那些比賽」裡的場均得分，至少出賽 10 場才排得上前面
    mates["ppg_on"] = mates["pts_with"] / _fill_pos(mates["g_with"])
    mates["rk_key"] = mates["ppg_on"].where(mates["g_with"] >= 10, -1).fillna(-1)
    mates["rk"] = mates.groupby(keys)["rk_key"].rank(ascending=False, method="first")
    mates["part"] = mates["rk"].map(lambda r: "第 2 號得分手" if r == 1 else ("第 3 號得分手" if r == 2 else "其他隊友"))

    t = d.groupby(keys).agg(abbreviation=("abbreviation", "first"), star_name=("star_name", "first"),
                            gw=("team_g_with", "first"), ww=("team_w_with", "first"),
                            go=("team_g_without", "first"), wo=("team_w_without", "first"))
    star = d[d["is_star"]].groupby(keys)["pts_with"].sum().reindex(t.index).fillna(0)
    t["star_on"] = star / _fill_pos(t["gw"])
    sums = ["pts_with", "pts_without", "fga_with", "fga_without", "fta_with", "fta_without"]
    for part, _ in FILL_PARTS:
        m = mates[mates["part"] == part].groupby(keys)[sums].sum().reindex(t.index).fillna(0)
        t[f"{part}_gain"] = m["pts_without"] / _fill_pos(t["go"]) - m["pts_with"] / _fill_pos(t["gw"])
    a = mates.groupby(keys)[sums].sum().reindex(t.index).fillna(0)
    t["mate_on"] = a["pts_with"] / _fill_pos(t["gw"])
    t["mate_off"] = a["pts_without"] / _fill_pos(t["go"])
    t["gain"] = t["mate_off"] - t["mate_on"]
    t["fga_on"] = a["fga_with"] / _fill_pos(t["gw"])
    t["fga_off"] = a["fga_without"] / _fill_pos(t["go"])
    t["ts_on"] = _fill_ts(a["pts_with"], a["fga_with"], a["fta_with"])
    t["ts_off"] = _fill_ts(a["pts_without"], a["fga_without"], a["fta_without"])
    t["fill"] = t["gain"] / _fill_pos(t["star_on"])
    second = mates[mates["rk"] == 1].groupby(keys)["player_name"].first()
    t["second_name"] = second.reindex(t.index)
    t = t.reset_index()
    # 整季勝率（分出「其他強隊」）：用全聯盟每季數據
    lg = league_tbl[league_tbl["season_type"] == "Regular Season"][["season", "team_id", "w", "gp"]].copy() \\
        if not league_tbl.empty else pd.DataFrame(columns=["season", "team_id", "w", "gp"])
    for c in ["team_id", "w", "gp"]:
        lg[c] = pd.to_numeric(lg[c], errors="coerce")
    lg["season_win"] = lg["w"] / _fill_pos(lg["gp"])
    t = t.merge(lg[["season", "team_id", "season_win"]], on=["season", "team_id"], how="left")
    t["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(t["season"], t["abbreviation"])]
    t["grp"] = "其他球隊"
    t.loc[(~t["champion"]) & (t["season_win"] >= strong), "grp"] = "其他強隊"
    t.loc[t["champion"], "grp"] = "冠軍"
    return t[t["season"] != ALL_SEASONS[-1]]      # 本季還沒打完，先不列入


def pool_fill(t):
    """各組合計：每一隊依「缺陣場數」加權（缺陣 1 場的隊不會和缺陣 20 場的隊一樣重）"""
    rows = []
    for grp in FILL_GROUPS:
        s = t[(t["grp"] == grp) & (t["go"] > 0)].dropna(subset=["gain", "star_on"])
        w = s["go"]
        W = w.sum()
        if W == 0:
            continue
        r = {"grp": grp, "n_team": len(s), "games": int(W), "star": (s["star_on"] * w).sum() / W,
             "gain": (s["gain"] * w).sum() / W,
             "fga_d": ((s["fga_off"] - s["fga_on"]) * w).sum() / W}
        for part, _ in FILL_PARTS:
            r[part] = (s[f"{part}_gain"].fillna(0) * w).sum() / W
        ok = s.dropna(subset=["ts_on", "ts_off"])
        r["ts_d"] = ((ok["ts_off"] - ok["ts_on"]) * ok["go"]).sum() / ok["go"].sum() * 100 if ok["go"].sum() else float("nan")
        r["win_on"] = s["ww"].sum() / s["gw"].sum() if s["gw"].sum() else float("nan")
        r["win_off"] = s["wo"].sum() / W
        r["fill"] = r["gain"] / r["star"] if r["star"] else float("nan")
        rows.append(r)
    return pd.DataFrame(rows)


if PAGE == "誰補上得分":
    hypothesis("頭號得分手缺陣時，誰補上他的得分？是第 2 號球星一肩扛起，還是大家一起多得一點？",
               "隊友能補回他平常得分的一半以上；補上的分數分散在很多人身上（第 2 號得分手補的不到總補回的四成）；"
               "冠軍的隊友補得比其他強隊（整季勝率六成以上、沒奪冠）多（補回比例高 5 個百分點以上）。")
    FD = load_fill()
    if FD is None:
        st.info("尚未載入資料，請先在 Supabase 的 SQL Editor 執行 docs/sql/2026-11-17_誰補上得分.sql"
                "（建立 star_fill_mv 彙總表），再按左側「重新讀取最新資料」。")
        if "star_fill_mv" in VIEW_ERRORS:
            st.caption(f"讀取 star_fill_mv 的錯誤訊息（截圖給助教看）：{VIEW_ERRORS['star_fill_mv']}")
    else:
        FT = prep_fill(FD, league)
        P = pool_fill(FT)
        st.caption(f"用 {FT['abbreviation'].nunique()} 隊、{FT['season'].nunique()} 季例行賽計算；"
                   "頭號得分手＝這一季在這隊場均得分最高、至少上場 20 場的球員；缺陣＝球隊有打、他沒有上場（不知道原因）。本季還沒打完，先不列入。")
        if P.empty:
            st.info("資料庫裡還沒有「頭號得分手缺陣」的比賽可以比較。")
        else:
            # ===== 1 各組：補回幾成？誰補的？ =====
            slot1 = section("1　少了他，隊友補回幾成？",
                            "長條＝隊友每場多得的分數，佔他平常場均得分的幾 %；三段由左到右是第 2 號得分手、第 3 號、其他隊友；"
                            "虛線 100%＝把他的分數全部補回來。各組依缺陣場數加權合計。")
            P = P.set_index("grp").reindex([g for g in FILL_GROUPS if g in set(P["grp"])])
            labels = [f"{g}（{int(r['n_team'])} 隊季、缺陣 {int(r['games'])} 場）" for g, r in P.iterrows()]
            fig = go.Figure()
            for part, colr in FILL_PARTS:
                share = P[part] / P["star"]
                fig.add_trace(go.Bar(y=labels, x=share, name=part, orientation="h", marker_color=colr,
                                     customdata=P[part],
                                     hovertemplate=part + "：每場多得 %{customdata:+.1f} 分（補回 %{x:.0%}）<extra></extra>"))
            fig.add_trace(go.Scatter(y=labels, x=P["fill"].clip(lower=0), mode="text", showlegend=False, hoverinfo="skip",
                                     text=[f"  合計 {f:.0%}（{g:+.1f} 分／他平常 {s:.1f} 分）"
                                           for f, g, s in zip(P["fill"], P["gain"], P["star"])],
                                     textposition="middle right", textfont=dict(size=11.5, color=INK_2)))
            fig.add_vline(x=1, line_dash="dash", line_color="#b3adc2")
            fig.add_vline(x=0.5, line_dash="dot", line_color="#d9d3e6")
            fig.update_layout(barmode="relative", legend=dict(orientation="h", y=1.12, x=0))
            fig.update_xaxes(title="補回他平常得分的幾 %", tickformat=".0%", range=[min(0, float((P["fill"]).min()) - 0.05), 1.6])
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            rounded(fig)
            st.plotly_chart(style(fig, 120 + 62 * len(P)), width="stretch", config={"displayModeBar": False})

            lines, chk = [], None
            if "冠軍" in P.index:
                c_ = P.loc["冠軍"]
                sec = c_["第 2 號得分手"] / c_["gain"] if c_["gain"] > 0 else float("nan")
                lines.append(f"<b>頭號得分手缺陣時，冠軍的隊友補回他 {c_['fill']:.0%}：</b>每場多得 {c_['gain']:+.1f} 分"
                             f"（他平常場均 {c_['star']:.1f} 分），其中第 2 號得分手多得 {c_['第 2 號得分手']:+.1f} 分。")
                others = [f"{g} {P.loc[g, 'fill']:.0%}" for g in ["其他強隊", "其他球隊"] if g in P.index]
                if others:
                    lines.append("其他組補回：" + "、".join(others) + "。")
                if c_["games"] < 60:
                    lines.append(f"冠軍的頭號得分手合計只缺陣 {int(c_['games'])} 場，數字起伏會比較大。")
                front = ("前段成立" if c_["fill"] >= 0.5 else "前段不成立") + f"：冠軍補回 {c_['fill']:.0%}（門檻五成）"
                mid = ("中段不成立：第 2 號得分手沒有多得分" if not (sec == sec) else
                       ("中段成立" if sec < 0.4 else "中段不成立") + f"：第 2 號得分手佔總補回的 {sec:.0%}（門檻四成）")
                if "其他強隊" in P.index:
                    gap = (c_["fill"] - P.loc["其他強隊", "fill"]) * 100
                    back = ("後段成立" if gap >= 5 else "後段不成立：冠軍和其他強隊差不多（差不到 5 個百分點）" if gap > -5
                            else "後段不成立：冠軍補得比其他強隊少") + f"（冠軍 − 其他強隊 {gap:+.0f} 個百分點）"
                else:
                    back = "後段無法比較：還沒有其他強隊的資料"
                chk = f"{front}；{mid}；{back}。"
            else:
                lines.append("資料庫裡的冠軍球季還沒有頭號得分手缺陣的比賽。")
            lines.append("讀法：先看冠軍那一列的合計有沒有超過 50% 的點線（前段假設）；再看紫色那一段（第 2 號得分手）"
                         "佔整條的多少（中段）；最後比冠軍和其他強隊兩列誰比較長（後段）。"
                         "隊友多得的分數，是用「球隊每一場」平均（他那場沒上場就算 0 分），所以三段加起來就是全部隊友多得的分數。"
                         "缺陣的比賽可能剛好打弱隊（見「缺陣場的對手」頁），補回比例可能被高估。")
            insight(lines, where=slot1, check=chk)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["頭號得分手（本頁）", "缺陣（本頁）", "補回比例", "第 2 號、第 3 號得分手", "其他強隊", "真實命中率"],
                           first_note="隊友的「每場多得幾分」是用球隊的場數當分母：缺陣的比賽裡隊友一共得幾分 ÷ 缺陣場數，"
                                      "減掉有他上場時的同樣算法。這樣三段加起來，剛好是全部隊友多得的分數。")

            # ===== 2 每一位冠軍 =====
            st.divider()
            slot2 = section("2　每一位冠軍：缺陣時誰多得分",
                            "長條＝隊友每場多得幾分（三段同上）；灰色空心點＝他平常的場均得分，長條碰到灰點＝全部補回；括號是缺陣幾場")
            C = FT[(FT["grp"] == "冠軍") & (FT["go"] > 0)].sort_values("season")
            full = FT[(FT["grp"] == "冠軍") & (FT["go"] == 0)].sort_values("season")
            if C.empty:
                st.info("資料庫裡的冠軍球季還沒有頭號得分手缺陣的比賽。")
            else:
                labels2 = [f"{s_} {ALL_ZH.get(a_, a_)}　{n_}（{int(g_)} 場）"
                           for s_, a_, n_, g_ in zip(C["season"], C["abbreviation"], C["star_name"], C["go"])]
                fig = go.Figure()
                for part, colr in FILL_PARTS:
                    fig.add_trace(go.Bar(y=labels2, x=C[f"{part}_gain"], name=part, orientation="h", marker_color=colr,
                                         hovertemplate=part + "：每場 %{x:+.1f} 分<extra></extra>"))
                fig.add_trace(go.Scatter(y=labels2, x=C["star_on"], mode="markers", name="他平常的場均",
                                         marker=dict(size=11, symbol="circle-open", color="#8f889f", line=dict(width=2)),
                                         hovertemplate="他平常場均 %{x:.1f} 分<extra></extra>"))
                fig.update_layout(barmode="relative", legend=dict(orientation="h", y=1.04, x=0))
                fig.update_xaxes(title="隊友每場多得幾分", zeroline=True, zerolinecolor="#b3adc2")
                fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
                rounded(fig)
                st.plotly_chart(style(fig, 100 + 34 * len(C)), width="stretch", config={"displayModeBar": False})
                big = C[C["go"] >= 5]
                lines2 = []
                if len(big):
                    k50 = int((big["fill"] >= 0.5).sum())
                    top = big.sort_values("fill", ascending=False).iloc[0]
                    lines2.append(f"<b>缺陣至少 5 場的 {len(big)} 位冠軍裡，{k50} 位的隊友補回一半以上：</b>"
                                  f"補最多的是 {top['season']} {ALL_ZH.get(top['abbreviation'], top['abbreviation'])}"
                                  f"（少了 {top['star_name']}，隊友補回 {top['fill']:.0%}）。")
                else:
                    lines2.append("冠軍的頭號得分手缺陣都不到 5 場，單一冠軍的數字只能當參考。")
                if len(full):
                    lines2.append("整季全勤（沒有缺陣場、不在圖上）：" + "、".join(
                        f"{s_} {ALL_ZH.get(a_, a_)} {n_}" for s_, a_, n_ in zip(full["season"], full["abbreviation"], full["star_name"])) + "。")
                lines2.append("讀法：缺陣只有 1、2 場的冠軍，一場爆發就會讓長條變很長，不要只看單一冠軍；"
                              "長條在 0 左邊＝缺陣時那群隊友反而得比較少（例如輪休時主力一起休息）。")
                insight(lines2, where=slot2)
                with st.expander("看每一位冠軍的數字"):
                    tb = pd.DataFrame({
                        "球季": C["season"], "冠軍": [ALL_ZH.get(a, a) for a in C["abbreviation"]], "_key": C["abbreviation"],
                        "頭號得分手": C["star_name"], "他的場均": [fmt(v, ".1f") for v in C["star_on"]],
                        "缺陣場數": C["go"].astype(int),
                        "有他／缺陣戰績": [f"{int(a)}-{int(b - a)}／{int(c)}-{int(d - c)}"
                                     for a, b, c, d in zip(C["ww"], C["gw"], C["wo"], C["go"])],
                        "第 2 號得分手": C["second_name"].fillna("-"),
                        "他多得": [f"{v:+.1f}" for v in C["第 2 號得分手_gain"].fillna(0)],
                        "隊友合計多得": [f"{v:+.1f}" for v in C["gain"]],
                        "補回": [fmt(v, ".0%") for v in C["fill"]],
                    })
                    nice_table(tb, num_cols=("他的場均", "缺陣場數", "他多得", "隊友合計多得", "補回"),
                               signed_cols=("他多得", "隊友合計多得"), dot_col="冠軍", colors=TEAM_COLORS)
                    st.caption("戰績是「勝-敗」。第 2 號得分手＝有他上場的比賽裡，隊上場均得分第二高（至少出賽 10 場）的人。")

            # ===== 3 怎麼補：多出手還是更準？ =====
            st.divider()
            slot3 = section("3　怎麼補：多出手，還是投得更準？",
                            "全部隊友合計：缺陣時每場多出手幾次、真實命中率變多少；最後兩欄是全隊得分和勝率的變化")
            tb3 = pd.DataFrame({
                "組": P.index, "缺陣場數": [int(v) for v in P["games"]],
                "隊友每場出手": [f"{v:+.1f} 次" for v in P["fga_d"]],
                "隊友真實命中率": [f"{v:+.1f} 百分點" for v in P["ts_d"]],
                "全隊每場得分": [f"{g - s:+.1f} 分" for g, s in zip(P["gain"], P["star"])],
                "勝率（有他 → 缺陣）": [f"{a:.0%} → {b:.0%}" for a, b in zip(P["win_on"], P["win_off"])],
            })
            nice_table(tb3, num_cols=("缺陣場數", "隊友每場出手", "隊友真實命中率", "全隊每場得分"),
                       signed_cols=("隊友每場出手", "隊友真實命中率", "全隊每場得分"))
            lines3 = []
            if "冠軍" in P.index:
                c_ = P.loc["冠軍"]
                how = ("主要靠多出手（接手他的出手權），命中率沒有變好" if c_["fga_d"] >= 3 and c_["ts_d"] <= 0.5 else
                       "多出手、也投得更準" if c_["fga_d"] >= 3 else
                       "出手沒有多很多，主要靠投得更準" if c_["ts_d"] > 0.5 else "出手和命中率都沒有明顯變化")
                lines3.append(f"<b>冠軍的隊友{how}：</b>缺陣時每場多出手 {c_['fga_d']:+.1f} 次、"
                              f"真實命中率 {c_['ts_d']:+.1f} 個百分點；全隊每場得分 {c_['gain'] - c_['star']:+.1f} 分。")
            lines3.append("讀法：出手變多、命中率變低，代表隊友是「硬接」他的出手權；兩樣都變好，代表少了他反而打得更流暢。"
                          "全隊每場得分是負數＝沒有全部補回來。")
            insight(lines3, where=slot3)
'''
EARLIER = ["贏球與輸球", "防守端", "節奏與勝率", "奪冠前一季", "陣容深度", "季後賽輪次",
           "頭號得分手缺陣", "輸球時的球星", "缺陣場的對手"]


def insert_after(text, anchor, add, what):
    i = text.find(anchor)
    if i < 0:
        sys.exit(f"找不到「{what}」的位置（{anchor.strip()}），app.py 可能被改過，請把這段訊息貼給助教。")
    j = i + len(anchor)
    return text[:j] + add + text[j:]


def main():
    if not os.path.exists(APP):
        sys.exit("找不到 app.py：請把這個檔案放在和 app.py 同一個資料夾（C:\\basketball_research）再執行。")
    with open(APP, encoding="utf-8", newline="") as f:
        raw = f.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    if f'if PAGE == "{NAME}":' in text:
        print(f"已經有「{NAME}」頁了，不用再加。")
        return
    for p in EARLIER:
        if f'if PAGE == "{p}":' not in text:
            print(f"提醒：這份 app.py 裡沒有「{p}」頁（那天的補丁還沒跑），先跑或後跑都可以。")
    # 1 PAGES：放在「冠軍故事」最後一頁的後面（＝「自由探索」第一頁的前面）
    k = text.find('    ("自由探索",')
    if k < 0:
        sys.exit("找不到 PAGES 裡的「自由探索」，app.py 可能被改過，請把這段訊息貼給助教。")
    text = text[:k] + PAGE_ENTRY + text[k:]
    # 2 名詞小辭典、相關頁面、資料來源與方法
    text = insert_after(text, "TERMS = {\n", TERMS_ADD, "名詞小辭典 TERMS")
    text = insert_after(text, "RELATED = {\n", RELATED_ADD, "相關頁面 RELATED")
    text = insert_after(text, "SOURCES = {\n", SOURCES_ADD, "資料來源 SOURCES")
    # 3 這一頁的程式：放在「每頁共用的結尾」那一段的前面
    k = text.find("# 每頁共用的結尾")
    if k < 0:
        sys.exit("找不到「每頁共用的結尾」，app.py 可能被改過，請把這段訊息貼給助教。")
    k = text.rfind("# =====", 0, k)
    text = text[:k] + BLOCK.lstrip("\n") + "\n\n" + text[k:]
    try:
        compile(text, "app.py", "exec")
    except SyntaxError as e:
        sys.exit(f"加完之後的 app.py 有語法錯誤，沒有寫入（原本的檔案沒有動）：{e}")
    shutil.copyfile(APP, BACKUP)
    with open(APP, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", nl))
    print(f"完成：已加入「{NAME}」頁（冠軍故事最後一頁）。原本的檔案備份在 {os.path.basename(BACKUP)}")
    print("記得先在 Supabase 執行 docs/sql/2026-11-17_誰補上得分.sql，再 streamlit run app.py 看看。")


if __name__ == "__main__":
    main()
