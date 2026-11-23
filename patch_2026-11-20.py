"""
patch_2026-11-20.py　把「二號與三號得分手」頁加進你電腦裡的 app.py

用法（在 VS Code 終端機，專案資料夾 C:\basketball_research）：
    python patch_2026-11-20.py

會做的事：
  1. 先把原本的 app.py 備份成 app_備份_2026-11-20.py
  2. 在左側選單「冠軍故事」最後面加一頁「二號與三號得分手」
  3. 把這一頁的程式加在 app.py 最後的 finish_page() 前面
不論你有沒有跑過 11/06～11/19 的補丁都可以用；已經加過不會重複加。
新頁要先在 Supabase 執行 docs/sql/2026-11-20_二號與三號得分手.sql（沒執行時頁面只會顯示提示，不會壞）。
"""
import os
import shutil
import sys

PAGE = "二號與三號得分手"
HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app.py")
BACKUP = os.path.join(HERE, "app_備份_2026-11-20.py")
PAGES_LINE = ('    ("冠軍故事", "二號與三號得分手", "越往後，誰站出來？",\n'
              '     "季後賽每一輪，頭號、第 2、第 3 號得分手比自己例行賽變多少；頭號被守住時，配角有沒有補上。", set()),\n')
EARLIER = ["贏球與輸球", "防守端", "節奏與勝率", "奪冠前一季", "陣容深度", "季後賽輪次", "頭號得分手缺陣",
           "輸球時的球星", "缺陣場的對手", "誰補上得分", "每一輪的球星", "對手防守與球星"]

