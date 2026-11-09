-- =============================================================
-- 2026-11-05　「得分穩定度」頁需要的彙總表（materialized view）
--
-- 為什麼要先算好：
--   要知道一位球員每場得分「忽高忽低」多少（標準差），就得看他每一場的得分。
--   player_game_stats 有幾十萬筆，網站一頁一頁讀太慢，所以請資料庫先算成
--   「一位球員 × 一隊 × 一季 × 比賽類型 一列」（約一萬多列），網站直接讀。
--
-- 這份 SQL 做三件事：
--   1. 建立彙總表 player_scoring_spread_mv（如果 11/04 已經建過，會先刪掉再重建，內容一樣是從原始資料算出來的）
--   2. 開放網站（公開金鑰）讀取
--   3. 更新每天自動重算的函式 refresh_season_stats()：
--      load_to_supabase.py 每天抓完資料會呼叫它，所以新球隊、新比賽會自動算進來
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約要十幾秒到一分鐘）
-- 不會刪除或修改任何原始資料（players、games、player_game_stats 都不動）。
-- =============================================================

drop materialized view if exists player_scoring_spread_mv;

create materialized view player_scoring_spread_mv as
with g as (                                   -- 每一場：誰、哪隊、哪季、得幾分（上場 0 分鐘的不算）
  select s.player_id, s.team_id, gm.season, gm.season_type, s.pts
  from player_game_stats s
  join games gm on gm.game_id = s.game_id
  where coalesce(s.min, 0) > 0 and s.pts is not null
),
a as (                                        -- 每位球員每季：場數、平均、標準差、最低、最高
  select player_id, team_id, season, season_type,
         count(*)                 as gp,
         avg(pts)::numeric        as ppg,
         stddev_samp(pts)::numeric as sd_pts,
         min(pts)                 as min_pts,
         max(pts)                 as max_pts
  from g
  group by player_id, team_id, season, season_type
)
select a.team_id, t.abbreviation, a.season, a.season_type, a.player_id, p.player_name,
       a.gp,
       round(a.ppg, 2)                                          as ppg,
       round(a.sd_pts, 2)                                       as sd_pts,
       count(*) filter (where g.pts < 0.6 * a.ppg)              as low_games,   -- 低迷場：不到自己平均的六成
       count(*) filter (where g.pts >= 1.5 * a.ppg)             as high_games,  -- 爆發場：自己平均的 1.5 倍以上
       a.min_pts, a.max_pts
from a
join g        using (player_id, team_id, season, season_type)  -- 把平均接回每一場，才能判斷這場是不是低迷場
join teams t   on t.team_id   = a.team_id
join players p on p.player_id = a.player_id
group by a.team_id, t.abbreviation, a.season, a.season_type, a.player_id, p.player_name,
         a.gp, a.ppg, a.sd_pts, a.min_pts, a.max_pts;

create unique index if not exists player_scoring_spread_mv_key
  on player_scoring_spread_mv (team_id, season, season_type, player_id);

grant select on player_scoring_spread_mv to anon, authenticated;

-- 每天自動重算（沿用 2026-10-30 的函式名稱，只是多重算一張表）
create or replace function refresh_season_stats()
returns void
language plpgsql
security definer
set search_path = public
set statement_timeout = '5min'
as $$
begin
  refresh materialized view team_season_stats_mv;
  refresh materialized view player_season_stats_mv;
  refresh materialized view player_scoring_spread_mv;
end;
$$;
revoke execute on function refresh_season_stats() from public, anon, authenticated;
grant execute on function refresh_season_stats() to service_role;

-- 執行完可以用這幾行確認：
-- select count(*) from player_scoring_spread_mv;                         -- 大約一萬多列
-- select season, abbreviation, player_name, gp, ppg, sd_pts, low_games
-- from player_scoring_spread_mv
-- where season = '2021-22' and abbreviation = 'GSW' and season_type = 'Regular Season'
-- order by ppg desc limit 5;                                             -- 第一列應該是 Stephen Curry
