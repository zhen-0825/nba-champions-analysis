"""
補丁 2026-11-10：把「節奏與勝率」頁加進你電腦裡的 app.py

用法（VS Code 終端機，提示字元不用複製）：
    python patch_2026-11-10.py

- 不管你的 app.py 是 GitHub main 那份、還是已經跑過 11/06、11/09 補丁的那份，都可以用
- 已經加過就不會重複加
- 原本的檔案會先備份成 app_備份_2026-11-10.py
"""
import shutil
import sys

APP = "app.py"
MARK = "節奏與勝率"

PAGE_ENTRY = """    ("冠軍故事", "節奏與勝率", "打得快的隊比較會贏嗎？",
     "冠軍的節奏排聯盟第幾、全聯盟節奏和勝率有沒有關係、進了季後賽會不會變慢。", set()),
"""

NEW_TERMS = """    "回合": ("一次進攻機會：從拿到球開始，到投進、投失被對手搶到籃板、失誤或罰球結束為止", "約等於 出手 ＋ 0.44 × 罰球出手 − 進攻籃板 ＋ 失誤"),
    "季後賽節奏變化": ("同一隊、同一季，季後賽節奏減掉例行賽節奏；負數＝季後賽打得比較慢", "季後賽節奏 − 例行賽節奏"),
"""

RELATED_ENTRY = """    "節奏與勝率": [("冠軍密碼", "淨效率用每 100 回合算，已經把節奏扣掉"), ("跑動距離", "打得快的隊，是不是也跑得比較多"),
              ("例行賽與季後賽", "季後賽變慢，球星的得分怎麼變")],
"""

SOURCES_ENTRY = """    "節奏與勝率": ("league_team_seasons（全聯盟 30 隊每季：pace、勝負、例行賽／季後賽）、champions",
              "2006-07 起已經有冠軍的球季；本季不列入",
              "節奏＝每 48 分鐘回合數（NBA 官方）；比同季聯盟＝這隊 − 同季 30 隊平均；第幾快＝同季 30 隊排名（1＝最快）；"
              "相關係數 r 用「比同季平均快幾個回合」和例行賽勝率算；季後賽變化＝季後賽 − 例行賽，只算有打季後賽的隊。"),
"""

