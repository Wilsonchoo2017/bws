import { defineConfig } from "$fresh/server.ts";
import tailwind from "$fresh/plugins/tailwind.ts";

export default defineConfig({
  plugins: [tailwind()],
  server: {
    hostname: "0.0.0.0", // Bind to all network interfaces for Tailscale access
    port: 8000,
  },
});
