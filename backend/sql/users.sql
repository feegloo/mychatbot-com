SELECT
  u.user_id,
  u.fingerprint,
  u.user_agent AS browser,
  u.created_at,
  COUNT(m.id) AS total_messages
FROM user_fingerprints u
LEFT JOIN conversation_messages m ON m.user_id = u.user_id
GROUP BY u.user_id, u.fingerprint, u.user_agent, u.created_at
HAVING COUNT(m.id) > 0

UNION ALL

-- messages with no matching fingerprint user (user_id = 0 or NULL)
SELECT
  0               AS user_id,
  '(no fingerprint)' AS fingerprint,
  NULL            AS browser,
  NULL            AS created_at,
  COUNT(m.id)     AS total_messages
FROM conversation_messages m
WHERE m.user_id IS NULL OR m.user_id NOT IN (SELECT user_id FROM user_fingerprints)

ORDER BY total_messages DESC, user_id;