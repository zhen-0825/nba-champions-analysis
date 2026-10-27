-- =============================================================
-- 彙總檢視表（view）：讓網頁讀「已經加總好」的資料，不用每次搬 10 萬筆
-- 用法：在 Supabase SQL Editor 開新的 snippet，整份貼上 → Run
--      這份可以重複執行，不會出錯
-- =============================================================

-- 1. 球員 × 球隊 × 球季 × 比賽類型 的加總數據（約幾千筆）
create or replace view player_season_stats
with (security_invoker = true) as        -- 讀取時照樣遵守 RLS 安全規則
select
  s.team_id,
  t.abbreviation,
  g.season,
  g.season_type,
  s.player_id,
  p.player_name,
  count(*)          as gp,               -- 出賽場數
  sum(s.min)        as min,
  sum(s.pts)        as pts,
  sum(s.fgm)        as fgm,
  sum(s.fga)        as fga,
  sum(s.fg3m)       as fg3m,
  sum(s.fg3a)       as fg3a,
  sum(s.ftm)        as ftm,
  sum(s.fta)        as fta,
  sum(s.reb)        as reb,
  sum(s.ast)        as ast,
  sum(s.stl)        as stl,
  sum(s.blk)        as blk,
  sum(s.tov)        as tov
from player_game_stats s
join games   g on g.game_id   = s.game_id
join teams   t on t.team_id   = s.team_id
join players p on p.player_id = s.player_id
group by s.team_id, t.abbreviation, g.season, g.season_type, s.player_id, p.player_name;


-- 2. 球隊 × 球季 × 比賽類型 的加總數據（約 150 筆）
create or replace view team_season_stats
with (security_invoker = true) as
with box as (                            -- 先把每場比賽的全隊數據加起來
  select game_id, team_id,
         sum(pts) as pts, sum(fgm) as fgm, sum(fga) as fga,
         sum(fg3m) as fg3m, sum(fg3a) as fg3a, sum(ftm) as ftm, sum(fta) as fta,
         sum(oreb) as oreb, sum(dreb) as dreb, sum(reb) as reb,
         sum(ast) as ast, sum(stl) as stl, sum(blk) as blk, sum(tov) as tov
  from player_game_stats
  group by game_id, team_id
)
select
  b.team_id,
  t.abbreviation,
  t.full_name,
  g.season,
  g.season_type,
  count(*)                          as games,   -- 比賽場數
  sum(case when tg.wl = 'W' then 1 else 0 end) as wins,
  sum(b.pts) as pts, sum(b.fgm) as fgm, sum(b.fga) as fga,
  sum(b.fg3m) as fg3m, sum(b.fg3a) as fg3a, sum(b.ftm) as ftm, sum(b.fta) as fta,
  sum(b.oreb) as oreb, sum(b.dreb) as dreb, sum(b.reb) as reb,
  sum(b.ast) as ast, sum(b.stl) as stl, sum(b.blk) as blk, sum(b.tov) as tov
from box b
join games      g  on g.game_id  = b.game_id
join teams      t  on t.team_id  = b.team_id
join team_games tg on tg.game_id = b.game_id and tg.team_id = b.team_id
group by b.team_id, t.abbreviation, t.full_name, g.season, g.season_type;


-- 開放網頁（publishable key）讀取這兩個檢視表
grant select on player_season_stats to anon, authenticated;
grant select on team_season_stats   to anon, authenticated;
