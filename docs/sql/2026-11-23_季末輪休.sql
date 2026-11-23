-- =============================================================
-- 2026-11-23　「季末輪休」頁需要的彙總表（materialized view）
--
-- 問題：例行賽最後 10 場，強隊是不是真的讓主力休息？
-- 為什麼要先算好：要知道「每一場」前 3 號主力有沒有上場，得看 player_game_stats 每一筆，
--   網站一頁一頁讀太慢，所以請資料庫先算成「一隊 × 一季 × 兩段（前面／最後 10 場）一列」（約 1,200 列）。
--
-- 這份 SQL 做兩件事：
--   1. 建立彙總表 rest_end_mv（如果已經建過，會先刪掉再重建）
--   2. 開放網站（公開金鑰）讀取
-- 只算「已經打完的球季」（有季後賽比賽的球季），所以例行賽期間不會變，不需要每天重算；
-- 每年季後賽開打後想更新，在 SQL Editor 跑：
--   set enable_nestloop = off; refresh materialized view rest_end_mv; reset enable_nestloop;
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（大約十幾秒到一分鐘）
-- 不會刪除或修改任何原始資料。
-- =============================================================

drop materialized view if exists rest_end_mv;

-- 這張表的中間步驟很多，資料庫有時會選到很慢的算法（一筆一筆對），先請它改用「整批對」
set enable_nestloop = off;

create materialized view rest_end_mv as
with done as (                                  -- 打完的球季：已經有季後賽比賽
  select distinct season from games where season_type = 'Playoffs'
),
rg as (                                         -- 例行賽每一隊每一場：倒數第幾場
  select tg.game_id, tg.team_id, g.season, g.game_date,
         (tg.wl = 'W')::int as win,
         row_number() over (partition by g.season, tg.team_id order by g.game_date desc, tg.game_id desc) as from_end,
         count(*)     over (partition by g.season, tg.team_id) as n_games
  from team_games tg
  join games g on g.game_id = tg.game_id
  where g.season_type = 'Regular Season' and g.season in (select season from done)
),
pg as (                                         -- 有上場的球員（上場 0 分鐘不算）
  select s.game_id, s.team_id, s.player_id, s.min, rg.season, rg.game_date
  from player_game_stats s
  join rg on rg.game_id = s.game_id and rg.team_id = s.team_id
  where coalesce(s.min, 0) > 0
),
tot as (                                        -- 每位球員在這一隊這一季：總分鐘、場數、第一場與最後一場
  select season, team_id, player_id, sum(min) as min_tot, count(*) as gp,
         min(game_date) as first_d, max(game_date) as last_d
  from pg group by season, team_id, player_id
),
core as (                                       -- 前 3 號主力：這一季替這隊上場總分鐘最多的 3 人（至少 20 場）
  select * from (
    select tot.*, row_number() over (partition by season, team_id order by min_tot desc, player_id) as rk
    from tot where gp >= 20
  ) x where rk <= 3
),
moved as (                                      -- 被交易走的主力：之後又替別隊上場，離隊後的比賽不算缺陣
  select distinct c.season, c.team_id, c.player_id
  from core c
  join pg p2 on p2.player_id = c.player_id and p2.season = c.season and p2.team_id <> c.team_id
  where p2.game_date > c.last_d
),
cg as (                                         -- 每一場 × 每位主力：有沒有上場、上場幾分鐘
  select rg.game_id, rg.team_id, c.player_id, (p.player_id is not null) as played, coalesce(p.min, 0) as min
  from rg
  join core c on c.season = rg.season and c.team_id = rg.team_id
  left join moved m on m.season = c.season and m.team_id = c.team_id and m.player_id = c.player_id
  left join pg p on p.game_id = rg.game_id and p.team_id = rg.team_id and p.player_id = c.player_id
  where rg.game_date >= c.first_d                         -- 加入球隊以前的比賽不算
    and (m.player_id is null or rg.game_date <= c.last_d)  -- 被交易走以後的比賽不算
),
gcore as (
  select game_id, team_id,
         count(*)                               as n_core,
         count(*) filter (where not played)     as n_out,
         count(*) filter (where played)         as n_played,
         sum(min) filter (where played)         as core_min
  from cg group by game_id, team_id
),
gteam as (                                      -- 每場上場人數
  select game_id, team_id, count(*) as n_used from pg group by game_id, team_id
),
sw as (                                         -- 整季勝率
  select season, team_id, avg(win)::numeric as season_win from rg group by season, team_id
),
opp as (                                        -- 同一場的另一隊＝對手
  select a.game_id, a.team_id, b.team_id as opp_id
  from team_games a join team_games b on b.game_id = a.game_id and b.team_id <> a.team_id
),
po as (                                         -- 有進季後賽的隊季
  select distinct g.season, tg.team_id from team_games tg join games g on g.game_id = tg.game_id
  where g.season_type = 'Playoffs'
)
select rg.season, rg.team_id, t.abbreviation,
       case when rg.from_end <= 10 then '最後10場' else '前面' end      as seg,
       max(sw.season_win)                                                as season_win,
       bool_or(po.team_id is not null)                                   as playoff,
       count(*)                                                          as games,
       sum(rg.win)                                                       as wins,
       coalesce(sum(gc.n_core), 0)                                       as core_slots,   -- 主力「應該上場」的人次
       coalesce(sum(gc.n_out), 0)                                        as core_out,     -- 其中缺陣的人次
       count(*) filter (where coalesce(gc.n_out, 0) = 0)                 as games_full,   -- 3 位主力都上場的場數
       coalesce(sum(rg.win) filter (where coalesce(gc.n_out, 0) = 0), 0) as wins_full,
       round(sum(gc.core_min) / nullif(sum(gc.n_played), 0), 2)          as core_min,     -- 主力有上場時，平均每人幾分鐘
       round(avg(gt.n_used), 2)                                          as used,         -- 每場上場人數
       round(avg(osw.season_win), 4)                                     as opp_win       -- 對手整季勝率（平均）
from rg
join teams t       on t.team_id = rg.team_id
join sw            on sw.season = rg.season and sw.team_id = rg.team_id
left join po       on po.season = rg.season and po.team_id = rg.team_id
left join gcore gc on gc.game_id = rg.game_id and gc.team_id = rg.team_id
left join gteam gt on gt.game_id = rg.game_id and gt.team_id = rg.team_id
left join opp o    on o.game_id = rg.game_id and o.team_id = rg.team_id
left join sw osw   on osw.season = rg.season and osw.team_id = o.opp_id
where rg.n_games >= 40
group by rg.season, rg.team_id, t.abbreviation, seg;

create unique index if not exists rest_end_mv_key on rest_end_mv (season, team_id, seg);

grant select on rest_end_mv to anon, authenticated;
reset enable_nestloop;

-- 執行完可以用這幾行確認：
-- select seg, count(*) from rest_end_mv group by seg;          -- 兩段列數一樣，約各 600 列
-- select season, abbreviation, seg, games, wins, core_out, core_slots, games_full, core_min, used
-- from rest_end_mv where abbreviation = 'GSW' and season = '2021-22' order by seg;