BLOCK = r'''
# ---------- 二號與三號得分手：季後賽越往後，誰站出來？（2026-11-20）----------
SUP_SQL = "docs/sql/2026-11-20_二號與三號得分手.sql"
SUP_ROUND = ["首輪", "次輪", "分區決賽", "總冠軍賽"]
SUP_VIEW = {   # 顯示名稱 → (欄位, 單位, 是不是比例)
    "得分佔全隊比例": ("share", "百分點", True),
    "真實命中率": ("ts", "百分點", True),
    "場均得分": ("ppg", "分", False),
    "場均上場分鐘": ("mpg", "分鐘", False),
}
SUP_LINES = [   # （組名, 冠軍嗎, 第幾號, 顏色, 線型）
    ("冠軍・頭號得分手", True, "頭號", "#b9a6f0", "solid"),
    ("冠軍・第 2、3 號", True, "第 2、3 號", ACCENT, "solid"),
    ("其他晉級球隊・頭號得分手", False, "頭號", "#c9c4d4", "dash"),
    ("其他晉級球隊・第 2、3 號", False, "第 2、3 號", "#5f5873", "dash"),
]
SUP_NEED = {"season", "team_id", "abbreviation", "rnd", "games", "wins", "team_pts", "scorer_rk", "player_name",
            "g", "min", "pts", "fga", "fta", "reg_g", "reg_min", "reg_pts", "reg_fga", "reg_fta", "team_reg_pts"}


@st.cache_data(ttl=3600, show_spinner="讀取每一輪的前三號得分手中…")
def _read_sup():
    """讀 support_round_mv（一隊一季一輪一位得分手一列）。讀不到會丟出錯誤，Streamlit 不會記住失敗的結果"""
    return fetch_all("support_round_mv", ["season", "team_id", "rnd", "scorer_rk"])


def load_sup():
    """讀不到、是空的、或欄位不對（例如還沒執行今天的 SQL）時回傳 None，頁面改顯示提示"""
    try:
        df = _read_sup()
    except Exception:
        return None
    if df.empty or not SUP_NEED.issubset(df.columns):
        return None
    return df


def sup_wmean(v, w):
    """加權平均；全部是空值時回傳 NaN（不會除以 0）"""
    ok = v.notna() & w.notna() & (w > 0)
    return (v[ok] * w[ok]).sum() / w[ok].sum() if ok.any() else float("nan")


def sup_prep(df, champs_):
    """算出每一列「這一輪」和「自己例行賽」的四項數字，以及兩者的差"""
    d = df.copy()
    for c in SUP_NEED - {"season", "abbreviation", "player_name"}:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d[d["rnd"].between(1, 4) & d["scorer_rk"].between(1, 3)].copy()
    pos = lambda s: s.where(s > 0)
    d["tsa"] = 2 * (d["fga"] + 0.44 * d["fta"])
    d["ppg"], d["ppg_reg"] = d["pts"] / pos(d["g"]), d["reg_pts"] / pos(d["reg_g"])
    d["mpg"], d["mpg_reg"] = d["min"] / pos(d["g"]), d["reg_min"] / pos(d["reg_g"])
    d["ts"] = d["pts"] / pos(d["tsa"])
    d["ts_reg"] = d["reg_pts"] / pos(2 * (d["reg_fga"] + 0.44 * d["reg_fta"]))
    d["share"], d["share_reg"] = d["pts"] / pos(d["team_pts"]), d["reg_pts"] / pos(d["team_reg_pts"])
    for c in ["ppg", "mpg", "ts", "share"]:
        d[f"d_{c}"] = d[c] - d[f"{c}_reg"]
    # 以「球隊場數」算的每場得分：他缺陣的比賽算 0 分，第 3 節用來看「少掉的分數誰補上」
    d["d_pts_tg"] = d["pts"] / pos(d["games"]) - d["ppg_reg"]
    champ_ids = set(zip(champs_["season"], pd.to_numeric(champs_["team_id"], errors="coerce")))
    d["champion"] = [(s_, t_) in champ_ids for s_, t_ in zip(d["season"], d["team_id"])]
    d["won"] = d["wins"] >= 4
    d["role"] = d["scorer_rk"].map(lambda r: "頭號" if r == 1 else "第 2、3 號")
    d["round"] = d["rnd"].map(lambda r: SUP_ROUND[int(r) - 1])
    return d


def sup_weight(col):
    """每一項用不同的權重：命中率看出手數、得分佔比看球隊場數、其他看他上場幾場"""
    return {"ts": "tsa", "share": "games"}.get(col, "g")


def sup_lines(d, col):
    """四條線 × 四輪的加權平均（只留冠軍和贏下這一輪的球隊，對照組才公平）"""
    rows = []
    x = d[d["champion"] | d["won"]]
    for name, is_champ, role, _, _ in SUP_LINES:
        g_ = x[(x["champion"] == is_champ) & (x["role"] == role)]
        for r in range(1, 5):
            gg = g_[g_["rnd"] == r]
            rows.append({"line": name, "rnd": r, "mean": sup_wmean(gg[f"d_{col}"], gg[sup_weight(col)]),
                         "n": gg[["season", "team_id"]].drop_duplicates().shape[0]})
    return pd.DataFrame(rows)


def sup_sg(v):
    """帶正負號、一位小數；−0.03 這種不要印成「-0.0」"""
    return "-" if pd.isna(v) else f"{(0.0 if abs(v) < 0.05 else v):+.1f}"


def sup_val(L, line, r):
    x = L[(L["line"] == line) & (L["rnd"] == r)]["mean"]
    return x.iloc[0] if len(x) else float("nan")


if PAGE == "二號與三號得分手":
    hypothesis("季後賽越往後，對手越會包夾頭號得分手；那第 2、第 3 號得分手會站出來嗎？",
               "前段：冠軍的第 2、3 號得分手，越往後得分佔全隊比例越高（總冠軍賽比首輪平均每人多 1 個百分點以上）；"
               "中段：前三輪裡，冠軍第 2、3 號的真實命中率比其他晉級球隊的第 2、3 號好（至少多 1 個百分點）；"
               "後段（交叉驗證）：頭號得分手這一輪少得越多，第 2、3 號就多得越多（r ≤ −0.3）。")
    st.markdown('<div class="howread" style="margin-top:-4px">接著「每一輪的球星」（只看頭號得分手）往下問：他被守住的時候，誰補上？'
                '第 1～3 號得分手＝這一季這隊例行賽場均得分前 3 名（至少上場 20 場），季後賽也看同一批人；'
                '每一輪都和他自己這一季的例行賽比。</div>', unsafe_allow_html=True)
    SUP = load_sup()
    if SUP is None:
        st.info(f"尚未載入資料：請先在 Supabase 的 SQL Editor 執行 {SUP_SQL}（建立 support_round_mv），"
                "再按左側「重新讀取最新資料」。")
    else:
        D = sup_prep(SUP, champs)
        D = D[D["season"].isin(set(champs["season"]))]
        if D.empty or not D["champion"].any():
            st.info("資料不足：support_round_mv 裡還沒有冠軍的季後賽資料。")
        else:
            view = seg("看哪一項", list(SUP_VIEW), "sup_view")
            col, unit, is_pct = SUP_VIEW[view]
            k = 100 if is_pct else 1

            # ===== 1. 每一輪比自己例行賽變多少 =====
            slot1 = section(f"1　越往後，誰站出來？（{view}，比自己例行賽變多少）",
                            "紫色實線＝冠軍、灰色虛線＝同一輪也晉級的其他球隊；淺色＝頭號得分手、深色＝第 2、3 號；"
                            "0 以上＝這一輪比他自己例行賽高。總冠軍賽的贏家一定是冠軍，所以那一輪沒有對照組", anchor="sup1")
            L = sup_lines(D, col)
            fig = go.Figure()
            for name, _, _, c_, dash in SUP_LINES:
                g_ = L[L["line"] == name].sort_values("rnd")
                fig.add_trace(go.Scatter(x=[SUP_ROUND[int(r) - 1] for r in g_["rnd"]], y=g_["mean"] * k, name=name,
                                         mode="lines+markers", connectgaps=False,
                                         line=dict(color=c_, width=3 if "冠軍" in name else 2, dash=dash),
                                         marker=dict(size=9 if "冠軍" in name else 7, color=c_, line=dict(width=1, color=SURFACE)),
                                         customdata=g_[["n"]].values,
                                         hovertemplate=name + "<br>%{x}：%{y:+.1f} " + unit + "（%{customdata[0]:.0f} 隊）<extra></extra>"))
            fig.add_hline(y=0, line=dict(color=MUTED, width=1))
            fig.update_xaxes(type="category", categoryorder="array", categoryarray=SUP_ROUND)
            fig.update_yaxes(title=f"比自己例行賽變多少（{unit}）", tickformat="+.1f")
            fig.update_layout(legend=dict(orientation="h", y=1.1, x=0))
            st.plotly_chart(style(fig, 400), width="stretch", config={"displayModeBar": False})

            c1, c4 = sup_val(L, "冠軍・第 2、3 號", 1), sup_val(L, "冠軍・第 2、3 號", 4)
            s1, s4 = sup_val(L, "冠軍・頭號得分手", 1), sup_val(L, "冠軍・頭號得分手", 4)
            lines = [f"冠軍的第 2、3 號得分手，{view}在首輪比例行賽 {sup_sg(c1 * k)}、總冠軍賽 {sup_sg(c4 * k)} {unit}；"
                     f"頭號得分手是 {sup_sg(s1 * k)} → {sup_sg(s4 * k)} {unit}。"]
            # 對照假設：固定用「得分佔比」和「真實命中率」判斷，不受上面切換影響
            Ls, Lt = sup_lines(D, "share"), sup_lines(D, "ts")
            up = (sup_val(Ls, "冠軍・第 2、3 號", 4) - sup_val(Ls, "冠軍・第 2、3 號", 1)) * 100
            front = ("前段算不出來（總冠軍賽或首輪沒有資料）" if pd.isna(up) else
                     ("前段成立" if up >= 1 else "前段不成立") + f"：第 2、3 號的得分佔比，總冠軍賽比首輪平均每人 {up:+.1f} 個百分點（門檻 +1）")
            gaps = [(sup_val(Lt, "冠軍・第 2、3 號", r) - sup_val(Lt, "其他晉級球隊・第 2、3 號", r)) * 100 for r in (1, 2, 3)]
            gaps = [x for x in gaps if pd.notna(x)]
            if gaps:
                gm = sum(gaps) / len(gaps)
                mid = (("中段成立" if gm >= 1 else "中段不成立") + f"：前三輪冠軍第 2、3 號的命中率變化平均比其他晉級球隊 {gm:+.1f} 個百分點（門檻 +1）；"
                       f"{sum(1 for x in gaps if x > 0)} / {len(gaps)} 輪比較好")
            else:
                mid = "中段算不出來（前三輪沒有對照組資料）"
            lines.append("讀法：先看深紫色線是不是越往右越高（第 2、3 號越後面越重要），再看它在前三輪是不是高過深灰色虛線（比其他晉級球隊的第 2、3 號撐得住）；"
                         "切到「場均上場分鐘」可以看得分增加是不是只是打比較久。")
            insight(lines, where=slot1, check=front + "；" + mid + "。")
            with st.expander("這頁的名詞是什麼意思？（名詞小辭典）"):
                for k_, v_ in {
                    "第 1～3 號得分手（本頁）": ("這一季這隊例行賽場均得分前 3 名（至少上場 20 場）；季後賽也看同一批人，不會因為季後賽得分變多就換人",
                                         "依例行賽場均得分排名"),
                    "得分佔全隊比例": ("這一輪全隊的得分裡，他一個人得了幾成；缺陣的比賽算 0 分", "他這一輪的總得分 ÷ 全隊這一輪的總得分"),
                    "比自己例行賽變多少": ("每一輪都和他自己這一季的例行賽比，場均 30 分和 15 分的人才能放在一起看", "這一輪的數字 − 他這一季例行賽的數字"),
                    "其他晉級球隊": ("同一輪也贏下系列賽的球隊；被淘汰的球隊投不進本來就是輸的原因之一，和冠軍比不公平", "這一輪贏 4 場的球隊（不含冠軍）"),
                }.items():
                    TERMS.setdefault(k_, v_)
                term_table(["第 1～3 號得分手（本頁）", "得分佔全隊比例", "比自己例行賽變多少", "其他晉級球隊", "真實命中率", "相關係數 r"],
                           first_note="季後賽每一輪只有 4～7 場，單一球員起伏很大；所以每一條線都是很多隊的加權平均（命中率依出手數、得分佔比依場數、其他依上場場數）。")

            # ===== 2. 交叉驗證：頭號少得的分，第 2、3 號補上了嗎？ =====
            st.divider()
            slot2 = section("2　交叉驗證：頭號得分手少得的分，第 2、3 號補上了嗎？",
                            "每個點是一隊打的一輪（所有季後賽球隊），橫軸＝頭號得分手這一輪每場比例行賽多（右）或少（左）幾分、"
                            "縱軸＝第 2、3 號合計每場多幾分；★ 是冠軍。每場都用「球隊場數」算，缺陣的比賽算 0 分，所以頭號受傷缺陣也看得到", anchor="sup2")
            P = D.pivot_table(index=["season", "team_id", "abbreviation", "rnd", "champion", "games"],
                              columns="role", values="d_pts_tg", aggfunc="sum").reset_index()
            nm = D[D["scorer_rk"] == 1].set_index(["season", "team_id", "rnd"])["player_name"]
            if {"頭號", "第 2、3 號"}.issubset(P.columns):
                P = P.dropna(subset=["頭號", "第 2、3 號"])
                P = P[P["games"] >= 4]
            else:
                P = P.iloc[0:0]
            if len(P) < 5:
                insight(["資料不足：可以畫的系列賽不到 5 個。"], where=slot2)
            else:
                P["star"] = [nm.get((s_, t_, r_), "") for s_, t_, r_ in zip(P["season"], P["team_id"], P["rnd"])]
                P["lab"] = [f"{s_} {ALL_ZH.get(a_, a_)}　{SUP_ROUND[int(r_) - 1]}" for s_, a_, r_ in zip(P["season"], P["abbreviation"], P["rnd"])]
                xm, ym = P["頭號"].mean(), P["第 2、3 號"].mean()
                den = ((P["頭號"] - xm) ** 2).sum()
                b = ((P["頭號"] - xm) * (P["第 2、3 號"] - ym)).sum() / den if den > 0 else float("nan")
                a = ym - b * xm
                r_all = P["頭號"].corr(P["第 2、3 號"])
                fig = go.Figure()
                for is_c, nm_, c_, sym, sz in [(False, "其他球隊", "#c9c4d4", "circle", 7), (True, "冠軍", ACCENT, "star", 14)]:
                    q = P[P["champion"] == is_c]
                    fig.add_trace(go.Scatter(x=q["頭號"], y=q["第 2、3 號"], mode="markers", name=nm_,
                                             marker=dict(size=sz, symbol=sym, color=c_, line=dict(width=1, color=SURFACE)),
                                             customdata=q[["lab", "star"]].values,
                                             hovertemplate="%{customdata[0]}<br>頭號 %{customdata[1]}：每場 %{x:+.1f} 分"
                                                           "<br>第 2、3 號合計：每場 %{y:+.1f} 分<extra></extra>"))
                if pd.notna(b):
                    xs = [P["頭號"].min(), P["頭號"].max()]
                    fig.add_trace(go.Scatter(x=xs, y=[a + b * v for v in xs], mode="lines", name="趨勢線",
                                             line=dict(color=INK_2, width=1.5, dash="dot"), hoverinfo="skip"))
                fig.add_hline(y=0, line=dict(color=MUTED, width=1))
                fig.add_vline(x=0, line=dict(color=MUTED, width=1))
                fig.update_xaxes(title="頭號得分手：每場比例行賽多幾分", tickformat="+.0f", showgrid=True, gridcolor=GRID)
                fig.update_yaxes(title="第 2、3 號合計：每場多幾分", tickformat="+.0f")
                fig.update_layout(legend=dict(orientation="h", y=1.08, x=0))
                st.plotly_chart(style(fig, 440), width="stretch", config={"displayModeBar": False})
                Cn = P[P["champion"]]
                left = P[P["頭號"] < -3]
                more = "多" if pd.isna(b) or b <= 0 else "也少"
                lines = [f"{len(P)} 個「一隊一輪」裡，頭號得分手每場少 1 分，第 2、3 號合計平均{more} {abs(b):.2f} 分"
                         f"（r ＝ {r_all:+.2f}，{corr_word(r_all)}）。"]
                if len(left):
                    lines.append(f"頭號得分手每場少 3 分以上的 {len(left)} 輪裡，第 2、3 號合計平均每場 {left['第 2、3 號'].mean():+.1f} 分"
                                 f"（冠軍 {len(Cn[Cn['頭號'] < -3])} 輪）。")
                lines.append("讀法：點如果由左上往右下排，代表「頭號少、配角多」——有人補位；點如果貼著水平線，代表少掉的分沒人補。"
                             "斜率不到 −1 是正常的：頭號少得的分，也可能由第 4 號以後的球員或板凳補上。")
                back = (("後段成立" if r_all <= -0.3 else "後段不成立") + f"：r ＝ {r_all:+.2f}（門檻 −0.3）") if pd.notna(r_all) else "後段算不出來"
                insight(lines, where=slot2, check=back + "。")

            # ===== 3. 每一位冠軍：每一輪是誰得最多分 =====
            st.divider()
            slot3 = section("3　每一位冠軍：每一輪是誰得最多分？",
                            "一列一位冠軍、一欄一輪；格子寫這一輪前三號裡得分最多的人和他的每場得分。"
                            "淺紫＝頭號得分手自己、中紫＝第 2 號、深紫＝第 3 號", anchor="sup3")
            C = D[D["champion"]].copy()
            C["ppg_tg"] = C["pts"] / C["games"].where(C["games"] > 0)
            lead = (C.sort_values(["season", "rnd", "pts", "scorer_rk"], ascending=[True, True, False, True])
                    .drop_duplicates(["season", "rnd"]))
            seasons_c = sorted(lead["season"].unique())
            ab_by = lead.drop_duplicates("season").set_index("season")["abbreviation"]
            rows_lab = [f"{s_} {ALL_ZH.get(ab_by[s_], ab_by[s_])}" for s_ in seasons_c]
            Z = lead.pivot(index="season", columns="rnd", values="scorer_rk").reindex(index=seasons_c, columns=[1, 2, 3, 4])
            T = lead.assign(t=[f"{str(n).split(' ')[-1]}<br>{v:.1f}" for n, v in zip(lead["player_name"], lead["ppg_tg"])]) \
                .pivot(index="season", columns="rnd", values="t").reindex(index=seasons_c, columns=[1, 2, 3, 4]).fillna("")
            fig = go.Figure(go.Heatmap(
                z=Z.values, x=SUP_ROUND, y=rows_lab, zmin=1, zmax=3, showscale=False,
                colorscale=[[0, "#e1d6fa"], [0.5, "#8a63d9"], [1, "#4c2a96"]],
                text=T.values, texttemplate="%{text}", textfont=dict(size=11),
                xgap=2, ygap=2, hovertemplate="%{y}　%{x}<br>得分最多：%{text}<extra></extra>"))
            fig.update_xaxes(type="category", side="top")
            fig.update_yaxes(type="category", autorange="reversed")
            st.plotly_chart(style(fig, 80 + 34 * len(rows_lab)), width="stretch", config={"displayModeBar": False})
            n_all, n_sup = len(lead), int((lead["scorer_rk"] > 1).sum())
            by_r = lead[lead["scorer_rk"] > 1].groupby("rnd").size()
            lines = [f"{len(seasons_c)} 位冠軍、{n_all} 輪裡，有 <b>{n_sup}</b> 輪（{n_sup / max(n_all, 1):.0%}）得最多分的不是頭號得分手。"]
            if len(by_r):
                rr = int(by_r.idxmax())
                lines.append(f"最常由第 2、3 號帶頭的是「{SUP_ROUND[rr - 1]}」（{int(by_r.max())} 次）；"
                             f"有 {lead[lead['scorer_rk'] > 1]['season'].nunique()} 位冠軍至少一輪由第 2 或第 3 號得最多分。")
            insight(lines, where=slot3)
            with st.expander("看每一位冠軍每一輪的數字"):
                C = C.sort_values(["season", "rnd", "scorer_rk"])
                nice_table(pd.DataFrame({
                    "球季": C["season"], "冠軍": [ALL_ZH.get(a_, a_) for a_ in C["abbreviation"]], "_key": C["abbreviation"],
                    "輪": C["round"], "對手": [ALL_ZH.get(o_, o_) if isinstance(o_, str) else "-" for o_ in C.get("opp_abbr", pd.Series("-", index=C.index))],
                    "戰績": [f"{int(w_)}-{int(n_ - w_)}" for w_, n_ in zip(C["wins"], C["games"])],
                    "第幾號": [f"第 {int(r_)}" for r_ in C["scorer_rk"]], "球員": C["player_name"],
                    "上場": [f"{int(g_)} 場" for g_ in C["g"]],
                    "場均得分": [f"{fmt(a_, '.1f')}（例 {fmt(b_, '.1f')}）" for a_, b_ in zip(C["ppg"], C["ppg_reg"])],
                    "得分佔比": [f"{fmt(a_, '.0%')}（例 {fmt(b_, '.0%')}）" for a_, b_ in zip(C["share"], C["share_reg"])],
                    "命中率差": [fmt_d(v_, ".1%").replace(" 百分點", "") for v_ in C["d_ts"]],
                }), num_cols=("場均得分", "得分佔比", "命中率差"), signed_cols=("命中率差",), dot_col="冠軍", colors=TEAM_COLORS)


RELATED["二號與三號得分手"] = [("每一輪的球星", "只看頭號得分手，四輪怎麼變"), ("對手防守與球星", "頭號得分手掉，是不是因為對手會守"),
                        ("誰補上得分", "例行賽頭號得分手缺陣時，誰補上")]
SOURCES["二號與三號得分手"] = (
    "support_round_mv（預先算好的彙總表，docs/sql/2026-11-20_二號與三號得分手.sql，由 player_game_stats、team_games、games 算）、champions",
    "2006-07 起；季後賽四輪；全聯盟 30 隊",
    "第 1～3 號得分手＝這一季這隊例行賽場均得分前 3 名（至少上場 20 場）；第幾輪＝同一季季後賽依日期排好、對手換人就 +1；"
    "每一輪都和他自己這一季例行賽比；第 1 節只留冠軍和贏下這一輪的球隊，命中率依出手數、得分佔比依場數、其他依上場場數加權；"
    "第 2 節每場得分用球隊場數算（缺陣算 0 分），趨勢線是最小平方法直線。限制：一輪只有 4～7 場；看不出對手是不是真的包夾頭號得分手。")
'''


