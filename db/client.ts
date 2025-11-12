import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema.ts";

// Get database URL from environment or use default
const DATABASE_URL = Deno.env.get("DATABASE_URL") ||
  "postgresql://postgres:postgres@localhost:5432/bws";

// Create postgres connection
export const connection = postgres(DATABASE_URL, {
  max: 10, // Connection pool size
  idle_timeout: 20,
  connect_timeout: 10,
});

// Create Drizzle ORM instance
export const db = drizzle(connection, { schema });

// Graceful shutdown
Deno.addSignalListener("SIGINT", async () => {
  await connection.end();
  Deno.exit(0);
});

Deno.addSignalListener("SIGTERM", async () => {
  await connection.end();
  Deno.exit(0);
});
