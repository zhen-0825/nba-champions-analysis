-- =============================================================
-- 新增：每日戰報用的兩張表 + 一個球員本季平均檢視表
-- 用法：Supabase SQL Editor → ＋ → Create a new snippet → 整份貼上 → Run
--      出現「Potential issue detected」是因為有 drop policy，按 Run query 即可
-- 資料由 load_recap.py 寫入（每天 daily_update.py 會自動跑）
-- =============================================================

-- 1. 全聯盟每場比賽 × 每支球隊
create table if not exists recap_team_games (
  game_id      text   not null,
  team_id      bigint not null,
  season       text   not null,
  season_type  text   not null,           -- Regular Season / PlayIn / Playoffs
  game_date    date   not null,
  abbreviation text,                      -- 球隊縮寫，例如 LAL
  matchup      text,                      -- LAL vs. UTA（主場）／LAL @ UTA（客場）
  is_home      boolean,
  wl           text,                      -- W 或 L
  min          numeric,
  pts int, opp_pts int,                   -- 自己得分、對手得分
  fgm int, fga int, fg3m int, fg3a int, ftm int, fta int,
  oreb int, dreb int, reb int, ast int, stl int, blk int, tov int, pf int,
  plus_minus int,                         -- 淨勝分
  primary key (game_id, team_id)
);
create index if not exists idx_recap_team_date on recap_team_games(season, game_date);

-- 2. 全聯盟每場比賽 × 每位球員
create table if not exists recap_player_games (
  game_id      text   not null,
  player_id    bigint not null,
  season       text   not null,
  season_type  text   not null,
  game_date    date   not null,
  player_name  text,
  team_id      bigint,
  abbreviation text,
  matchup      text,
  wl           text,
  min          numeric,
  pts int, fgm int, fga int, fg3m int, fg3a int, ftm int, fta int,
  oreb int, dreb int, reb int, ast int, stl int, blk int, tov int, pf int,
  plus_minus int,
  primary key (game_id, player_id)
);
create index if not exists idx_recap_player_date on recap_player_games(season, game_date);

-- 3. 球員本季累計（用來判斷「今天比平常好多少」）
create or replace view recap_player_season
with (security_invoker = true) as
select season, player_id, team_id,
       max(player_name) as player_name, max(abbreviation) as abbreviation,
       count(*) as gp, sum(min) as min, sum(pts) as pts, sum(reb) as reb, sum(ast) as ast,
       sum(fga) as fga, sum(fta) as fta, sum(fg3m) as fg3m, max(game_date) as last_game
from recap_player_games
where season_type = 'Regular Season'
group by season, player_id, team_id;

-- 安全設定：所有人只能讀
alter table recap_team_games   enable row level security;
alter table recap_player_games enable row level security;
drop policy if exists "public read" on recap_team_games;
drop policy if exists "public read" on recap_player_games;
create policy "public read" on recap_team_games   for select to anon, authenticated using (true);
create policy "public read" on recap_player_games for select to anon, authenticated using (true);
grant select on recap_player_season to anon, authenticated;
