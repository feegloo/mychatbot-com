-- WARNING: This drops ALL data and recreates the database from scratch.
-- Usage:
--   docker exec -i chatrag-postgres psql -U chatrag -d postgres -f - \
--     < backend/sql/recreate.sql

DROP DATABASE IF EXISTS chatrag;
CREATE DATABASE chatrag OWNER chatrag;

\connect chatrag

\i schema.sql
