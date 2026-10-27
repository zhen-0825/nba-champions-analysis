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

比較 2022～2026 五屆 NBA 冠軍（勇士、金塊、塞爾提克、雷霆、尼克）在 2012-13 ～ 2025-26 共 14 季的表現。

## 架構

```
NBA 官方數據（nba_api）
      │  load_to_supabase.py：依起訖日期抓取，寫入資料庫
      ▼
Supabase（PostgreSQL）：schema.sql 建表、views.sql 建彙總檢視表
      │  app.py：從資料庫讀取
      ▼
Streamlit 網頁：球季趨勢、球隊 × 球季交叉分析、冠軍球季比較、球員分析
```

## 檔案說明

| 檔案 | 用途 |
|---|---|
| `fetch_nba.py` | 向 NBA 官網抓取球員逐場數據，並存成本機快取 |
| `load_to_supabase.py` | 依起訖日期抓取資料，寫入 Supabase |
| `schema.sql` | 資料庫結構：6 張表與 RLS 安全規則 |
| `views.sql` | 彙總檢視表（球隊球季、球員球季） |
| `app.py` | Streamlit 網頁，從 Supabase 讀資料呈現 |
| `Dockerfile` | Hugging Face Spaces 部署設定 |

## 本機執行

1. `pip install -r requirements.txt`
2. 複製 `.env.example` 為 `.env`，填入 Supabase 金鑰
3. 寫入資料：`python load_to_supabase.py`
4. 開啟網頁：`streamlit run app.py`

資料來源：NBA 官方數據（nba_api）
