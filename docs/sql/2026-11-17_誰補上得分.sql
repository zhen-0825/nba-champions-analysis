-- =============================================================
-- 2026-11-17　誰補上得分：頭號得分手缺陣時，隊友每場多得幾分？
--
-- 為什麼要這份 SQL：
--   網站要比較「頭號得分手有上場的比賽」和「他缺陣的比賽」裡，每一位隊友各得幾分。
--   要把 team_games（球隊打了哪幾場）、player_game_stats（每個人每一場）一場一場對起來，
--   幾十萬筆網站自己算太慢，所以請資料庫先算好，存成「預先算好的彙總表」star_fill_mv
--   （一隊一季一位球員一列，約一萬列，網站一下就讀完）。
--
-- 定義（和 11/14「頭號得分手缺陣」頁一樣）：
--   頭號得分手＝這一季在這隊「例行賽」場均得分最高、至少上場 20 場的球員
--   缺陣＝球隊有打這一場，但他沒有紀錄或上場 0 分鐘
--   季中被交易的球員：只算他替這隊打球期間（他第一場到最後一場之間）的比賽
--   只看例行賽
--
-- 這份 SQL 做兩件事：
--   1. 建立 star_fill_mv
--   2. 讓網站（公開金鑰）可以讀
--   每天自動重算：11/06 的 SQL 已經把 refresh_season_stats() 改成「所有 _mv 彙總表都重算」，
--   所以這張表也會自動跟著更新，不用再改函式。
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約幾十秒）
-- 不會刪除或修改任何原本的資料表；不需要改 load_to_supabase.py。
-- =============================================================

-- 1. 預先算好的彙總表
drop materialized view if exists star_fill_mv;
create materialized view star_fill_mv as
with pg as (                  -- 例行賽每一位球員每一場（空值當 0）
  select s.game_id, s.team_id, s.player_id, g.season, g.game_date,
         coalesce(s.min, 0) as min, coalesce(s.pts, 0) as pts,
         coalesce(s.fga, 0) as fga, coalesce(s.fta, 0) as fta
  from player_game_stats s
  join games g on g.game_id = s.game_id and g.season_type = 'Regular Season'
),
star as (                     -- 每隊每季的頭號得分手
  select distinct on (season, team_id) season, team_id, player_id as star_id, avg(pts) as star_ppg
  from pg
  where min > 0
  group by season, team_id, player_id
  having count(*) >= 20
  order by season, team_id, avg(pts) desc, player_id
),
span as (                     -- 他替這隊打球的期間（第一場到最後一場）
  select st.season, st.team_id, st.star_id, st.star_ppg, min(pg.game_date) as d0, max(pg.game_date) as d1
  from star st
  join pg on pg.season = st.season and pg.team_id = st.team_id and pg.player_id = st.star_id
  group by st.season, st.team_id, st.star_id, st.star_ppg
),
tg as (                       -- 這段期間球隊的每一場：他有沒有上場、輸贏
  select sp.season, sp.team_id, sp.star_id, sp.star_ppg, t.game_id, t.wl,
         exists (select 1 from player_game_stats p
                 where p.game_id = t.game_id and p.player_id = sp.star_id
                   and p.team_id = sp.team_id and coalesce(p.min, 0) > 0) as played
  from span sp
  join games g       on g.season = sp.season and g.season_type = 'Regular Season'
                    and g.game_date between sp.d0 and sp.d1
  join team_games t  on t.game_id = g.game_id and t.team_id = sp.team_id
),
tc as (                       -- 球隊在兩種比賽各打幾場、贏幾場
  select season, team_id,
         count(*) filter (where played)              as team_g_with,
         count(*) filter (where played and wl = 'W') as team_w_with,
         count(*) filter (where not played)              as team_g_without,
         count(*) filter (where not played and wl = 'W') as team_w_without
  from tg
  group by season, team_id
)
select tg.season, tg.team_id, tm.abbreviation,
       tg.star_id, sp.player_name as star_name, round(tg.star_ppg, 1) as star_ppg,
       pg.player_id, pl.player_name, (pg.player_id = tg.star_id) as is_star,
       tc.team_g_with, tc.team_w_with, tc.team_g_without, tc.team_w_without,
       count(*)       filter (where tg.played and pg.min > 0)     as g_with,
       coalesce(sum(pg.min) filter (where tg.played), 0)          as min_with,
       coalesce(sum(pg.pts) filter (where tg.played), 0)          as pts_with,
       coalesce(sum(pg.fga) filter (where tg.played), 0)          as fga_with,
       coalesce(sum(pg.fta) filter (where tg.played), 0)          as fta_with,
       count(*)       filter (where not tg.played and pg.min > 0) as g_without,
       coalesce(sum(pg.min) filter (where not tg.played), 0)      as min_without,
       coalesce(sum(pg.pts) filter (where not tg.played), 0)      as pts_without,
       coalesce(sum(pg.fga) filter (where not tg.played), 0)      as fga_without,
       coalesce(sum(pg.fta) filter (where not tg.played), 0)      as fta_without
from tg
join pg       on pg.game_id = tg.game_id and pg.team_id = tg.team_id
join tc       on tc.season = tg.season and tc.team_id = tg.team_id
join teams tm on tm.team_id = tg.team_id
left join players pl on pl.player_id = pg.player_id
left join players sp on sp.player_id = tg.star_id
group by tg.season, tg.team_id, tm.abbreviation, tg.star_id, sp.player_name, tg.star_ppg,
         pg.player_id, pl.player_name,
         tc.team_g_with, tc.team_w_with, tc.team_g_without, tc.team_w_without;

create unique index if not exists star_fill_mv_key
  on star_fill_mv (season, team_id, player_id);

-- 2. 網站可以讀（彙總表不能開 RLS，所以用 grant：只給「讀」）
grant select on star_fill_mv to anon, authenticated;

-- 執行完可以用這幾行確認：
-- select count(*) from star_fill_mv;                       -- 大約一萬列
-- select player_name, is_star, team_g_with, team_g_without,
--        round(pts_with::numeric / nullif(team_g_with, 0), 1)       as 有他時每場,
--        round(pts_without::numeric / nullif(team_g_without, 0), 1) as 缺陣時每場
-- from star_fill_mv
-- where abbreviation = 'GSW' and season = '2016-17'
-- order by pts_with desc;
--   -- 每一列是一位球員；is_star = true 的那一列是頭號得分手（缺陣時每場是 0）
