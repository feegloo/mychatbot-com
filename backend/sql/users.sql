SELECT
  u.user_id,
  u.fingerprint,
  u.user_agent AS browser,
  u.created_at,
  COUNT(m.id) AS total_messages
FROM user_fingerprints u
LEFT JOIN conversation_messages m ON m.user_id = u.user_id
GROUP BY u.user_id, u.fingerprint, u.user_agent, u.created_at
ORDER BY total_messages DESC, u.user_id;