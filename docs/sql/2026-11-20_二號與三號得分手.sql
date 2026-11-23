-- =============================================================
-- 2026-11-20　二號與三號得分手：季後賽越往後，誰站出來？
--
-- 建立一張預先算好的彙總表 support_round_mv：
--   一隊 × 一季 × 季後賽第幾輪 × 隊內第幾號得分手（1、2、3）＝ 一列（約 1,800 列）
--   「第幾號得分手」＝這一季在這隊「例行賽」場均得分排名（至少上場 20 場），季後賽也看同一批人。
--   每一列有：這一輪他上了幾場、得幾分、出手、罰球、上場分鐘；全隊這一輪得幾分；
--             以及他自己這一季例行賽的同樣數字（當作基準）、全隊例行賽總得分。
--   「第幾輪」＝同一季季後賽依日期排好，對手換人就 +1（和 11/18 每一輪的球星同一個方法）。
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（大約幾十秒）
-- 不會刪除或修改任何原本的資料表。
-- 季後賽期間（4～6 月）想更新這張表時，在 SQL Editor 執行：
--   refresh materialized view support_round_mv;
-- （它只看季後賽，例行賽期間內容不會變，所以沒有加進每天自動重算的函式）
-- =============================================================

drop materialized view if exists support_round_mv;

create materialized view support_round_mv as
with pg as (            -- 球員逐場（只要例行賽、季後賽）
  select p.game_id, p.player_id, p.team_id, g.season, g.season_type,
         coalesce(p.min, 0) as min, coalesce(p.pts, 0) as pts,
         coalesce(p.fga, 0) as fga, coalesce(p.fta, 0) as fta
  from player_game_stats p
  join games g on g.game_id = p.game_id
  where g.season_type in ('Regular Season', 'Playoffs')
),
reg as (                -- 每位球員在每隊每季的例行賽合計（至少上場 20 場）
  select season, team_id, player_id,
         count(*) as reg_g, sum(min) as reg_min, sum(pts) as reg_pts,
         sum(fga) as reg_fga, sum(fta) as reg_fta, avg(pts) as reg_ppg
  from pg
  where season_type = 'Regular Season' and min > 0
  group by season, team_id, player_id
  having count(*) >= 20
),
top3 as (               -- 隊內例行賽場均得分前 3 名
  select * from (
    select reg.*, row_number() over (partition by season, team_id
                                     order by reg_ppg desc, player_id) as scorer_rk
    from reg
  ) x
  where scorer_rk <= 3
),
team_reg as (           -- 全隊例行賽總得分（得分佔比的基準）
  select season, team_id, sum(pts) as team_reg_pts
  from pg
  where season_type = 'Regular Season'
  group by season, team_id
),
po as (                 -- 季後賽每一場：同一場的另一隊就是對手
  select tg.game_id, tg.team_id, tg.wl, g.season, g.game_date, o.team_id as opp_id
  from team_games tg
  join games g      on g.game_id = tg.game_id and g.season_type = 'Playoffs'
  join team_games o on o.game_id = tg.game_id and o.team_id <> tg.team_id
),
po2 as (
  select po.*,
         case when opp_id is distinct from lag(opp_id) over (partition by team_id, season order by game_date, game_id)
              then 1 else 0 end as new_series
  from po
),
po3 as (
  select po2.*, sum(new_series) over (partition by team_id, season order by game_date, game_id) as rnd
  from po2
),
rnd_team as (           -- 每一隊每一輪：對手、場數、勝場
  select r.season, r.team_id, r.rnd, max(r.opp_id) as opp_id,
         count(*) as games, count(*) filter (where r.wl = 'W') as wins
  from po3 r
  where r.rnd <= 4
  group by r.season, r.team_id, r.rnd
),
rnd_pts as (            -- 全隊這一輪的總得分（所有球員加起來）
  select r.season, r.team_id, r.rnd, sum(x.pts) as team_pts
  from po3 r
  join pg x on x.game_id = r.game_id and x.team_id = r.team_id
  where r.rnd <= 4
  group by r.season, r.team_id, r.rnd
),
sc as (                 -- 前 3 號得分手在每一輪的數字（沒上場的比賽算 0）
  select r.season, r.team_id, r.rnd, t.player_id, t.scorer_rk,
         count(x.game_id) filter (where x.min > 0) as g,
         coalesce(sum(x.min), 0) as min, coalesce(sum(x.pts), 0) as pts,
         coalesce(sum(x.fga), 0) as fga, coalesce(sum(x.fta), 0) as fta
  from po3 r
  join top3 t    on t.season = r.season and t.team_id = r.team_id
  left join pg x on x.game_id = r.game_id and x.player_id = t.player_id and x.team_id = r.team_id
  where r.rnd <= 4
  group by r.season, r.team_id, r.rnd, t.player_id, t.scorer_rk
)
select sc.season, sc.team_id, tm.abbreviation, sc.rnd,
       rt.opp_id, op.abbreviation as opp_abbr, rt.games, rt.wins, rp.team_pts,
       sc.scorer_rk, sc.player_id, pl.player_name,
       sc.g, sc.min, sc.pts, sc.fga, sc.fta,
       t3.reg_g, t3.reg_min, t3.reg_pts, t3.reg_fga, t3.reg_fta,
       tr.team_reg_pts
from sc
join rnd_team rt on rt.season = sc.season and rt.team_id = sc.team_id and rt.rnd = sc.rnd
join rnd_pts rp  on rp.season = sc.season and rp.team_id = sc.team_id and rp.rnd = sc.rnd
join top3 t3     on t3.season = sc.season and t3.team_id = sc.team_id and t3.player_id = sc.player_id
join team_reg tr on tr.season = sc.season and tr.team_id = sc.team_id
join teams tm    on tm.team_id = sc.team_id
left join teams op on op.team_id = rt.opp_id
left join players pl on pl.player_id = sc.player_id;

create unique index if not exists support_round_mv_key
  on support_round_mv (season, team_id, rnd, scorer_rk);

-- 網站（公開金鑰）只能讀
grant select on support_round_mv to anon, authenticated;
notify pgrst, 'reload schema';

-- 執行完可以用這兩行確認：
-- select count(*) from support_round_mv;                                   -- 大約 1,700～1,900
-- select rnd, count(*) from support_round_mv group by rnd order by rnd;    -- 第 1 輪最多、第 4 輪最少（每季 2 隊 × 3 人）
