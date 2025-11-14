import { connection, db } from "./client.ts";

console.log("🗑️  Dropping all tables and data...");

try {
  // Drop the public schema and recreate it
  await db.execute(`DROP SCHEMA public CASCADE`);
  await db.execute(`CREATE SCHEMA public`);
  await db.execute(`GRANT ALL ON SCHEMA public TO postgres`);
  await db.execute(`GRANT ALL ON SCHEMA public TO public`);

  console.log("✅ Database reset successfully - all tables and data cleared");
} catch (error) {
  console.error("❌ Database reset failed:", error);
  Deno.exit(1);
} finally {
  await connection.end();
  Deno.exit(0);
}
