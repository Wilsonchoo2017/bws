import { migrate } from "drizzle-orm/postgres-js/migrator";
import { connection, db } from "./client.ts";

console.log("🔄 Running migrations...");

try {
  await migrate(db, { migrationsFolder: "./drizzle" });
  console.log("✅ Migrations completed successfully");
} catch (error) {
  console.error("❌ Migration failed:", error);
  Deno.exit(1);
} finally {
  await connection.end();
  Deno.exit(0);
}
