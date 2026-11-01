-- =============================================================
-- 新增：賽程表（每日戰報的「下一場預測」用）
-- 用法：Supabase SQL Editor → ＋ → Create a new snippet → 整份貼上 → Run
--      出現「Potential issue detected」是因為有 drop policy，按 Run query 即可
-- 資料由 load_recap.py 寫入（每天 daily_update.py 會自動跑）
-- =============================================================
create table if not exists recap_schedule (
  game_id      text primary key,
  season       text not null,
  game_date    date not null,            -- 美國比賽日
  home_team_id bigint,
  away_team_id bigint,
  home_abbr    text,                     -- 主隊縮寫
  away_abbr    text,                     -- 客隊縮寫
  status       text                      -- 例如 7:30 pm ET、Final
);
create index if not exists idx_recap_schedule_date on recap_schedule(season, game_date);

alter table recap_schedule enable row level security;
drop policy if exists "public read" on recap_schedule;
create policy "public read" on recap_schedule for select to anon, authenticated using (true);
