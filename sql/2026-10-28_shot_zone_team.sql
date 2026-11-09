-- =============================================================
-- 2026-10-28　投籃分區彙總檢視表 shot_zone_team
-- 用途：網站「投籃分布」分頁下方的「每季出手選擇 vs 聯盟」趨勢圖
-- 為什麼需要：shots 表一季就有約 7,000 筆，10 季 × 8 隊是幾十萬筆，
--            網頁每次都讀逐筆資料會很慢；檢視表讓資料庫先幫我們「分區加總」，
--            網頁只要讀幾百列。
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run
-- 這段 SQL 只「新增一個檢視表」，不會改動或刪除任何資料。
-- =============================================================

create or replace view shot_zone_team
with (security_invoker = true)   -- 用「查詢的人」的權限讀 shots，沿用 shots 的 RLS（public read）
as
select
  season,
  season_type,
  team_id,
  zone_basic,
  zone_area,
  count(*)                              as fga,     -- 出手次數
  sum(case when made then 1 else 0 end) as fgm,     -- 命中次數
  round(avg(loc_x)::numeric, 1)         as avg_x,   -- 這區出手的平均位置（畫圖用）
  round(avg(loc_y)::numeric, 1)         as avg_y
from shots
group by season, season_type, team_id, zone_basic, zone_area;

-- 讓網站（publishable key = anon 角色）可以讀這個檢視表
grant select on shot_zone_team to anon, authenticated;

-- 執行完可以用這段確認（應該看到每隊每季十幾個區域）：
-- select * from shot_zone_team where season = '2021-22' and season_type = 'Regular Season' order by team_id, fga desc;
