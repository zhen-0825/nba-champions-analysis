-- =============================================================
-- 新增：投籃分布、戰術使用、陣容組合、跑動距離（2016-17 起）
-- 用法：Supabase SQL Editor → ＋ → Create a new snippet → 整份貼上 → Run
--      出現「Potential issue detected」是因為有 drop policy，按 Run query 即可
-- 這幾張表的資料來自 NBA 不同的資料庫，可能出現我們 teams、players 表沒有的編號，
-- 所以不設外鍵，避免寫入失敗；查詢時一樣可以用 team_id、player_id 去 join。
-- =============================================================

-- 1. 投籃紀錄：每一次出手一筆（8 支冠軍隊）
create table if not exists shots (
  game_id        text     not null,
  game_event_id  int      not null,      -- 這場比賽中的第幾個事件
  season         text     not null,
  season_type    text     not null,
  game_date      date,
  team_id        bigint,
  player_id      bigint,
  player_name    text,
  period         smallint,               -- 第幾節（5 以上是延長賽）
  minutes_remaining smallint,            -- 該節剩幾分
  seconds_remaining smallint,            -- 該節剩幾秒
  action_type    text,                   -- 出手動作，例如 Jump Shot、Driving Layup
  shot_type      text,                   -- 2PT Field Goal / 3PT Field Goal
  zone_basic     text,                   -- 區域：Restricted Area、Mid-Range、Above the Break 3…
  zone_area      text,                   -- 左中右：Left Side(L)、Center(C)…
  zone_range     text,                   -- 距離帶：Less Than 8 ft.、24+ ft.…
  shot_distance  smallint,               -- 出手距離（英尺）
  loc_x          smallint,               -- 球場座標：籃框在 (0,0)，單位 0.1 英尺
  loc_y          smallint,
  made           boolean,                -- 有沒有進
  primary key (game_id, game_event_id)
);
create index if not exists idx_shots_team_season on shots(team_id, season);
create index if not exists idx_shots_player on shots(player_id);

-- 1b. 聯盟各區域平均命中率（和球隊比較用）
create table if not exists shot_zone_league (
  season      text not null,
  season_type text not null,
  zone_basic  text not null,
  zone_area   text not null,
  zone_range  text not null,
  fga numeric, fgm numeric, fg_pct numeric,
  primary key (season, season_type, zone_basic, zone_area, zone_range)
);

-- 2a. 球隊戰術使用（Synergy），進攻與防守
create table if not exists playtypes_team (
  season        text not null,
  season_type   text not null,
  team_id       bigint not null,
  play_type     text not null,           -- Isolation、PRBallHandler、Spotup…
  type_grouping text not null,           -- offensive 進攻 / defensive 防守
  gp numeric,
  poss numeric,                          -- 回合數
  poss_pct numeric,                      -- 這種戰術佔全部回合的比例（使用頻率）
  ppp numeric,                           -- 每回合得分（效率）
  pts numeric,
  fg_pct numeric, efg_pct numeric,
  tov_poss_pct numeric,                  -- 失誤回合比例
  score_poss_pct numeric,                -- 得分回合比例
  percentile numeric,                    -- 聯盟百分等級
  primary key (season, season_type, team_id, play_type, type_grouping)
);

-- 2b. 球員戰術使用（進攻端、例行賽）
create table if not exists playtypes_player (
  season      text not null,
  season_type text not null,
  player_id   bigint not null,
  player_name text,
  team_id     bigint not null,
  play_type   text not null,
  gp numeric, poss numeric, poss_pct numeric, ppp numeric, pts numeric,
  fg_pct numeric, efg_pct numeric, tov_poss_pct numeric, score_poss_pct numeric, percentile numeric,
  primary key (season, season_type, player_id, team_id, play_type)
);

-- 3. 5 人陣容組合（8 支冠軍隊）
create table if not exists lineups (
  season      text not null,
  season_type text not null,
  team_id     bigint not null,
  group_id    text not null,             -- 5 位球員編號串起來，例如 -201939-202691-…
  group_name  text,                      -- 5 位球員名字，例如 S. Curry - K. Thompson - …
  gp numeric, w numeric, l numeric,
  min numeric,                           -- 這 5 人同時在場的總分鐘
  pts numeric, fga numeric, fg3a numeric, fg3m numeric, ast numeric, tov numeric, reb numeric,
  plus_minus numeric,                    -- 同時在場時的淨勝分
  off_rating numeric, def_rating numeric, net_rating numeric, pace numeric, poss numeric,
  primary key (season, season_type, team_id, group_id)
);

-- 4. 跑動距離與速度（球員追蹤，每場平均）
create table if not exists tracking_speed (
  season      text not null,
  season_type text not null,
  entity      text not null,             -- player 球員 / team 球隊
  id          bigint not null,           -- 球員編號或球隊編號
  name        text,
  team_id     bigint,
  gp numeric, min numeric,
  dist_miles numeric,                    -- 每場跑動距離（英里）
  dist_miles_off numeric,                -- 進攻時
  dist_miles_def numeric,                -- 防守時
  avg_speed numeric,                     -- 平均速度（英里／小時）
  avg_speed_off numeric, avg_speed_def numeric,
  primary key (season, season_type, entity, id)
);

-- 安全設定：所有人只能讀
alter table shots            enable row level security;
alter table shot_zone_league enable row level security;
alter table playtypes_team   enable row level security;
alter table playtypes_player enable row level security;
alter table lineups          enable row level security;
alter table tracking_speed   enable row level security;

drop policy if exists "public read" on shots;
drop policy if exists "public read" on shot_zone_league;
drop policy if exists "public read" on playtypes_team;
drop policy if exists "public read" on playtypes_player;
drop policy if exists "public read" on lineups;
drop policy if exists "public read" on tracking_speed;

create policy "public read" on shots            for select to anon, authenticated using (true);
create policy "public read" on shot_zone_league for select to anon, authenticated using (true);
create policy "public read" on playtypes_team   for select to anon, authenticated using (true);
create policy "public read" on playtypes_player for select to anon, authenticated using (true);
create policy "public read" on lineups          for select to anon, authenticated using (true);
create policy "public read" on tracking_speed   for select to anon, authenticated using (true);