PAGE_CODE = r'''
# ---------- 節奏與勝率：打得快的隊比較會贏嗎？（2026-11-10）----------
def prep_pace(lg):
    """全聯盟 30 隊每季：節奏、勝率、同季排名、和同季平均的差；只留已經有冠軍的球季（本季還沒打完）"""
    if lg is None or lg.empty or "pace" not in lg.columns:
        return pd.DataFrame()
    d = lg[lg["season_type"].isin(["Regular Season", "Playoffs"])].copy()
    for c in ["pace", "w", "gp", "net_rating"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[(d["gp"] > 0) & d["pace"].notna()]
    d["win_pct"] = d["w"] / d["gp"]
    keys = ["season", "season_type"]
    d["lg_pace"] = d.groupby(keys)["pace"].transform("mean")
    d["d_pace"] = d["pace"] - d["lg_pace"]                                    # 比同季平均快幾個回合
    d["rk_pace"] = d.groupby(keys)["pace"].rank(ascending=False, method="min")  # 1＝最快
    champ_ids = set(zip(champs["season"], champs["team_id"]))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    return d[d["season"].isin(set(champs["season"]))]


def corr_r(x, y):
    """相關係數 r（點太少或沒有變化時回傳空值）"""
    ok = x.notna() & y.notna()
    if ok.sum() < 5:
        return float("nan")
    return float(x[ok].corr(y[ok]))


if PAGE == "節奏與勝率":
    hypothesis("打得快的隊比較會贏嗎？冠軍是打得快，還是打得慢？進了季後賽會不會變慢？",
               "節奏和勝率幾乎沒有關係（同一季裡相關係數 |r| < 0.2）；冠軍有快有慢，節奏排名的中位數在聯盟中段（第 10～20 名）；"
               "進了季後賽幾乎每一隊都會變慢，冠軍也一樣。")
    PC = prep_pace(league)
    if PC.empty:
        st.info("尚未載入資料，請執行 python load_to_supabase.py --only league（全聯盟每季數據還沒有寫進資料庫）")
    else:
        RS = PC[PC["season_type"] == "Regular Season"]
        st.caption(f"用全聯盟 30 隊每季數據（{RS['season'].min()}～{RS['season'].max()}，共 {RS['season'].nunique()} 季）計算；"
                   "本季還沒打完，先不列入。節奏＝每 48 分鐘打幾個回合。")
        # ===== 1 每一位冠軍排第幾 =====
        slot1 = section("1　每一位冠軍的節奏排第幾（例行賽）",
                        "一列一季：灰點＝當季其他球隊、彩色點＝冠軍；橫軸＝比同季聯盟平均快（右）或慢（左）幾個回合；"
                        "括號是在 30 隊裡第幾快")
        C1 = RS[RS["champion"]].sort_values("season")
        if C1.empty:
            st.info("資料庫裡還沒有冠軍球季的全聯盟數據。")
        else:
            lab = {s_: f"{s_} {ALL_ZH.get(a_, a_)}（第 {r_:.0f} 快）"
                   for s_, a_, r_ in zip(C1["season"], C1["abbreviation"], C1["rk_pace"])}
            O1 = RS[(~RS["champion"]) & RS["season"].isin(lab)]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=O1["d_pace"], y=[lab[s_] for s_ in O1["season"]], mode="markers",
                                     name="當季其他球隊", marker=dict(size=7, color=DIM),
                                     customdata=O1[["abbreviation", "pace"]].values,
                                     hovertemplate="%{customdata[0]}：節奏 %{customdata[1]:.1f}（%{x:+.1f}）<extra></extra>"))
            fig.add_trace(go.Scatter(x=C1["d_pace"], y=[lab[s_] for s_ in C1["season"]], mode="markers", name="冠軍",
                                     marker=dict(size=14, symbol="diamond", line=dict(width=1.2, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in C1["abbreviation"]]),
                                     customdata=C1[["abbreviation", "pace"]].values,
                                     hovertemplate="★ %{customdata[0]}：節奏 %{customdata[1]:.1f}（%{x:+.1f}）<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dash"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="比同季聯盟平均快幾個回合（每 48 分鐘）", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 100 + 30 * len(C1)), width="stretch", config={"displayModeBar": False})
            med = float(C1["rk_pace"].median())
            n_fast = int((C1["rk_pace"] <= 10).sum())
            n_slow = int((C1["rk_pace"] >= 21).sum())
            n_mid = len(C1) - n_fast - n_slow
            fast1 = C1.sort_values("rk_pace").iloc[0]
            slow1 = C1.sort_values("rk_pace").iloc[-1]
            lines = [f"<b>冠軍有快有慢：</b>{len(C1)} 位冠軍裡，{n_fast} 位排前 10 快、{n_mid} 位在中段、{n_slow} 位排後 10 名；"
                     f"排名中位數是第 {med:.0f} 快。",
                     f"最快的是 {fast1['season']} {ALL_ZH.get(fast1['abbreviation'], fast1['abbreviation'])}（第 {fast1['rk_pace']:.0f} 快），"
                     f"最慢的是 {slow1['season']} {ALL_ZH.get(slow1['abbreviation'], slow1['abbreviation'])}（第 {slow1['rk_pace']:.0f} 快）。",
                     "讀法：彩色點在虛線右邊＝那一季比聯盟平均打得快。看彩色點是不是左右都有——"
                     "如果都擠在同一邊，才代表冠軍有固定的節奏。"]
            ok_mid = 10 <= med <= 20 and n_fast > 0 and n_slow > 0
            chk1 = (("第二句成立" if ok_mid else "第二句不成立")
                    + f"：排名中位數第 {med:.0f}，快（前 10）{n_fast} 位、慢（後 10）{n_slow} 位。")
            insight(lines, where=slot1, check=chk1)
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                term_table(["節奏", "回合", "比同季聯盟平均多多少", "相關係數 r", "季後賽節奏變化"],
                           first_note="節奏只說明<b>打得多快</b>，不是打得多好；"
                                      "用每 100 回合算的進攻、防守效率（冠軍密碼頁）已經把節奏的影響扣掉了。")

        # ===== 2 打得快比較會贏嗎 =====
        st.divider()
        slot2 = section("2　打得快比較會贏嗎？（全聯盟，例行賽）",
                        "每個點是一隊一季；橫軸＝比同季平均快幾個回合、縱軸＝勝率，★ 是冠軍；"
                        "也可以切換成「每一季的 r」，看是不是每一年都一樣")
        view2 = seg("看哪一種", ["全部的點", "每一季的 r"], "pace_view2")
        r_all = corr_r(RS["d_pace"], RS["win_pct"])
        by_s = pd.DataFrame([{"season": s_, "r": corr_r(g_["d_pace"], g_["win_pct"])} for s_, g_ in RS.groupby("season")])
        if view2 == "全部的點":
            o2, c2 = RS[~RS["champion"]], RS[RS["champion"]]
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=o2["d_pace"], y=o2["win_pct"], mode="markers", name="其他球隊",
                                     marker=dict(size=7, color=DIM, opacity=0.85),
                                     customdata=o2[["season", "abbreviation"]].values,
                                     hovertemplate="%{customdata[0]} %{customdata[1]}<br>快 %{x:+.1f} 回合｜勝率 %{y:.0%}<extra></extra>"))
            fig.add_trace(go.Scatter(x=c2["d_pace"], y=c2["win_pct"], mode="markers", name="冠軍",
                                     marker=dict(size=14, symbol="star", line=dict(width=1, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in c2["abbreviation"]]),
                                     customdata=c2[["season", "abbreviation"]].values,
                                     hovertemplate="★ %{customdata[0]} %{customdata[1]}<br>快 %{x:+.1f} 回合｜勝率 %{y:.0%}<extra></extra>"))
            fig.add_vline(x=0, line=dict(color=MUTED, width=1, dash="dash"))
            fig.update_xaxes(title="比同季聯盟平均快幾個回合")
            fig.update_yaxes(title="例行賽勝率", tickformat=".0%")
            fig.update_layout(legend=dict(orientation="h", y=1.06, x=0))
            st.plotly_chart(style(fig, 420), width="stretch")
        else:
            fig = go.Figure(go.Bar(x=by_s["season"], y=by_s["r"],
                                   marker_color=[ACCENT if abs(v) >= 0.3 else "#c9c3d6" for v in by_s["r"].fillna(0)],
                                   text=[fmt(v, "+.2f") for v in by_s["r"]], textposition="outside", cliponaxis=False,
                                   textfont=dict(size=10, color=INK_2),
                                   hovertemplate="%{x}：r = %{y:+.2f}<extra></extra>"))
            rounded(fig)
            for y_ in (0.3, -0.3):
                fig.add_hline(y=y_, line=dict(color=MUTED, width=1, dash="dot"))
            fig.update_xaxes(type="category", title="球季")
            fig.update_yaxes(title="節奏和勝率的相關係數 r", range=[-1, 1])
            st.plotly_chart(style(fig, 360), width="stretch", config={"displayModeBar": False})
        n_strong = int((by_s["r"].abs() >= 0.3).sum())
        n_pos = int((by_s["r"] > 0).sum())
        strength = ("幾乎沒有關係" if abs(r_all) < 0.1 else "弱" if abs(r_all) < 0.3 else "中等" if abs(r_all) < 0.5 else "強")
        lines = [f"<b>節奏和勝率{strength}：</b>全部 {len(RS)} 個隊季放在一起，r = {r_all:+.2f}"
                 + ("（打得快的隊稍微比較會贏）。" if r_all >= 0.1 else "（打得快的隊稍微比較會輸）。" if r_all <= -0.1 else "。"),
                 f"{len(by_s)} 季裡，有 {n_pos} 季是正的（快的隊贏比較多）、{len(by_s) - n_pos} 季是負的；"
                 f"|r| 到 0.3（中等）的只有 {n_strong} 季。",
                 "讀法：r 正負一直換、大多在 ±0.3 的虛線之間，代表「快」本身不會讓球隊比較會贏；"
                 "第 1 節冠軍有快有慢，也是同一件事。"]
        chk2 = (("第一句成立" if abs(r_all) < 0.2 else "第一句不成立") + f"：全部隊季 r = {r_all:+.2f}"
                + f"，{n_strong} / {len(by_s)} 季 |r| ≥ 0.3。") if pd.notna(r_all) else None
        insight(lines, where=slot2, check=chk2)

        # ===== 3 進季後賽會變慢嗎 =====
        st.divider()
        slot3 = section("3　進了季後賽會變慢嗎？",
                        "一列一位冠軍：灰點＝例行賽節奏、彩色點＝季後賽節奏；括號是季後賽 − 例行賽（負數＝變慢）；"
                        "發現框再和所有季後賽球隊比")
        PO = PC[PC["season_type"] == "Playoffs"][["season", "team_id", "pace"]].rename(columns={"pace": "po_pace"})
        RP = RS[["season", "team_id", "abbreviation", "pace", "champion"]].merge(PO, on=["season", "team_id"], how="inner")
        RP["dlt"] = RP["po_pace"] - RP["pace"]
        C3 = RP[RP["champion"]].sort_values("season")
        if C3.empty:
            st.info("資料庫裡還沒有冠軍的季後賽全聯盟數據（load_to_supabase.py --only league 會一起抓季後賽）。")
        else:
            labels = [f"{s_} {ALL_ZH.get(a_, a_)}（{d_:+.1f}）" for s_, a_, d_ in zip(C3["season"], C3["abbreviation"], C3["dlt"])]
            fig = go.Figure()
            for lab_, (_, r_) in zip(labels, C3.iterrows()):
                fig.add_trace(go.Scatter(x=[r_["pace"], r_["po_pace"]], y=[lab_, lab_], mode="lines",
                                         line=dict(color="#d9d3e6", width=3), showlegend=False, hoverinfo="skip"))
            fig.add_trace(go.Scatter(x=C3["pace"], y=labels, mode="markers", name="例行賽",
                                     marker=dict(size=11, color="#b3adc2", line=dict(width=1, color=SURFACE)),
                                     hovertemplate="%{y}<br>例行賽節奏 %{x:.1f}<extra></extra>"))
            fig.add_trace(go.Scatter(x=C3["po_pace"], y=labels, mode="markers", name="季後賽",
                                     marker=dict(size=14, color=[TEAM_COLORS.get(a, ACCENT) for a in C3["abbreviation"]],
                                                 line=dict(width=1.5, color=SURFACE)),
                                     hovertemplate="%{y}<br>季後賽節奏 %{x:.1f}<extra></extra>"))
            fig.update_yaxes(type="category", autorange="reversed", showgrid=False)
            fig.update_xaxes(title="節奏（每 48 分鐘回合數）", showgrid=True, gridcolor=GRID)
            fig.update_layout(legend=dict(orientation="h", y=1.04, x=0))
            st.plotly_chart(style(fig, 100 + 32 * len(C3)), width="stretch", config={"displayModeBar": False})
            O3 = RP[~RP["champion"]]
            k_slow_c = int((C3["dlt"] < 0).sum())
            share_all = float((RP["dlt"] < 0).mean())
            c_m, o_m = C3["dlt"].mean(), O3["dlt"].mean() if len(O3) else float("nan")
            lines = [f"<b>季後賽變慢：</b>{len(C3)} 位冠軍裡有 {k_slow_c} 位季後賽比例行賽慢（平均 {c_m:+.1f} 個回合）。",
                     (f"所有打進季後賽的球隊（{len(RP)} 個隊季）有 {share_all:.0%} 變慢；"
                      f"其他季後賽球隊平均 {o_m:+.1f}，冠軍" + ("變慢得比較多。" if c_m < o_m else "變慢得比較少。"))
                     if len(O3) else "還沒有其他季後賽球隊可以比較。",
                     "讀法：季後賽對手固定、防守更認真、暫停和罰球比較多，整體比賽會變慢；"
                     "所以要看冠軍是「跟大家一樣變慢」，還是特別快或特別慢。"]
            ok3 = share_all >= 0.7 and k_slow_c > len(C3) / 2
            chk3 = (("第三句成立" if ok3 else "第三句不成立")
                    + f"：{share_all:.0%} 的季後賽球隊變慢，冠軍 {k_slow_c} / {len(C3)} 位變慢。")
            insight(lines, where=slot3, check=chk3)

        # ===== 4 背景：聯盟一年比一年快 =====
        st.divider()
        slot4 = section("4　背景：聯盟一年比一年快",
                        "灰線＝聯盟平均節奏、彩色點＝當季冠軍；這一節不是在驗證假設，"
                        "而是說明為什麼前面都用「和同季平均比」：不同年代的快慢差很多，直接比數字不公平")
        LGm = RS.groupby("season")["pace"].mean().reset_index()
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=LGm["season"], y=LGm["pace"], mode="lines+markers", name="聯盟平均",
                                 line=dict(color=MUTED, width=2.4), marker=dict(size=6, color=MUTED),
                                 hovertemplate="%{x} 聯盟平均 %{y:.1f}<extra></extra>"))
        if len(C1):
            fig.add_trace(go.Scatter(x=C1["season"], y=C1["pace"], mode="markers", name="冠軍",
                                     marker=dict(size=11, symbol="diamond", line=dict(width=1, color=SURFACE),
                                                 color=[TEAM_COLORS.get(a, ACCENT) for a in C1["abbreviation"]]),
                                     customdata=C1["abbreviation"],
                                     hovertemplate="%{x} ★ %{customdata}：%{y:.1f}<extra></extra>"))
        fig.update_xaxes(type="category", title="球季")
        fig.update_yaxes(title="節奏（每 48 分鐘回合數）")
        fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
        st.plotly_chart(style(fig, 340), width="stretch", config={"displayModeBar": False})
        if len(LGm) >= 2:
            lo_ = LGm.sort_values("pace").iloc[0]
            insight([f"聯盟平均節奏從 {LGm['season'].iloc[0]} 的 {LGm['pace'].iloc[0]:.1f} 變成 "
                     f"{LGm['season'].iloc[-1]} 的 {LGm['pace'].iloc[-1]:.1f} 個回合；最慢是 {lo_['season']}（{lo_['pace']:.1f}）。"],
                    where=slot4, to_summary=False)
        with st.expander("看每一位冠軍的節奏數字"):
            T = C1.merge(RP[["season", "team_id", "po_pace", "dlt"]], on=["season", "team_id"], how="left") if len(C1) else C1
            if len(T):
                nice_table(pd.DataFrame({
                    "球季": T["season"], "冠軍": [ALL_ZH.get(a, a) for a in T["abbreviation"]], "_key": T["abbreviation"],
                    "例行賽節奏": [f"{v:.1f}" for v in T["pace"]], "聯盟平均": [f"{v:.1f}" for v in T["lg_pace"]],
                    "比聯盟": [f"{v:+.1f}" for v in T["d_pace"]], "第幾快": [f"{v:.0f}" for v in T["rk_pace"]],
                    "例行賽勝率": [f"{v:.0%}" for v in T["win_pct"]],
                    "季後賽節奏": [fmt(v, ".1f") for v in T["po_pace"]], "季後賽變化": [fmt(v, "+.1f") for v in T["dlt"]],
                }), num_cols=("例行賽節奏", "聯盟平均", "比聯盟", "第幾快", "例行賽勝率", "季後賽節奏", "季後賽變化"),
                    signed_cols=("比聯盟", "季後賽變化"), dot_col="冠軍", colors=TEAM_COLORS)


'''


