import { defineConfig } from "drizzle-kit";

export default defineConfig({
  schema: "./db/schema.ts",
  out: "./drizzle",
  dialect: "postgresql",
  dbCredentials: {
    url: Deno.env.get("DATABASE_URL") ||
      "postgresql://postgres:postgres@localhost:5432/bws",
  },
  verbose: true,
  strict: true,
});
