import { Pool, QueryResultRow } from "pg";
import { config } from "./config.js";

export const pool = new Pool({
  connectionString: config.databaseUrl
});

export async function query<T extends QueryResultRow = any>(sql: string, params: any[] = []) {
  return pool.query<T>(sql, params);
}
