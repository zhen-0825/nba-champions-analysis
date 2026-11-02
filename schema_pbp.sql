-- =============================================================
-- 新增：逐回合紀錄（play-by-play）兩張表，給「每日戰報」的比賽走勢、關鍵時刻、今日戰報稿用
-- 用法：Supabase SQL Editor → ＋ → Create a new snippet → 整份貼上 → Run
--      出現「Potential issue detected」是因為有 drop policy，按 Run query 即可
--      這份可以重複執行，不會刪掉已經存的資料
-- 資料由 load_pbp.py 寫入（daily_update.py 每天會自動跑）
-- 容量：只存「得分的那一刻」（投進的球、罰進的球），一場約 120 筆，一整季約 15 萬筆（約 20～30 MB）
-- =============================================================

-- 1. 每一次得分（一場比賽 × 一次得分 = 一筆）
create table if not exists pbp_events (
  game_id       text    not null,
  action_number int     not null,          -- NBA 官方的動作編號（同一場裡由小到大）
  season        text    not null,
  season_type   text    not null,          -- Regular Season / PlayIn / Playoffs
  game_date     date    not null,          -- 美國比賽日
  period        int     not null,          -- 第幾節（5 以上是延長賽）
  clock_sec     numeric,                   -- 這一節還剩幾秒
  elapsed_sec   numeric,                   -- 從開賽算起過了幾秒（畫走勢圖用）
  team_id       bigint,
  team_abbr     text,
  player_id     bigint,
  player_name   text,
  action_type   text,                      -- 2PT 兩分、3PT 三分、FT 罰球
  points        int,                       -- 這一球幾分（1、2、3）
  score_home    int,                       -- 進球之後的比分（主隊）
  score_away    int,                       -- 進球之後的比分（客隊）
  is_clutch     boolean,                   -- 關鍵時刻：第四節或延長賽最後 5 分鐘、進球前分差 5 分以內
  description   text,                      -- 官方文字描述，例如 Curry 26' 3PT (12 PTS)
  primary key (game_id, action_number)
);
create index if not exists idx_pbp_events_date on pbp_events(season, game_date);

-- 2. 每一場比賽的走勢摘要（一場一筆，由 load_pbp.py 算好）
create table if not exists pbp_game_flow (
  game_id         text primary key,
  season          text not null,
  season_type     text not null,
  game_date       date not null,
  home_abbr       text,
  away_abbr       text,
  home_pts        int,
  away_pts        int,
  lead_changes    int,                     -- 領先互換幾次
  times_tied      int,                     -- 平手幾次
  home_max_lead   int,                     -- 主隊最多領先幾分
  away_max_lead   int,                     -- 客隊最多領先幾分
  comeback_team   text,                    -- 贏球的一方
  comeback_pts    int,                     -- 贏球的一方最多落後幾分（0＝一路領先）
  best_run_team   text,                    -- 這場最長的連續得分是哪一隊
  best_run_pts    int,                     -- 連續得幾分（對手 0 分）
  best_run_period int,                     -- 從第幾節開始
  clutch_game     boolean,                 -- 最後 5 分鐘分差還在 5 分以內＝關鍵時刻比賽
  home_periods    text,                    -- 每節得分，例如 28,30,25,27
  away_periods    text,
  score_check     boolean                  -- 逐回合加總的比分和官方比分一致嗎
);
create index if not exists idx_pbp_flow_date on pbp_game_flow(season, game_date);

-- 安全設定：所有人只能讀（寫入只有電腦上用 secret 金鑰的 load_pbp.py）
alter table pbp_events    enable row level security;
alter table pbp_game_flow enable row level security;
drop policy if exists "public read" on pbp_events;
drop policy if exists "public read" on pbp_game_flow;
create policy "public read" on pbp_events    for select to anon, authenticated using (true);
create policy "public read" on pbp_game_flow for select to anon, authenticated using (true);
