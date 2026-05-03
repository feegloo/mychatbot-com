SELECT
  u.user_id,
  COUNT(m.id) AS total_messages,
  u.created_at,
  u.user_agent AS browser,
  u.fingerprint
FROM user_fingerprints u
LEFT JOIN conversation_messages m ON m.user_id = u.user_id
GROUP BY u.user_id, u.fingerprint, u.user_agent, u.created_at
HAVING COUNT(m.id) > 0

UNION ALL

-- messages with no matching fingerprint user (user_id = 0 or NULL)
SELECT
  0               AS user_id,
  COUNT(m.id)     AS total_messages,
  NULL            AS created_at,
  NULL            AS browser,
  '(no fingerprint)' AS fingerprint
FROM conversation_messages m
WHERE m.user_id IS NULL OR m.user_id NOT IN (SELECT user_id FROM user_fingerprints)

ORDER BY total_messages DESC, user_id;