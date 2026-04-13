apply migration.sql

```
docker exec -i mychatbot-postgres psql -U mychatbot -d mychatbot < backend/sql/migration.sql
```

recreate db:

```
docker exec mychatbot-postgres dropdb -U mychatbot mychatbot && \
docker exec mychatbot-postgres createdb -U mychatbot mychatbot && \
docker exec -i mychatbot-postgres psql -U mychatbot -d mychatbot < backend/sql/schema.sql
```

reset chroma:

```
docker compose down chroma
docker volume rm mychatbot-com_chroma_data
docker compose up -d chroma
```