def main():
    if not os.path.exists(APP):
        print("找不到 app.py：請把這個檔案放在 C:\\basketball_research（和 app.py 同一個資料夾）再執行。")
        sys.exit(1)
    with open(APP, encoding="utf-8") as f:
        src = f.read()
    if f'if PAGE == "{PAGE}":' in src:
        print(f"已經有「{PAGE}」頁了，不用再加。")
        return
    anchor = '    ("自由探索", "球季趨勢"'
    end = "\nfinish_page()\n"
    if src.count(anchor) != 1 or end not in src:
        print("這份 app.py 的格式和預期不一樣（找不到 PAGES 裡的「球季趨勢」或最後的 finish_page()），沒有修改。請把 app.py 傳給我。")
        sys.exit(1)
    src = src.replace(anchor, PAGES_LINE + anchor, 1)
    i = src.rfind(end)
    src = src[:i] + "\n\n" + BLOCK.rstrip() + "\n\n" + src[i:]
    shutil.copyfile(APP, BACKUP)
    with open(APP, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    miss = [p for p in EARLIER if f'if PAGE == "{p}":' not in src]
    if miss:
        print(f"提醒：這份 app.py 裡還沒有這 {len(miss)} 頁：{'、'.join(miss)}（那幾天的補丁還沒跑，先跑或後跑都可以）。")
    print(f"完成：已加入「{PAGE}」頁（冠軍故事最後一頁）。原本的檔案備份在 {os.path.basename(BACKUP)}")
    print("記得先在 Supabase 執行 docs/sql/2026-11-20_二號與三號得分手.sql，再 streamlit run app.py。")


if __name__ == "__main__":
    main()
