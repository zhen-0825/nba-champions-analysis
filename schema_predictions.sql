-- =============================================================
-- 新增：每天的預測紀錄（每日戰報的「預測準不準」用）
-- 用法：Supabase SQL Editor → ＋ → Create a new snippet → 整份貼上 → Run
--      出現「Potential issue detected」是因為有 drop policy，按 Run query 即可
-- 資料由 save_predictions.py 寫入（每天 daily_update.py 會自動跑）
-- =============================================================

-- 1. 每場比賽的預測（比賽開打前存下來，之後不再改）
create table if not exists recap_predictions (
  game_id    text primary key,
  season     text not null,
  game_date  date not null,              -- 美國比賽日
  home_abbr  text,
  away_abbr  text,
  p_home     numeric,                    -- 主隊勝率（0～1）
  margin     numeric,                    -- 預測分差（主隊 − 客隊）
  home_pts   numeric,                    -- 預估比分
  away_pts   numeric,
  factors    text,                       -- 影響因素（實力、主場、背靠背…）
  source     text,                       -- 當天存下／事後回推
  saved_at   timestamptz default now()
);
create index if not exists idx_recap_pred_date on recap_predictions(season, game_date);

-- 2. 球員表現的預測（每場兩隊各 2 位）
create table if not exists recap_player_predictions (
  game_id      text   not null,
  player_id    bigint not null,
  season       text   not null,
  game_date    date   not null,
  player_name  text,
  abbreviation text,
  opp_abbr     text,
  pts numeric, reb numeric, ast numeric, -- 預估得分、籃板、助攻
  pts_lo numeric, pts_hi numeric,        -- 得分合理範圍
  was_out      boolean,                  -- 預測時他上一場沒上場
  source       text,
  saved_at     timestamptz default now(),
  primary key (game_id, player_id)
);
create index if not exists idx_recap_ppred_date on recap_player_predictions(season, game_date);

-- 安全設定：所有人只能讀
alter table recap_predictions        enable row level security;
alter table recap_player_predictions enable row level security;
drop policy if exists "public read" on recap_predictions;
drop policy if exists "public read" on recap_player_predictions;
create policy "public read" on recap_predictions        for select to anon, authenticated using (true);
create policy "public read" on recap_player_predictions for select to anon, authenticated using (true);
