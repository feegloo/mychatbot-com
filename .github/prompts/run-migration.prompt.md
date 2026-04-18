# Run SQL Migration

Apply a SQL migration file to the ChatRAG production database (GCP Cloud SQL).

---

## Arguments

- `{{sqlFile}}` — SQL filename in `backend/sql/` (e.g. `005-parent-conversation-id.sql`).

## Steps

### 1. Gather inputs — ask the user

Ask two questions up front:

1. **Migration file** — If `{{sqlFile}}` is empty or not provided, list numbered migration files in `backend/sql/` and ask which one to run.
2. **DB password** — Ask the user for the Cloud SQL password. Hint: it's `DB_PASSWORD` in `infra/cloudrun/.env.gcp`.

Do **not** read the password from the env file automatically — let the user paste it.

### 2. Validate the migration file

- Confirm `backend/sql/{{sqlFile}}` exists.
- Verify it contains SQL wrapped in `BEGIN; ... COMMIT;`.

### 3. Set up environment (macOS)

Detect and add required tools to PATH:

```bash
# Homebrew libpq (psql)
[[ -d /usr/local/opt/libpq/bin ]] && export PATH="/usr/local/opt/libpq/bin:$PATH"
[[ -d /opt/homebrew/opt/libpq/bin ]] && export PATH="/opt/homebrew/opt/libpq/bin:$PATH"

# gcloud SDK
[[ -d /usr/local/share/google-cloud-sdk/bin ]] && export PATH="/usr/local/share/google-cloud-sdk/bin:$PATH"
[[ -d /opt/homebrew/share/google-cloud-sdk/bin ]] && export PATH="/opt/homebrew/share/google-cloud-sdk/bin:$PATH"
[[ -d "$HOME/google-cloud-sdk/bin" ]] && export PATH="$HOME/google-cloud-sdk/bin:$PATH"
```

### 4. Apply to GCP Cloud SQL (production)

```bash
gcloud sql connect chatrag-db-instance \
  --project=chatbotqa-app \
  --user=chatrag \
  --database=chatrag \
  < backend/sql/{{sqlFile}}
```

- When the password prompt appears, send the password the user provided in step 1.
- Verify output shows no `ERROR` lines.

### 5. Confirm success

- Report whether the migration applied cleanly or any errors encountered.

## Creating a new migration

When creating a new migration file (not running one):

1. Find the highest-numbered file in `backend/sql/` (e.g. `005-*.sql`).
2. Name the new file `<next_number>-<short-description>.sql` (e.g. `006-add-reactions.sql`).
3. Wrap all statements in `BEGIN; ... COMMIT;` for transactional safety.
4. Use `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and similar idempotent patterns where possible.
