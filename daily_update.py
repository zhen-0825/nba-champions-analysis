"""
每日自動更新：抓「進行中這一季」的最新比賽數據，寫進 Supabase

平常由 Windows 工作排程器每天執行（daily_update.bat → 這支程式），也可以手動執行：
  python daily_update.py             正式更新
  python daily_update.py --dry-run   試跑：只抓資料，不寫進資料庫

會依序執行：
  1. load_to_supabase.py --start <本季開始日>   八隊球員逐場數據、全聯盟球隊數據
  2. load_extra.py --current                    本季的投籃、戰術、陣容、跑動數據
  3. load_to_supabase.py --next 2               再加入 2 支還沒載入的球隊（20 季完整資料）
     想改成每天 1 隊：把下面 TEAMS_PER_DAY 改成 1；30 隊都載完後這一步會自動略過
每次的訊息會存在 logs/ 資料夾（只留最近 30 天）。
"""

import os
import subprocess
import sys
from datetime import date, datetime

from fetch_nba import season_of

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(HERE, "logs")
KEEP_LOGS = 30
TEAMS_PER_DAY = 2   # 每天新加入幾支球隊（1 或 2 比較安全，太多可能被 NBA 官網暫時擋掉）


def run(args, log):
    """執行另一支 Python 程式，訊息同時顯示在畫面上、寫進記錄檔"""
    log.write(f"\n>>> python {' '.join(args)}\n")
    print(f"\n>>> python {' '.join(args)}", flush=True)
    # PYTHONIOENCODING：中文訊息不變亂碼；PYTHONUNBUFFERED：訊息即時顯示，不要累積到最後才一次出現
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    proc = subprocess.Popen([sys.executable] + args, cwd=HERE, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    for line in proc.stdout:
        text = line.decode("utf-8", errors="replace")
        print(text, end="", flush=True)
        log.write(text)
    return proc.wait() == 0


def clean_old_logs():
    logs = sorted(f for f in os.listdir(LOG_DIR) if f.startswith("daily_"))
    for f in logs[:-KEEP_LOGS]:
        os.remove(os.path.join(LOG_DIR, f))


def main():
    dry = ["--dry-run"] if "--dry-run" in sys.argv else []
    season = season_of(date.today())
    start = f"{season[:4]}-08-01"          # 這一季的第一天（NBA 球季約 10 月開打）

    os.makedirs(LOG_DIR, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"daily_{datetime.now():%Y-%m-%d_%H%M}.log")
    with open(log_path, "w", encoding="utf-8") as log:
        title = f"===== 每日更新 {datetime.now():%Y-%m-%d %H:%M}　球季 {season} ====="
        print(title)
        log.write(title + "\n")
        ok1 = run(["load_to_supabase.py", "--start", start] + dry, log)
        ok2 = run(["load_extra.py", "--current"] + dry, log)
        ok3 = run(["load_to_supabase.py", "--next", str(TEAMS_PER_DAY)] + dry, log)
        result = "全部成功" if ok1 and ok2 and ok3 else "有部分失敗，請看上面的訊息或記錄檔"
        log.write(f"\n===== 結束：{result} =====\n")
        print(f"\n===== 結束：{result} =====\n記錄檔：{log_path}")
    clean_old_logs()


if __name__ == "__main__":
    main()
