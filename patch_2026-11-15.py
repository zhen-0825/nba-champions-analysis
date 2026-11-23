# -*- coding: utf-8 -*-
"""
patch_2026-11-15.py　把「輸球時的球星」頁加進你電腦裡的 app.py

用法（在 VS Code 終端機，提示字元 (basketball) PS C:\basketball_research> 不用複製）：
    python patch_2026-11-15.py

- 不論你有沒有跑過 11/06～11/14 的補丁都可以用；已經加過就不會重複加。
- 執行前會把原本的 app.py 備份成 app_備份_2026-11-15.py。
- 新頁要先在 Supabase 執行 docs/sql/2026-11-15_輸球時的球星.sql；沒執行時頁面只會顯示提示，不會壞。
"""
import io
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")
NAME = "輸球時的球星"

PAGE_ENTRY = (
    '    ("冠軍故事", "輸球時的球星", "冠軍輸球，是球星失常嗎？",\n'
    '     "冠軍輸球的那幾場，頭號得分手和其他隊友各少得幾分；和其他強隊比，冠軍的球星是不是比較不會一起倒。", set()),\n'
)
RELATED_ENTRY = (
    '    "輸球時的球星": [("頭號得分手缺陣", "他沒上場的比賽，球隊還贏得了嗎"), ("陣容深度", "得分本來就靠幾個人"),\n'
    '               ("得分穩定度", "球星每場得分的起伏")],\n'
)
SOURCES_ENTRY = (
    '    "輸球時的球星": ("star_wl_mv（預先算好的彙總表，docs/sql/2026-11-15_輸球時的球星.sql，由 player_game_stats、team_games、games 算）、"\n'
    '               "league_team_seasons（勝率、其他強隊）、champions",\n'
    '               "2006-07 起；30 隊；例行賽本季不列入",\n'
    '               "頭號得分手＝這一季在這隊例行賽場均得分最高、至少上場 20 場；只算他有上場（超過 0 分鐘）的比賽；"\n'
    '               "隊友＝同一場全隊得分 − 他的得分；輸球時少了幾 %＝（贏球場均 − 輸球場均）÷ 贏球場均；"\n'
    '               "各組先把比賽加總再算（合併計算），單一隊季輸球場數少時不會把平均拉歪。"),\n'
)
BLOCK = r'''# ---------- 輸球時的球星（2026-11-15 新增）----------
@st.cache_data(ttl=900, show_spinner="讀取球星贏球／輸球數據中…")
def load_star_wl():
    """讀取預先算好的彙總表 star_wl_mv（docs/sql/2026-11-15_輸球時的球星.sql）；還沒建立就回傳空表格"""
    try:
        return fetch_all("star_wl_mv", ["team_id", "season", "season_type", "wl"])
    except Exception:
        return pd.DataFrame()


SWL_SUM = ["games", "star_pts", "star_fga", "star_fta", "star_min", "team_pts", "team_fga", "team_fta"]


def swl_rates(g):
    """把加總數字換成每場平均與真實命中率（g 可以是一隊一季，也可以是一整組加起來）"""
    out = pd.DataFrame(index=g.index)
    n = g["games"].where(g["games"] > 0)
    out["star_ppg"] = g["star_pts"] / n
    out["rest_ppg"] = (g["team_pts"] - g["star_pts"]) / n
    out["star_ts"] = g["star_pts"] / (2 * (g["star_fga"] + 0.44 * g["star_fta"])).where(lambda x: x > 0)
    rest_den = 2 * ((g["team_fga"] - g["star_fga"]) + 0.44 * (g["team_fta"] - g["star_fta"]))
    out["rest_ts"] = (g["team_pts"] - g["star_pts"]) / rest_den.where(rest_den > 0)
    out["star_mpg"] = g["star_min"] / n
    out["games"] = g["games"]
    return out


def prep_star_wl(sw, league_tbl, season_type, strong=0.6):
    """一隊一季一列：頭號得分手在贏球場 vs 輸球場（只算他有上場的比賽）"""
    d = sw[sw["season_type"] == season_type].copy()
    if d.empty:
        return d
    for c in SWL_SUM + ["star_ppg"]:
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0)
    keys = ["season", "team_id", "abbreviation", "player_name"]
    w = d[d["wl"] == "W"].set_index(keys)[SWL_SUM]
    l_ = d[d["wl"] == "L"].set_index(keys)[SWL_SUM]
    both = w.join(l_, how="inner", lsuffix="_w", rsuffix="_l")
    if both.empty:
        return pd.DataFrame()
    rw = swl_rates(both[[f"{c}_w" for c in SWL_SUM]].rename(columns=lambda c: c[:-2]))
    rl = swl_rates(both[[f"{c}_l" for c in SWL_SUM]].rename(columns=lambda c: c[:-2]))
    out = rw.add_suffix("_w").join(rl.add_suffix("_l")).reset_index()
    tot = (both[[f"{c}_w" for c in SWL_SUM]].values + both[[f"{c}_l" for c in SWL_SUM]].values)
    tot = pd.DataFrame(tot, columns=SWL_SUM)
    out["share"] = (tot["star_pts"] / tot["team_pts"].where(tot["team_pts"] > 0)).values
    out["star_drop"] = (out["star_ppg_w"] - out["star_ppg_l"]) / out["star_ppg_w"].where(out["star_ppg_w"] > 0) * 100
    out["rest_drop"] = (out["rest_ppg_w"] - out["rest_ppg_l"]) / out["rest_ppg_w"].where(out["rest_ppg_w"] > 0) * 100
    out["champion"] = [(s_, a_) in CHAMP_SET for s_, a_ in zip(out["season"], out["abbreviation"])]
    # 其他強隊：例行賽勝率六成以上、沒奪冠（和月份趨勢、頭號得分手缺陣同一個定義）
    out["grp"] = "其他球隊"
    if not league_tbl.empty and {"w", "gp"} <= set(league_tbl.columns):
        lg = league_tbl[league_tbl["season_type"] == "Regular Season"][["season", "team_id", "w", "gp"]].copy()
        lg["win_pct"] = pd.to_numeric(lg["w"], errors="coerce") / pd.to_numeric(lg["gp"], errors="coerce").where(lambda x: x > 0)
        out = out.merge(lg[["season", "team_id", "win_pct"]], on=["season", "team_id"], how="left")
        out.loc[(~out["champion"]) & (out["win_pct"] >= strong), "grp"] = "其他強隊"
    out.loc[out["champion"], "grp"] = "冠軍"
    # 本季還沒打完，不列入
    return out[out["season"] != ALL_SEASONS[-1]] if season_type == "Regular Season" else out


SWL_GROUPS = ["冠軍", "其他強隊", "其他球隊"]
TERMS.setdefault("頭號得分手", ("這一季在這隊例行賽場均得分最高的球員（至少上場 20 場）", "季中被交易的球員只算替這隊打的比賽"))
TERMS.setdefault("隊友得分", ("同一場比賽裡，頭號得分手以外所有人的得分加起來", "全隊得分 − 頭號得分手得分"))
TERMS.setdefault("輸球時少了幾 %", ("（贏球場均 − 輸球場均）÷ 贏球場均；20 分 → 17 分＝少了 15%", "用百分比，球星和隊友才能放在同一把尺上比"))
TERMS.setdefault("其他強隊", ("整季勝率六成以上、但沒有奪冠的球隊季", "例行賽勝率 ≥ 60%"))
SWL_VIEW = {"場均得分（少了幾 %）": ("ppg", "%"), "真實命中率（掉幾個百分點）": ("ts", "百分點")}

if PAGE == "輸球時的球星":
    hypothesis("冠軍輸球的那幾場，是頭號球星失常，還是隊友沒跟上？",
               "冠軍輸球時，頭號得分手的得分只比贏球時少一點；以百分比算，掉比較多的是其他隊友。"
               "而且冠軍的頭號得分手，輸球時掉得比其他強隊（勝率六成以上、沒奪冠）的頭號得分手少。")
    SW = load_star_wl()
    if SW.empty:
        st.info("尚未載入資料：請先在 Supabase → SQL Editor 執行 docs/sql/2026-11-15_輸球時的球星.sql"
                "（建立 star_wl_mv），再按左側「重新讀取最新資料」。")
    else:
        swl_type = seg("比賽類型", ["例行賽", "季後賽"], "swl_type")
        SWL = prep_star_wl(SW, league, TYPE_OPTIONS[swl_type])
        st.caption("頭號得分手＝這一季在這隊例行賽場均得分最高、至少上場 20 場的球員；只算他有上場的比賽"
                   "（他缺陣的比賽在「頭號得分手缺陣」頁）。隊友＝同一場其他所有人加起來。")
        if SWL.empty or not SWL["champion"].any():
            st.info("資料不足：還沒有同時有贏球場和輸球場的冠軍。")
        else:
            view = seg("看哪一項", list(SWL_VIEW), "swl_view")
            vkey, unit = SWL_VIEW[view]

            # ===== 1. 冠軍／其他強隊／其他球隊：球星和隊友各掉多少 =====
            slot1 = section("1　輸球時，誰掉比較多：頭號得分手，還是隊友？",
                            "紫＝頭號得分手、灰＝其他隊友；長條越高＝輸球時掉越多。同一組的比賽先全部加起來再算，"
                            "所以輸球只有 1、2 場的隊不會把平均拉歪")
            G = SWL.copy()
            gsum = pd.DataFrame()
            for side in ["w", "l"]:
                base = pd.DataFrame({
                    "grp": G["grp"], "games": G[f"games_{side}"],
                    "star_pts": G[f"star_ppg_{side}"] * G[f"games_{side}"],
                    "team_pts": (G[f"star_ppg_{side}"] + G[f"rest_ppg_{side}"]) * G[f"games_{side}"],
                    "star_tsa": G[f"star_ppg_{side}"] * G[f"games_{side}"] / (2 * G[f"star_ts_{side}"]),
                    "rest_tsa": G[f"rest_ppg_{side}"] * G[f"games_{side}"] / (2 * G[f"rest_ts_{side}"]),
                }).replace([float("inf"), -float("inf")], float("nan"))
                s_ = base.groupby("grp")[["games", "star_pts", "team_pts", "star_tsa", "rest_tsa"]].sum()
                s_["star_ppg"] = s_["star_pts"] / s_["games"]
                s_["rest_ppg"] = (s_["team_pts"] - s_["star_pts"]) / s_["games"]
                s_["star_ts"] = s_["star_pts"] / (2 * s_["star_tsa"])
                s_["rest_ts"] = (s_["team_pts"] - s_["star_pts"]) / (2 * s_["rest_tsa"])
                gsum = s_.add_suffix(f"_{side}") if gsum.empty else gsum.join(s_.add_suffix(f"_{side}"))
            gsum = gsum.reindex([g_ for g_ in SWL_GROUPS if g_ in gsum.index])
            gsum["n"] = SWL.groupby("grp").size().reindex(gsum.index)
            for who in ["star", "rest"]:
                if vkey == "ppg":
                    gsum[f"{who}_d"] = (gsum[f"{who}_ppg_w"] - gsum[f"{who}_ppg_l"]) / gsum[f"{who}_ppg_w"] * 100
                else:
                    gsum[f"{who}_d"] = (gsum[f"{who}_ts_w"] - gsum[f"{who}_ts_l"]) * 100
            xlab = [f"{g_}（{int(n_)} 隊季）" for g_, n_ in zip(gsum.index, gsum["n"])]
            fig = go.Figure()
            for who, name, colr in [("star", "頭號得分手", ACCENT), ("rest", "其他隊友", "#b9b2c7")]:
                fig.add_trace(go.Bar(x=xlab, y=gsum[f"{who}_d"], name=name, marker_color=colr,
                                     text=[f"{v:.1f}{'%' if unit == '%' else ''}" for v in gsum[f"{who}_d"]],
                                     textposition="outside", cliponaxis=False, textfont=dict(color=INK),
                                     hovertemplate=f"<b>%{{x}}</b>　{name}<br>輸球時少了 %{{y:.1f}} {unit}<extra></extra>"))
            rounded(fig)
            fig.update_layout(barmode="group")
            fig.update_yaxes(title=f"輸球時少了幾{'%' if unit == '%' else '個百分點'}", rangemode="tozero")
            st.plotly_chart(style(fig, 380), width="stretch", config={"displayModeBar": False})

            if "冠軍" in gsum.index:
                c_ = gsum.loc["冠軍"]
                u_ = "%" if unit == "%" else " 個百分點"
                front = ("前半成立：冠軍輸球時，頭號得分手掉得比隊友少" if c_["star_d"] < c_["rest_d"] else
                         "前半不成立：冠軍輸球時，頭號得分手掉得比隊友多（輸球時球星也一起失常）")
                back = "其他強隊資料不足，後半無法比較"
                if "其他強隊" in gsum.index:
                    s_d = gsum.loc["其他強隊", "star_d"]
                    back = ("後半成立：冠軍的頭號得分手掉得比其他強隊的少" if c_["star_d"] < s_d - 2 else
                            "後半不成立：冠軍和其他強隊的頭號得分手掉得差不多（差不到 2）" if c_["star_d"] <= s_d + 2 else
                            "後半不成立：冠軍的頭號得分手掉得比其他強隊的多")
                lines = [f"冠軍輸球時，頭號得分手{view.split('（')[0]}少了 <b>{c_['star_d']:.1f}{u_}</b>，"
                         f"其他隊友少了 <b>{c_['rest_d']:.1f}{u_}</b>",
                         f"冠軍頭號得分手：贏球場均 {c_['star_ppg_w']:.1f} 分 → 輸球 {c_['star_ppg_l']:.1f} 分；"
                         f"隊友合計：{c_['rest_ppg_w']:.1f} → {c_['rest_ppg_l']:.1f} 分（{swl_type}）。"]
                if "其他強隊" in gsum.index:
                    lines.append(f"其他強隊的頭號得分手少了 {gsum.loc['其他強隊', 'star_d']:.1f}{u_}、"
                                 f"隊友少了 {gsum.loc['其他強隊', 'rest_d']:.1f}{u_}。")
                insight(lines, where=slot1, check=f"{front}；{back}")

            with st.expander("名詞小辭典"):
                term_table(["頭號得分手", "隊友得分", "輸球時少了幾 %", "其他強隊", "真實命中率"],
                           first_note="只算頭號得分手有上場的比賽；輸球時大家得分都會變少（比賽本來就輸了），"
                                      "所以要比的是「誰少得多」，而不是有沒有變少。")

            # ===== 2. 每一位冠軍的頭號得分手：贏球 → 輸球 =====
            C2 = SWL[SWL["champion"]].sort_values("season")
            slot2 = section(f"2　每一位冠軍的頭號得分手：贏球 → 輸球（{swl_type}）",
                            "灰點＝贏球場均得分、彩色點＝輸球場均得分，括號是少了幾 %；"
                            "最右邊灰字是同一場其他隊友少了幾 %。季後賽冠軍只輸 2～8 場，單一冠軍的數字起伏很大")
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}　{p_}" for s_, a_, p_ in
                      zip(C2["season"], C2["abbreviation"], C2["player_name"])]
            fig = go.Figure()
            for lab, (_, r_) in zip(labels, C2.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["star_ppg_w"], r_["star_ppg_l"]], y=[lab, lab], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C2["star_ppg_w"], y=labels, mode="markers", name="贏球",
                                     marker=dict(size=11, color="#b9b2c7", line=dict(width=1.5, color=SURFACE)),
                                     customdata=C2[["games_w"]].values,
                                     hovertemplate="%{y}<br>贏球 %{customdata[0]:.0f} 場，場均 %{x:.1f} 分<extra></extra>"))
            fig.add_trace(go.Scatter(x=C2["star_ppg_l"], y=labels, mode="markers+text", name="輸球",
                                     text=[f"（−{v:.0f}%）" if v >= 0 else f"（+{-v:.0f}%）" for v in C2["star_drop"]],
                                     textposition="middle left", textfont=dict(size=11, color=INK_2),
                                     marker=dict(size=13, color=[TEAM_COLORS.get(a_, ACCENT) for a_ in C2["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     customdata=C2[["games_l", "rest_drop"]].values,
                                     hovertemplate="%{y}<br>輸球 %{customdata[0]:.0f} 場，場均 %{x:.1f} 分"
                                                   "<br>隊友少了 %{customdata[1]:.0f}%<extra></extra>"))
            xmax = float(max(C2["star_ppg_w"].max(), C2["star_ppg_l"].max()))
            for lab, v in zip(labels, C2["rest_drop"]):
                fig.add_annotation(x=xmax + 4, y=lab, text=f"隊友 −{v:.0f}%" if v >= 0 else f"隊友 +{-v:.0f}%",
                                   showarrow=False, xanchor="left", font=dict(size=11, color=MUTED))
            fig.update_xaxes(title="頭號得分手場均得分", range=[0, xmax + 11])
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            st.plotly_chart(style(fig, 110 + 30 * len(C2)), width="stretch", config={"displayModeBar": False})
            k_less = int((C2["star_drop"] < C2["rest_drop"]).sum())
            insight([f"{len(C2)} 位冠軍裡，有 <b>{k_less} 位</b>輸球時頭號得分手掉得比隊友少",
                     f"掉最多的是 {C2.loc[C2['star_drop'].idxmax(), 'season']} "
                     f"{C2.loc[C2['star_drop'].idxmax(), 'player_name']}（少了 {C2['star_drop'].max():.0f}%）；"
                     f"掉最少的是 {C2.loc[C2['star_drop'].idxmin(), 'season']} "
                     f"{C2.loc[C2['star_drop'].idxmin(), 'player_name']}"
                     + (f"（少了 {C2['star_drop'].min():.0f}%）。" if C2['star_drop'].min() >= 0
                        else f"（輸球時反而多得 {-C2['star_drop'].min():.0f}%）。")],
                    where=slot2)
            with st.expander("看每一位冠軍的數字"):
                tb = C2.assign(**{
                    "球季": C2["season"], "冠軍": C2["abbreviation"].map(lambda a_: ALL_ZH.get(a_, a_)),
                    "頭號得分手": C2["player_name"],
                    "贏／輸場數": [f"{w_:.0f}／{l_:.0f}" for w_, l_ in zip(C2["games_w"], C2["games_l"])],
                    "球星得分 贏→輸": [f"{a:.1f} → {b:.1f}" for a, b in zip(C2["star_ppg_w"], C2["star_ppg_l"])],
                    "球星命中率 贏→輸": [f"{a * 100:.1f}% → {b * 100:.1f}%" for a, b in zip(C2["star_ts_w"], C2["star_ts_l"])],
                    "隊友得分 贏→輸": [f"{a:.1f} → {b:.1f}" for a, b in zip(C2["rest_ppg_w"], C2["rest_ppg_l"])],
                    "球星變化": [f"{-v:+.0f}%" for v in C2["star_drop"]],
                    "隊友變化": [f"{-v:+.0f}%" for v in C2["rest_drop"]],
                })
                nice_table(tb[["球季", "冠軍", "頭號得分手", "贏／輸場數", "球星得分 贏→輸", "球星命中率 贏→輸",
                               "隊友得分 贏→輸", "球星變化", "隊友變化"]],
                           num_cols=("贏／輸場數", "球星變化", "隊友變化"), signed_cols=("球星變化", "隊友變化"))

            # ===== 3. 全聯盟：越依賴頭號得分手的隊，輸球時他掉越多嗎？ =====
            if swl_type == "例行賽":
                A3 = SWL[(SWL["games_w"] >= 10) & (SWL["games_l"] >= 10)].dropna(subset=["share", "star_drop"])
                slot3 = section("3　放到全聯盟：越依賴頭號得分手的隊，輸球時他掉越多嗎？",
                                "每個點是一隊一季（贏、輸都至少 10 場），橫軸＝他的得分佔全隊幾成、縱軸＝輸球時他少了幾 %；★ 是冠軍")
                if len(A3) >= 10:
                    oth, ch = A3[~A3["champion"]], A3[A3["champion"]]
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=oth["share"], y=oth["star_drop"], mode="markers", name="其他隊季",
                                             marker=dict(size=7, color="#cfc9da", line=dict(width=0.5, color=SURFACE)),
                                             customdata=oth[["season", "abbreviation", "player_name"]].values,
                                             hovertemplate="%{customdata[0]} %{customdata[1]}　%{customdata[2]}"
                                                           "<br>佔全隊 %{x:.0%}，輸球時少了 %{y:.0f}%<extra></extra>"))
                    fig.add_trace(go.Scatter(x=ch["share"], y=ch["star_drop"], mode="markers", name="冠軍",
                                             marker=dict(symbol="star", size=15,
                                                         color=[TEAM_COLORS.get(a_, ACCENT) for a_ in ch["abbreviation"]],
                                                         line=dict(width=1, color=SURFACE)),
                                             customdata=ch[["season", "abbreviation", "player_name"]].values,
                                             hovertemplate="★ %{customdata[0]} %{customdata[1]}　%{customdata[2]}"
                                                           "<br>佔全隊 %{x:.0%}，輸球時少了 %{y:.0f}%<extra></extra>"))
                    fig.add_hline(y=0, line=dict(color=MUTED, width=1, dash="dot"))
                    fig.update_xaxes(title="頭號得分手佔全隊得分", tickformat=".0%")
                    fig.update_yaxes(title="輸球時他少了幾 %")
                    st.plotly_chart(style(fig, 420), width="stretch", config={"displayModeBar": False})
                    r3 = A3["share"].corr(A3["star_drop"])
                    insight([f"得分佔比和「輸球時掉多少」的相關係數 r ＝ <b>{r3:+.2f}</b>（{corr_word(r3)}）",
                             f"共 {len(A3)} 個隊季；r 是正的＝越依賴他的隊，輸球時他掉越多（對手比較會針對他），"
                             "接近 0＝兩件事沒什麼關係。"], where=slot3)
                else:
                    st.info("資料不足：贏、輸都至少 10 場的隊季不到 10 個。")
'''
EARLIER = ["贏球與輸球", "防守端", "節奏與勝率", "奪冠前一季", "陣容深度", "季後賽輪次", "頭號得分手缺陣"]
FOOT = "# =====================================================================\n# 每頁共用的結尾"


