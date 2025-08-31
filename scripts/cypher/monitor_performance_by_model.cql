// Long-term + recent (top 50) average rewards per mode; no subqueries/params
MATCH (e:Episode)
WHERE e.mode IS NOT NULL AND e.reward IS NOT NULL
WITH e.mode AS mode, e
ORDER BY coalesce(e.created_at, datetime({epochMillis:0})) DESC
WITH mode, collect(toFloat(e.reward)) AS rewards
WITH mode, rewards, rewards[..50] AS recent_list
UNWIND rewards AS all_r
WITH mode, recent_list, avg(all_r) AS long_term_reward
UNWIND recent_list AS r
WITH mode, long_term_reward, avg(r) AS recent_reward
RETURN mode, long_term_reward, recent_reward
ORDER BY mode;
