-- =============================================================
-- 2026-11-06　贏球與輸球：每隊每季「贏球場」和「輸球場」的平均數據
--
-- 為什麼要這份 SQL：
--   網站要比較「贏球那幾場」和「輸球那幾場」差在哪裡，需要每一場的全隊數據。
--   全隊每場數據要從 player_game_stats（幾十萬筆球員逐場）加總出來，網站自己算太慢，
--   所以請資料庫先算好，存成一張「預先算好的彙總表」team_wl_splits_mv
--   （一隊一季一種比賽 × 贏／輸，約幾千列，網站一下就讀完）。
--
-- 這份 SQL 做三件事：
--   1. 建立 team_wl_splits_mv（贏球場／輸球場各項數據的平均，以及整季每場的標準差）
--   2. 讓網站（公開金鑰）可以讀
--   3. 把每天自動重算的函式 refresh_season_stats() 改成「資料庫裡所有 _mv 彙總表都重算」，
--      之後再新增彙總表也不用再改這個函式（11/05 的 player_scoring_spread_mv 也會一起重算）
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約幾十秒）
-- 不會刪除或修改任何原本的資料表；不需要改 load_to_supabase.py。
-- =============================================================

-- 1. 預先算好的彙總表
drop materialized view if exists team_wl_splits_mv;
create materialized view team_wl_splits_mv as
with game_tot as (            -- 一隊一場一列：把這隊所有球員的逐場數據加起來
  select s.game_id, s.team_id,
         sum(s.pts) pts, sum(s.fgm) fgm, sum(s.fga) fga, sum(s.fg3m) fg3m, sum(s.fg3a) fg3a,
         sum(s.ftm) ftm, sum(s.fta) fta, sum(s.oreb) oreb, sum(s.dreb) dreb, sum(s.ast) ast,
         sum(s.stl) stl, sum(s.blk) blk, sum(s.tov) tov, sum(s.pf) pf
  from player_game_stats s
  group by s.game_id, s.team_id
),
g as (                        -- 每一場的各項指標
  select t.team_id, tm.abbreviation, gm.season, gm.season_type, tg.wl,
         t.pts / nullif(2 * (t.fga + 0.44 * t.fta), 0)::numeric        as ts,       -- 真實命中率
         t.fg3m::numeric / nullif(t.fg3a, 0)                            as fg3_pct,  -- 三分命中率
         (t.fgm - t.fg3m)::numeric / nullif(t.fga - t.fg3a, 0)          as fg2_pct,  -- 兩分命中率
         t.fta::numeric / nullif(t.fga, 0)                              as fta_rate, -- 罰球出手率
         t.tov::numeric as tov, t.oreb::numeric as oreb, t.dreb::numeric as dreb,
         t.ast::numeric as ast, t.stl::numeric as stl, t.blk::numeric as blk, t.pf::numeric as pf
  from game_tot t
  join team_games tg on tg.game_id = t.game_id and tg.team_id = t.team_id
  join games gm      on gm.game_id = t.game_id
  join teams tm      on tm.team_id = t.team_id
  where tg.wl in ('W', 'L')
),
g2 as (                       -- 每一場旁邊貼上「這隊這季每場的標準差」（window function）
  select g.*,
         stddev_samp(ts)       over w as sd_ts,
         stddev_samp(fg3_pct)  over w as sd_fg3_pct,
         stddev_samp(fg2_pct)  over w as sd_fg2_pct,
         stddev_samp(fta_rate) over w as sd_fta_rate,
         stddev_samp(tov)      over w as sd_tov,
         stddev_samp(oreb)     over w as sd_oreb,
         stddev_samp(dreb)     over w as sd_dreb,
         stddev_samp(ast)      over w as sd_ast,
         stddev_samp(stl)      over w as sd_stl,
         stddev_samp(blk)      over w as sd_blk,
         stddev_samp(pf)       over w as sd_pf
  from g
  window w as (partition by team_id, season, season_type)
)
select team_id, abbreviation, season, season_type, wl,
       count(*) as games,
       avg(ts) ts, avg(fg3_pct) fg3_pct, avg(fg2_pct) fg2_pct, avg(fta_rate) fta_rate,
       avg(tov) tov, avg(oreb) oreb, avg(dreb) dreb, avg(ast) ast, avg(stl) stl, avg(blk) blk, avg(pf) pf,
       max(sd_ts) sd_ts, max(sd_fg3_pct) sd_fg3_pct, max(sd_fg2_pct) sd_fg2_pct, max(sd_fta_rate) sd_fta_rate,
       max(sd_tov) sd_tov, max(sd_oreb) sd_oreb, max(sd_dreb) sd_dreb, max(sd_ast) sd_ast,
       max(sd_stl) sd_stl, max(sd_blk) sd_blk, max(sd_pf) sd_pf
from g2
group by team_id, abbreviation, season, season_type, wl;

create unique index if not exists team_wl_splits_mv_key
  on team_wl_splits_mv (team_id, season, season_type, wl);

-- 2. 網站可以讀
grant select on team_wl_splits_mv to anon, authenticated;

-- 3. 每天自動重算：所有 _mv 彙總表一起重算（只有 secret key 可以呼叫，網站的公開金鑰不行）
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
-- select count(*) from team_wl_splits_mv;                 -- 大約幾千列
-- select * from team_wl_splits_mv
--   where abbreviation = 'GSW' and season = '2021-22' and season_type = 'Regular Season';
--   -- 2 列：W（53 場左右）、L（29 場左右）；W 那列的 ts、fg3_pct 應該比 L 高
