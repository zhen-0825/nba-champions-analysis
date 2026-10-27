-- =============================================================
-- 新增：全聯盟球隊每季數據（30 隊 × 每季 × 例行賽／季後賽）
-- 用法：Supabase SQL Editor → ＋ → Create a new snippet → 整份貼上 → Run
-- =============================================================

create table if not exists league_team_seasons (
  season      text   not null,                  -- 球季，例如 2025-26
  season_type text   not null,                  -- Regular Season / Playoffs
  team_id     bigint not null references teams(team_id),

  -- 基本數據（整季累計）
  gp   int,  w    int,  l    int,              -- 場數、勝、負
  pts  int,  fgm  int,  fga  int,              -- 得分、投籃命中、投籃出手
  fg3m int,  fg3a int,  ftm  int,  fta int,    -- 三分、罰球
  oreb int,  dreb int,  reb  int,              -- 籃板
  ast  int,  tov  int,  stl  int,  blk int,    -- 助攻、失誤、抄截、阻攻
  plus_minus int,                              -- 整季淨勝分

  -- 進階數據（每 100 回合，跟比賽節奏無關，適合跨隊、跨季比較）
  off_rating numeric(6,2),                     -- 進攻效率：每 100 回合得分
  def_rating numeric(6,2),                     -- 防守效率：每 100 回合失分（越低越好）
  net_rating numeric(6,2),                     -- 淨效率 = 進攻 − 防守
  pace       numeric(6,2),                     -- 節奏：每 48 分鐘回合數
  ts_pct     numeric(5,3),                     -- 真實命中率
  efg_pct    numeric(5,3),                     -- 有效命中率
  ast_to     numeric(5,2),                     -- 助攻失誤比
  tm_tov_pct numeric(5,3),                     -- 失誤率：每回合失誤比例
  oreb_pct   numeric(5,3),                     -- 進攻籃板率
  dreb_pct   numeric(5,3),                     -- 防守籃板率

  -- 對手數據（防守端：對手對這隊打出的數據）
  opp_pts  int, opp_fgm int, opp_fga int,
  opp_fg3m int, opp_fg3a int, opp_tov int,

  primary key (season, season_type, team_id)
);

create index if not exists idx_league_season on league_team_seasons(season);

-- 安全設定：所有人只能讀
alter table league_team_seasons enable row level security;

drop policy if exists "public read" on league_team_seasons;
create policy "public read" on league_team_seasons
  for select to anon, authenticated using (true);
