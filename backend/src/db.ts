import { Pool } from "pg";
import { config } from "./config.js";

export const pool = new Pool({
  connectionString: config.databaseUrl
});

export async function query<T = any>(sql: string, params: any[] = []) {
  return pool.query<T>(sql, params);
}
