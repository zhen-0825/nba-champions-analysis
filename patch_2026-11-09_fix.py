# -*- coding: utf-8 -*-
"""
2026-11-09 修正：每日戰報「預測準不準」出現
pandas.errors.InvalidIndexError: Reindexing only valid with uniquely valued Index objects
原因：有幾場比賽的主客場標示是空的（或兩隊都被標成客隊，例如中立場地），
      同一場比賽在「客隊表」出現兩次，對答案時就分不出是哪一列。
修正：主客標示不完整時，改看對戰文字（LAL @ UTA → UTA 是主隊），每場比賽只留一個主隊、一個客隊。
用法（提示字元不用複製）：python patch_2026-11-09_fix.py
"""
import shutil
import sys

APP = "app.py"
OLD = '''    t = tg[["game_id", "is_home", "pts", "abbreviation"]].copy()
    t["is_home"] = t["is_home"].astype(bool)
    home = t[t["is_home"]].set_index("game_id")
    away = t[~t["is_home"]].set_index("game_id")
'''
NEW = '''    t = tg[[c for c in ["game_id", "is_home", "pts", "abbreviation", "matchup"] if c in tg]].copy()
    # 主客標示：空白（None）一律先當成 False，不能直接 astype(bool)
    t["is_home"] = t["is_home"].map(lambda v: str(v).strip().lower() in ("true", "t", "1"))
    bad = t.groupby("game_id")["is_home"].transform("sum") != 1    # 這場不是「剛好一個主隊」
    if bad.any() and "matchup" in t:
        host = t["matchup"].astype(str).str.extract(r"@\\s*(\\w+)")[0]   # 「LAL @ UTA」→ UTA 是主隊
        host = host.groupby(t["game_id"]).transform("first")
        t.loc[bad, "is_home"] = t.loc[bad, "abbreviation"] == host[bad]
    home = t[t["is_home"]].drop_duplicates("game_id").set_index("game_id")    # 每場只留一列，避免對答案時重複
    away = t[~t["is_home"]].drop_duplicates("game_id").set_index("game_id")
'''


def main():
    try:
        src = open(APP, encoding="utf-8").read()
    except FileNotFoundError:
        sys.exit("找不到 app.py：請在 C:\\\\basketball_research 資料夾裡執行這個檔案。")
    if "每場只留一列，避免對答案時重複" in src:
        print("這份 app.py 已經修正過了，不用再執行。")
        return
    if src.count(OLD) != 1:
        sys.exit("找不到要修正的那幾行，沒有修改任何東西。請把這段訊息貼給 Claude。")
    shutil.copy(APP, "app_備份_2026-11-09_fix.py")
    open(APP, "w", encoding="utf-8").write(src.replace(OLD, NEW))
    print("完成：已修正「預測準不準」的錯誤。原本的檔案備份在 app_備份_2026-11-09_fix.py")


if __name__ == "__main__":
    main()
