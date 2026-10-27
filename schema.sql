-- =============================================================
-- NBA 冠軍球隊數據庫：建表 SQL
-- 用法：整份貼到 Supabase 左側選單 SQL Editor → 按 Run
-- =============================================================

-- 1. 球隊（30 支 NBA 球隊）
create table if not exists teams (
  team_id      bigint primary key,      -- NBA 官方球隊編號，例如勇士 1610612744
  abbreviation text   not null,         -- 縮寫，例如 GSW
  full_name    text   not null,         -- 全名，例如 Golden State Warriors
  city         text                     -- 城市
);

-- 2. 歷年冠軍（哪一季、哪一隊奪冠）
create table if not exists champions (
  season  text   primary key,                       -- 球季，例如 2021-22
  team_id bigint not null references teams(team_id) -- 冠軍球隊
);

-- 3. 球員
create table if not exists players (
  player_id   bigint primary key,       -- NBA 官方球員編號
  player_name text   not null           -- 球員姓名
);

-- 4. 比賽（每場比賽一筆）
create table if not exists games (
  game_id     text primary key,         -- NBA 官方比賽編號，例如 0022500123
  game_date   date not null,            -- 比賽日期
  season      text not null,            -- 球季，例如 2025-26
  season_type text not null             -- Regular Season / PlayIn / Playoffs
);

-- 5. 球隊在每場比賽的結果（一場比賽 × 一支球隊 = 一筆）
create table if not exists team_games (
  game_id text   references games(game_id),
  team_id bigint references teams(team_id),
  matchup text,                         -- 對戰，例如 GSW vs. LAL（vs. 主場、@ 客場）
  is_home boolean,                      -- 是否為主場
  wl      text,                         -- 勝負：W 或 L
  primary key (game_id, team_id)
);

-- 6. 球員逐場數據（一場比賽 × 一位球員 = 一筆）
create table if not exists player_game_stats (
  game_id    text   references games(game_id),
  player_id  bigint references players(player_id),
  team_id    bigint references teams(team_id), -- 球員當時效力的球隊（交易過的球員會不同）
  min        numeric(5,2),             -- 上場時間（分鐘）
  pts        int,                      -- 得分
  fgm        int,                      -- 投籃命中
  fga        int,                      -- 投籃出手
  fg3m       int,                      -- 三分命中
  fg3a       int,                      -- 三分出手
  ftm        int,                      -- 罰球命中
  fta        int,                      -- 罰球出手
  oreb       int,                      -- 進攻籃板
  dreb       int,                      -- 防守籃板
  reb        int,                      -- 總籃板
  ast        int,                      -- 助攻
  stl        int,                      -- 抄截
  blk        int,                      -- 阻攻
  tov        int,                      -- 失誤
  pf         int,                      -- 犯規
  plus_minus int,                      -- 正負值
  primary key (game_id, player_id)
);

-- 索引：讓「依球隊」「依球季」查詢更快
create index if not exists idx_stats_team    on player_game_stats(team_id);
create index if not exists idx_games_season  on games(season);
create index if not exists idx_games_date    on games(game_date);

-- =============================================================
-- 安全設定（RLS）：所有人只能「讀」，不能改
-- 寫入資料由你電腦上的程式用 secret key 執行（secret key 不受 RLS 限制）
-- =============================================================
alter table teams             enable row level security;
alter table champions         enable row level security;
alter table players           enable row level security;
alter table games             enable row level security;
alter table team_games        enable row level security;
alter table player_game_stats enable row level security;

create policy "public read" on teams             for select to anon, authenticated using (true);
create policy "public read" on champions         for select to anon, authenticated using (true);
create policy "public read" on players           for select to anon, authenticated using (true);
create policy "public read" on games             for select to anon, authenticated using (true);
create policy "public read" on team_games        for select to anon, authenticated using (true);
create policy "public read" on player_game_stats for select to anon, authenticated using (true);
