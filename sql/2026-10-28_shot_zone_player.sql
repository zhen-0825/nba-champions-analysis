-- =============================================================
-- 2026-10-28　球員投籃分區彙總檢視表 shot_zone_player
-- 用途：網站「投籃分布」選了某位球員時，最下面的「每季出手選擇 vs 聯盟」趨勢圖
-- 和 shot_zone_team 一樣的做法，只是多了「球員」這一層分組
-- 用法：Supabase → SQL Editor → ＋ → 整份貼上 → Run
-- 只「新增一個檢視表」，不會改動或刪除任何資料
-- =============================================================

create or replace view shot_zone_player
with (security_invoker = true)
as
select
  season,
  season_type,
  team_id,
  player_id,
  max(player_name)                      as player_name,
  zone_basic,
  zone_area,
  count(*)                              as fga,
  sum(case when made then 1 else 0 end) as fgm
from shots
group by season, season_type, team_id, player_id, zone_basic, zone_area;

grant select on shot_zone_player to anon, authenticated;

-- 確認（應該看到 Curry 每季十幾個區域）：
-- select * from shot_zone_player where player_name = 'Stephen Curry' and season_type = 'Regular Season' order by season, fga desc;
