-- =============================================================
-- 2026-11-15　輸球時的球星：頭號得分手在「贏球場」和「輸球場」各得幾分、隊友各得幾分
--
-- 為什麼要這份 SQL：
--   網站要比較「冠軍輸球時，是頭號得分手掉比較多，還是隊友掉比較多」，
--   需要把 player_game_stats（幾十萬筆球員逐場）和 team_games（每場輸贏）一場一場對起來。
--   網站自己算太慢，所以請資料庫先算好，存成預先算好的彙總表 star_wl_mv
--   （一隊一季一種比賽 × 贏／輸，約 2,500 列）。
--
-- 這份 SQL 做兩件事：
--   1. 建立 star_wl_mv
--   2. 讓網站（公開金鑰）可以讀
--   （每天自動重算不用改：11/06 那份 SQL 已經讓 refresh_season_stats() 重算所有 _mv 結尾的表）
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約幾十秒）
-- 不會刪除或修改任何原本的資料表；不需要改 load_to_supabase.py。
-- =============================================================

-- 1. 預先算好的彙總表
drop materialized view if exists star_wl_mv;
create materialized view star_wl_mv as
with pg as (                  -- 每位球員每一場，貼上比賽類型、球季和這一場的輸贏
  select s.game_id, s.team_id, s.player_id, gm.season, gm.season_type, tg.wl,
         coalesce(s.min, 0) as min, coalesce(s.pts, 0) as pts,
         coalesce(s.fga, 0) as fga, coalesce(s.fta, 0) as fta
  from player_game_stats s
  join games gm      on gm.game_id = s.game_id
  join team_games tg on tg.game_id = s.game_id and tg.team_id = s.team_id
  where gm.season_type in ('Regular Season', 'Playoffs') and tg.wl in ('W', 'L')
),
star as (                     -- 頭號得分手：這一季在這隊「例行賽」場均得分最高、至少上場 20 場
  select distinct on (season, team_id) season, team_id, player_id, avg(pts) as star_ppg
  from pg
  where season_type = 'Regular Season' and min > 0
  group by season, team_id, player_id
  having count(*) >= 20
  order by season, team_id, avg(pts) desc, player_id
),
team_game as (                -- 一隊一場一列：全隊得分、出手、罰球
  select game_id, team_id, sum(pts) as team_pts, sum(fga) as team_fga, sum(fta) as team_fta
  from pg
  group by game_id, team_id
)
select st.team_id, tm.abbreviation, p.season, p.season_type, p.wl,
       st.player_id, pl.player_name, round(st.star_ppg, 2) as star_ppg,
       count(*)          as games,        -- 他有上場的比賽（贏或輸）
       sum(p.pts)        as star_pts,
       sum(p.fga)        as star_fga,
       sum(p.fta)        as star_fta,
       sum(p.min)        as star_min,
       sum(t.team_pts)   as team_pts,
       sum(t.team_fga)   as team_fga,
       sum(t.team_fta)   as team_fta
from star st
join pg p         on p.season = st.season and p.team_id = st.team_id
                 and p.player_id = st.player_id and p.min > 0      -- 只算他有上場的比賽
join team_game t  on t.game_id = p.game_id and t.team_id = p.team_id
join teams tm     on tm.team_id = st.team_id
join players pl   on pl.player_id = st.player_id
group by st.team_id, tm.abbreviation, p.season, p.season_type, p.wl,
         st.player_id, pl.player_name, st.star_ppg;

create unique index if not exists star_wl_mv_key
  on star_wl_mv (team_id, season, season_type, wl);

-- 2. 網站可以讀
grant select on star_wl_mv to anon, authenticated;

-- 執行完可以用這幾行確認：
-- select count(*) from star_wl_mv;                       -- 大約 2,500 列
-- select season, abbreviation, player_name, season_type, wl, games,
--        round(star_pts::numeric / games, 1)                 as 球星場均,
--        round((team_pts - star_pts)::numeric / games, 1)    as 隊友場均
-- from star_wl_mv
-- where abbreviation = 'GSW' and season = '2016-17'
-- order by season_type desc, wl desc;
--   -- 4 列：例行賽 W／L、季後賽 W／L（2016-17 季後賽 16 勝 1 敗）