def main():
    if not os.path.exists(APP):
        print("找不到 app.py：請把這個檔案放在 C:\\basketball_research 再執行。")
        sys.exit(1)
    with io.open(APP, encoding="utf-8-sig") as f:
        src = f.read()
    nl = "\r\n" if "\r\n" in src else "\n"
    src = src.replace("\r\n", "\n")
    if f'"冠軍故事", "{NAME}"' in src:
        print(f"已經有「{NAME}」頁了，不用再加。")
        return
    anchors = ['    ("自由探索", "球季趨勢"', "RELATED = {\n", "SOURCES = {\n", FOOT]
    miss = [a.strip()[:20] for a in anchors if a not in src]
    if miss:
        print("這份 app.py 和預期的不一樣，找不到：" + "、".join(miss) + "。沒有修改任何東西，請把這段訊息貼給 Claude。")
        sys.exit(1)
    shutil.copyfile(APP, os.path.join(HERE, "app_備份_2026-11-15.py"))
    src = src.replace(anchors[0], PAGE_ENTRY + anchors[0], 1)
    src = src.replace(anchors[1], anchors[1] + RELATED_ENTRY, 1)
    src = src.replace(anchors[2], anchors[2] + SOURCES_ENTRY, 1)
    src = src.replace(FOOT, BLOCK.strip("\n") + "\n\n\n" + FOOT, 1)
    with io.open(APP, "w", encoding="utf-8", newline="") as f:
        f.write(src.replace("\n", nl))
    print(f"完成：已加入「{NAME}」頁（冠軍故事最後一頁）。原本的檔案備份在 app_備份_2026-11-15.py")
    for p in EARLIER:
        if f'"冠軍故事", "{p}"' not in src:
            print(f"提醒：這份 app.py 裡沒有「{p}」頁（那天的補丁還沒跑；先跑或後跑都可以）。")


if __name__ == "__main__":
    main()
