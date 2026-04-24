SELECT
  u.user_id,
  u.fingerprint,
  u.user_agent AS browser,
  u.created_at AS user_created_at,
  DATE(m.created_at) AS day,
  COUNT(*) AS messages_on_day,
  SUM(COUNT(*)) OVER (PARTITION BY u.user_id) AS total_messages
FROM user_fingerprints u
JOIN conversation_messages m ON m.user_id = u.user_id
WHERE m.user_id <> 0
GROUP BY u.user_id, u.fingerprint, u.user_agent, u.created_at, DATE(m.created_at)
ORDER BY total_messages DESC, u.user_id, day;