def insert_before(text, anchor, new, name):
    i = text.find(anchor)
    if i < 0:
        print(f"找不到插入位置（{name}），沒有修改任何東西。請把這段訊息截圖給助教。")
        sys.exit(1)
    return text[:i] + new + text[i:]


def main():
    try:
        text = open(APP, encoding="utf-8").read()
    except FileNotFoundError:
        print("找不到 app.py：請確認終端機在 C:\\basketball_research 資料夾（提示字元最後是 basketball_research>）")
        sys.exit(1)
    if f'if PAGE == "{MARK}":' in text:
        print("這份 app.py 已經有「節奏與勝率」頁，不用再加。")
        return
    shutil.copy(APP, "app_備份_2026-11-10.py")
    text = insert_before(text, '    ("自由探索", "球季趨勢",', PAGE_ENTRY, "頁面清單 PAGES")
    text = insert_before(text, "}\n\n\ndef term_table(", NEW_TERMS, "名詞小辭典 TERMS")
    text = insert_before(text, "# ---------- 自動結論：用資料算出一句話，放在圖的上面 ----------", PAGE_CODE, "頁面程式")
    text = insert_before(text, '    "球季趨勢": [("球隊 × 球季"', RELATED_ENTRY, "相關頁面 RELATED")
    text = insert_before(text, '    "球季趨勢": ("team_season_stats', SOURCES_ENTRY, "資料來源 SOURCES")
    open(APP, "w", encoding="utf-8").write(text)
    print("完成：已加入「節奏與勝率」頁。原本的檔案備份在 app_備份_2026-11-10.py")
    for p_ in ["贏球與輸球", "防守端"]:
        if f'if PAGE == "{p_}":' not in text:
            print(f"提醒：這份 app.py 裡沒有「{p_}」頁（11/06、11/09 的補丁還沒跑）。新頁一樣能用；想補上就再跑那兩個補丁。")


if __name__ == "__main__":
    main()
