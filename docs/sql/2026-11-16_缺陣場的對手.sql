-- 2026-11-16 缺陣場的對手：少了頭號得分手的那幾場，對手是不是比較弱？
-- 在 Supabase → SQL Editor 整份貼上 → Run。可以重跑（會先刪掉再重建）。
-- 建立 star_absence_opp_mv：一隊一季一列（例行賽），分「有他／缺陣」，
-- 各自的場數、勝場、對手平均淨效率，以及「對手比聯盟平均弱／強」兩組的場數與勝場。
-- 頭號得分手的定義和 11/14「頭號得分手缺陣」相同：這一季這隊例行賽場均得分最高、至少上場 20 場；
-- 季中被交易的球員只算他替這隊上場期間（第一場到最後一場之間）的比賽。

drop materialized view if exists star_absence_opp_mv;

create materialized view star_absence_opp_mv as
with pg as (                                  -- 例行賽每位球員每一場
  select p.game_id, p.team_id, p.player_id, p.pts, p.min, g.season, g.game_date
  from player_game_stats p
  join games g on g.game_id = p.game_id
  where g.season_type = 'Regular Season'
),
star as (                                     -- 每隊每季的頭號得分手
  select distinct on (season, team_id)
         season, team_id, player_id, avg(pts) as star_ppg,
         min(game_date) as first_d, max(game_date) as last_d
  from pg
  where coalesce(min, 0) > 0
  group by season, team_id, player_id
  having count(*) >= 20
  order by season, team_id, avg(pts) desc, player_id
),
tg as (                                       -- 每隊每一場＋對手是誰＋這是本季倒數第幾場
  select tg.game_id, tg.team_id, tg.wl, g.season, g.game_date, o.team_id as opp_id,
         row_number() over (partition by tg.team_id, g.season order by g.game_date desc) as from_end
  from team_games tg
  join games g      on g.game_id = tg.game_id and g.season_type = 'Regular Season'
  join team_games o on o.game_id = tg.game_id and o.team_id <> tg.team_id
),
lg as (                                       -- 每隊每季例行賽的淨效率與勝率
  select season, team_id, net_rating, w::numeric / nullif(gp, 0) as win_pct
  from league_team_seasons
  where season_type = 'Regular Season'
),
gm as (                                       -- 頭號得分手在隊期間的每一場：他有沒有上場、對手多強
  select tg.*, st.player_id, st.star_ppg, o.net_rating as opp_net,
         exists (select 1 from player_game_stats p
                 where p.game_id = tg.game_id and p.player_id = st.player_id
                   and p.team_id = st.team_id and coalesce(p.min, 0) > 0) as played
  from tg
  join star st on st.season = tg.season and st.team_id = tg.team_id
  left join lg o on o.season = tg.season and o.team_id = tg.opp_id
  where tg.game_date between st.first_d and st.last_d
)
select gm.season, gm.team_id, t.abbreviation, gm.player_id, pl.player_name,
       round(max(gm.star_ppg), 1)                                          as star_ppg,
       max(me.win_pct)                                                     as team_win_pct,
       bool_or(c.team_id is not null)                                      as champion,
       count(*) filter (where gm.played)                                   as with_g,
       count(*) filter (where gm.played and gm.wl = 'W')                   as with_w,
       avg(gm.opp_net) filter (where gm.played)                            as with_opp_net,
       count(*) filter (where not gm.played)                               as without_g,
       count(*) filter (where not gm.played and gm.wl = 'W')               as without_w,
       avg(gm.opp_net) filter (where not gm.played)                        as without_opp_net,
       count(*) filter (where not gm.played and gm.from_end <= 10)         as without_last10,
       -- 對手比聯盟平均弱（淨效率 < 0）／強（≥ 0）分開數：用來「只和同樣強弱的對手比」
       count(*) filter (where gm.played and gm.opp_net < 0)                as with_g_weak,
       count(*) filter (where gm.played and gm.opp_net < 0 and gm.wl = 'W')  as with_w_weak,
       count(*) filter (where gm.played and gm.opp_net >= 0)               as with_g_strong,
       count(*) filter (where gm.played and gm.opp_net >= 0 and gm.wl = 'W') as with_w_strong,
       count(*) filter (where not gm.played and gm.opp_net < 0)            as without_g_weak,
       count(*) filter (where not gm.played and gm.opp_net < 0 and gm.wl = 'W')  as without_w_weak,
       count(*) filter (where not gm.played and gm.opp_net >= 0)           as without_g_strong,
       count(*) filter (where not gm.played and gm.opp_net >= 0 and gm.wl = 'W') as without_w_strong
from gm
join teams t   on t.team_id = gm.team_id
join players pl on pl.player_id = gm.player_id
left join lg me on me.season = gm.season and me.team_id = gm.team_id
left join champions c on c.season = gm.season and c.team_id = gm.team_id
group by gm.season, gm.team_id, t.abbreviation, gm.player_id, pl.player_name;

create unique index if not exists star_absence_opp_mv_key on star_absence_opp_mv (season, team_id);

-- 網站（公開金鑰）只能讀
grant select on star_absence_opp_mv to anon, authenticated;

-- 之後每天想更新：在 SQL Editor 執行
--   refresh materialized view star_absence_opp_mv;
-- （這份沒有加進每天自動重算的函式，免得改到之前的 SQL；本季還在打，網站本來就不列入本季）

-- 執行完可以檢查：
--   select count(*) from star_absence_opp_mv;      -- 大約 600
