-- =============================================================
-- 2026-11-14　頭號得分手缺陣：每隊每季「頭號得分手有上場」和「缺陣」的比賽各贏幾場
--
-- 為什麼要這份 SQL：
--   要知道頭號得分手哪幾場沒上場，得把 team_games（球隊每一場）和 player_game_stats（球員每一場）
--   一場一場對起來，幾十萬筆資料網站自己算太慢，所以請資料庫先算好，
--   存成「預先算好的彙總表」star_absence_mv（一隊一季一列，約 600 列，網站一下就讀完）。
--
-- 怎麼算：
--   1. 頭號得分手＝這一季例行賽「在這一隊」場均得分最高、至少上場 20 場的球員
--   2. 有上場＝這一場有他的逐場紀錄、而且上場分鐘 > 0；缺陣＝球隊有打、他沒有上場
--   3. 季中被交易的球員：只算他「第一次到最後一次」替這隊上場之間的比賽（交易前、交易後的比賽不算缺陣）
--   只看例行賽；缺陣原因（受傷、休息、禁賽）資料庫沒有，分不出來。
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約幾十秒）
-- 不會刪除或修改任何原本的資料表；不需要改 load_to_supabase.py。
-- =============================================================

-- 1. 預先算好的彙總表
drop materialized view if exists star_absence_mv;
create materialized view star_absence_mv as
with ps as (                    -- 一位球員、一隊、一季一列（只算例行賽、有上場的比賽）
  select s.player_id, s.team_id, gm.season,
         count(*)        as gp,
         sum(s.pts)      as pts,
         min(gm.game_date) as first_d,
         max(gm.game_date) as last_d
  from player_game_stats s
  join games gm on gm.game_id = s.game_id
  where gm.season_type = 'Regular Season' and coalesce(s.min, 0) > 0
  group by s.player_id, s.team_id, gm.season
),
ps2 as (
  select ps.*,
         count(*) over (partition by player_id, season) as n_teams,     -- 這一季待過幾隊（> 1＝季中被交易）
         row_number() over (partition by team_id, season
                            order by pts::numeric / gp desc, gp desc) as rk
  from ps
  where gp >= 20
),
star as (select * from ps2 where rk = 1),
tg as (                         -- 球隊每一場例行賽
  select tg.team_id, tg.game_id, tg.wl, gm.season, gm.game_date
  from team_games tg
  join games gm on gm.game_id = tg.game_id
  where gm.season_type = 'Regular Season' and tg.wl in ('W', 'L')
),
g as (                          -- 頭號得分手在隊上期間的每一場，標出他有沒有上場
  select st.team_id, st.season, st.player_id, st.gp, st.pts, st.n_teams, tg.wl,
         exists (select 1 from player_game_stats p
                 where p.game_id = tg.game_id and p.player_id = st.player_id
                   and p.team_id = st.team_id and coalesce(p.min, 0) > 0) as played
  from star st
  join tg on tg.team_id = st.team_id and tg.season = st.season
         and (st.n_teams = 1 or tg.game_date between st.first_d and st.last_d)
)
select g.team_id, t.abbreviation, g.season, g.player_id, pl.player_name,
       max(g.gp)                                          as star_gp,
       round(max(g.pts)::numeric / max(g.gp), 1)          as star_ppg,
       max(g.n_teams) > 1                                 as traded,
       count(*) filter (where g.played)                   as with_g,
       count(*) filter (where g.played and g.wl = 'W')    as with_w,
       count(*) filter (where not g.played)               as without_g,
       count(*) filter (where not g.played and g.wl = 'W') as without_w
from g
join teams t    on t.team_id = g.team_id
join players pl on pl.player_id = g.player_id
group by g.team_id, t.abbreviation, g.season, g.player_id, pl.player_name;

create unique index if not exists star_absence_mv_key on star_absence_mv (team_id, season);

-- 2. 網站可以讀
grant select on star_absence_mv to anon, authenticated;

-- 3. 每天自動重算：所有 _mv 彙總表一起重算（和 11/06 那份相同；已經執行過也沒關係）
create or replace function refresh_season_stats()
returns void
language plpgsql
security definer
set search_path = public
set statement_timeout = '5min'
as $$
declare r record;
begin
  for r in select matviewname from pg_matviews where schemaname = 'public' loop
    execute format('refresh materialized view %I', r.matviewname);
  end loop;
end;
$$;
revoke execute on function refresh_season_stats() from public, anon, authenticated;
grant execute on function refresh_season_stats() to service_role;

-- 執行完可以用這幾行確認：
-- select count(*) from star_absence_mv;        -- 大約 600 列（30 隊 × 20 季，少數球季沒有人打滿 20 場）
-- select s.season, s.abbreviation, s.player_name, s.star_ppg, s.with_g, s.with_w, s.without_g, s.without_w
-- from star_absence_mv s join champions c on c.season = s.season and c.team_id = s.team_id
-- order by s.season;
--   -- 20 列（每位冠軍一列）；with_g + without_g 大約 82（縮短的球季少一點），without_g 多半是 0～20
