-- =============================================================
-- 2026-10-30　修正網站錯誤（postgrest APIError）＋預先算好的彙總表
--
-- 為什麼網站會壞：
--   team_season_stats、player_season_stats 是「檢視表」，網站每次讀，資料庫都要把
--   幾十萬筆球員逐場數據重新加總一次。每天加入新球隊後資料越來越多，加總時間超過了
--   網站（anon 角色）的時間上限 3 秒，資料庫就中斷查詢 → 網站顯示 APIError。
--
-- 這份 SQL 做三件事：
--   1. 先把網站讀取的時間上限從 3 秒放寬到 15 秒（網站馬上恢復）
--   2. 建立「預先算好的彙總表」（materialized view）：結果先存起來，網站直接讀，不用每次重算
--   3. 建立一個重新計算的函式，每天抓完資料後由 load_to_supabase.py 自動呼叫
--
-- 用法：Supabase → SQL Editor → ＋ New snippet → 整份貼上 → Run（第一次大約要幾十秒）
-- 不會刪除或修改任何原本的資料。
-- =============================================================

-- 1. 放寬網站讀取的時間上限
alter role anon set statement_timeout = '15s';
alter role authenticated set statement_timeout = '15s';
notify pgrst, 'reload config';

-- 2. 預先算好的彙總表（內容和原本的檢視表一模一樣，只是先存起來）
create materialized view if not exists team_season_stats_mv as
  select * from team_season_stats;
create unique index if not exists team_season_stats_mv_key
  on team_season_stats_mv (team_id, season, season_type);

create materialized view if not exists player_season_stats_mv as
  select * from player_season_stats;
create unique index if not exists player_season_stats_mv_key
  on player_season_stats_mv (team_id, season, season_type, player_id);

grant select on team_season_stats_mv, player_season_stats_mv to anon, authenticated;

-- 3. 重新計算的函式：只有寫入用的 secret key（service_role）可以呼叫，網站的公開金鑰不行
create or replace function refresh_season_stats()
returns void
language plpgsql
security definer
set search_path = public
set statement_timeout = '5min'
as $$
begin
  refresh materialized view team_season_stats_mv;
  refresh materialized view player_season_stats_mv;
end;
$$;
revoke execute on function refresh_season_stats() from public, anon, authenticated;
grant execute on function refresh_season_stats() to service_role;

-- 執行完可以用這兩行確認（應該看到筆數，而且很快就出來）：
-- select count(*) from team_season_stats_mv;
-- select count(*) from player_season_stats_mv;
