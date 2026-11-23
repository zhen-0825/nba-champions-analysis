-- =============================================================
-- 2026-11-18　每一輪的球星：頭號得分手在季後賽每一輪（首輪 → 總冠軍賽）的表現
--
-- 為什麼要這份 SQL：
--   網站要比較「同一位頭號得分手，在首輪、次輪、分區決賽、總冠軍賽各打得怎樣」，
--   需要把 player_game_stats（幾十萬筆球員逐場）和每一場是第幾輪對起來。網站自己算太慢，
--   所以請資料庫先算好，存成「預先算好的彙總表」star_round_mv
--   （一隊一季一輪一列，約 1,200 列，網站一下就讀完）。
--
-- 定義（和 11/14～11/17 的頁面一樣）：
--   頭號得分手＝這一季在這隊「例行賽」場均得分最高、至少上場 20 場的球員（季後賽也看同一個人）
--   第幾輪＝同一季的季後賽依日期排好，對手換人就是下一輪（附加賽 PlayIn 是另一種比賽類型，不會算進來）
--   對手＝同一場比賽（同一個 game_id）裡的另一隊
--
-- 這份 SQL 做兩件事：
--   1. 建立 star_round_mv
--   2. 讓網站（公開金鑰）可以讀
--   每天自動重算不用另外設定：11/06 的 SQL 已經把 refresh_season_stats() 改成「所有 _mv 一起重算」。
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約幾十秒）
-- 不會刪除或修改任何原本的資料表；不需要改 load_to_supabase.py。
-- =============================================================

drop materialized view if exists star_round_mv;
create materialized view star_round_mv as
with pg as (                  -- 球員逐場，貼上球季與比賽類型
  select s.game_id, s.team_id, s.player_id, g.season, g.season_type,
         coalesce(s.min, 0) as min, coalesce(s.pts, 0) as pts,
         coalesce(s.fga, 0) as fga, coalesce(s.fta, 0) as fta
  from player_game_stats s
  join games g on g.game_id = s.game_id
),
star as (                     -- 每隊每季的頭號得分手＋他的例行賽總數（當作比較的基準）
  select distinct on (season, team_id) season, team_id, player_id,
         count(*) as reg_g, sum(pts) as reg_pts, sum(fga) as reg_fga, sum(fta) as reg_fta, sum(min) as reg_min
  from pg
  where season_type = 'Regular Season' and min > 0
  group by season, team_id, player_id
  having count(*) >= 20
  order by season, team_id, avg(pts) desc, player_id
),
po as (                       -- 每一場季後賽：哪一隊、對手是誰、輸贏
  select tg.game_id, tg.team_id, tg.wl, g.season, g.game_date, o.team_id as opp_id
  from team_games tg
  join games g      on g.game_id = tg.game_id and g.season_type = 'Playoffs'
  join team_games o on o.game_id = tg.game_id and o.team_id <> tg.team_id
),
po2 as (                      -- 對手換人＝新的一輪開始
  select po.*,
         case when opp_id is distinct from lag(opp_id) over (partition by team_id, season order by game_date, game_id)
              then 1 else 0 end as new_series
  from po
),
po3 as (                      -- 累加起來就是第幾輪（1＝首輪 … 4＝總冠軍賽）
  select po2.*, sum(new_series) over (partition by team_id, season order by game_date, game_id) as rnd
  from po2
),
team_pts as (                 -- 全隊每場季後賽得分
  select game_id, team_id, sum(pts) as team_pts
  from pg
  where season_type = 'Playoffs'
  group by game_id, team_id
)
select p.season, p.team_id, t.abbreviation, p.rnd::int as rnd,
       p.opp_id, ot.abbreviation as opp_abbr,
       count(*)                              as games,     -- 這個系列賽打了幾場
       count(*) filter (where p.wl = 'W')    as wins,      -- 贏了幾場（4＝贏下這一輪）
       st.player_id, pl.player_name,
       st.reg_g, st.reg_pts, st.reg_fga, st.reg_fta, st.reg_min,
       count(sg.game_id) filter (where sg.min > 0) as star_g,   -- 他在這一輪上場幾場
       coalesce(sum(sg.pts), 0)  as star_pts,
       coalesce(sum(sg.fga), 0)  as star_fga,
       coalesce(sum(sg.fta), 0)  as star_fta,
       coalesce(sum(sg.min), 0)  as star_min,
       coalesce(sum(tp.team_pts) filter (where sg.min > 0), 0) as team_pts_on   -- 他有上場那幾場的全隊得分
from po3 p
join star st        on st.season = p.season and st.team_id = p.team_id
join teams t        on t.team_id = p.team_id
join teams ot       on ot.team_id = p.opp_id
join players pl     on pl.player_id = st.player_id
left join pg sg     on sg.game_id = p.game_id and sg.team_id = p.team_id and sg.player_id = st.player_id
left join team_pts tp on tp.game_id = p.game_id and tp.team_id = p.team_id
group by p.season, p.team_id, t.abbreviation, p.rnd, p.opp_id, ot.abbreviation,
         st.player_id, pl.player_name, st.reg_g, st.reg_pts, st.reg_fga, st.reg_fta, st.reg_min;

create unique index if not exists star_round_mv_key on star_round_mv (season, team_id, rnd);

grant select on star_round_mv to anon, authenticated;

-- 執行完可以用這幾行確認：
-- select count(*) from star_round_mv;          -- 大約 1,200 列（20 季 × 約 30 個系列賽 × 2 隊）
-- select season, abbreviation, rnd, opp_abbr, wins || '-' || (games - wins) as 戰績, player_name, star_g, star_pts
--   from star_round_mv where season = '2021-22' and abbreviation = 'GSW' order by rnd;
--   -- 4 列：首輪 DEN、次輪 MEM、分區決賽 DAL、總冠軍賽 BOS，戰績都是 4-x，球員是 Stephen Curry
