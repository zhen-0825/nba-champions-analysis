---
title: NBA Champions Analysis
emoji: 🏆
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 8501
pinned: false
---

# 🏆 NBA 冠軍球隊數據分析

比較 2019～2026 八屆 NBA 冠軍（暴龍、湖人、公鹿、勇士、金塊、塞爾提克、雷霆、尼克）近 20 季（2006-07 起）的表現，並以全聯盟 30 隊數據作為對照。

分析問題：
1. 奪冠的最佳因素是什麼？
2. 三分球時代是否造就了近年的冠軍？
3. 為什麼 2019～2026 連續 8 年冠軍都不同？

## 架構

```
NBA 官方數據（nba_api）
      │  load_to_supabase.py：依起訖日期抓取，寫入資料庫
      ▼
Supabase（PostgreSQL）：schema.sql、schema_league.sql 建表，views.sql 建彙總檢視表
      │  app.py：從資料庫讀取
      ▼
Streamlit 網頁：球季趨勢、球隊 × 球季交叉分析、冠軍球季比較、球員跨球季分析
```

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `fetch_nba.py` | 向 NBA 官網抓取球員逐場數據，並存成本機快取 |
| `load_to_supabase.py` | 依起訖日期抓取八隊球員逐場與全聯盟球隊數據，寫入 Supabase |
| `schema.sql` | 資料庫結構：6 張表與 RLS 安全規則 |
| `schema_league.sql` | 全聯盟球隊每季數據表（含攻守效率、對手數據） |
| `load_extra.py` | 抓取 2016-17 起的投籃分布、戰術使用（Synergy）、5 人陣容、跑動距離，寫入 Supabase |
| `schema_extra.sql` | 上述四種進階數據的資料表 |
| `daily_update.py` / `daily_update.bat` | 每日自動更新：抓進行中球季的最新數據寫進 Supabase |
| `setup_schedule.ps1` | 建立 Windows 工作排程，每天 15:30 自動執行更新 |
| `views.sql` | 彙總檢視表（球隊球季、球員球季） |
| `app.py` | Streamlit 網頁，從 Supabase 讀資料呈現 |

## 本機執行

1. `pip install -r requirements.txt`
2. 複製 `.env.example` 為 `.env`，填入 Supabase 金鑰
3. 寫入資料：`python load_to_supabase.py`
4. 開啟網頁：`streamlit run app.py`

資料來源：NBA 官方數據（nba_api）
