apply migration.sql

```
docker exec -i chatrag-postgres psql -U chatrag -d chatrag < backend/sql/migration.sql
```

recreate db:

```
docker exec chatrag-postgres dropdb -U chatrag chatrag && \
docker exec chatrag-postgres createdb -U chatrag chatrag && \
docker exec -i chatrag-postgres psql -U chatrag -d chatrag < backend/sql/schema.sql
```

reset chroma:

```
docker compose down chroma
docker volume rm chatrag-com_chroma_data
docker compose up -d chroma
```