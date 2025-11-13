import { PageProps } from "$fresh/server.ts";
import TagManager from "../islands/TagManager.tsx";

export default function TagsPage(_props: PageProps) {
  return (
    <div class="container mx-auto px-4 py-8 max-w-7xl">
      <div class="mb-6">
        <h1 class="text-3xl font-bold mb-2">Product Tags</h1>
        <p class="text-base-content/70">
          Manage time-limited tags for promotions and vouchers. Tags help you
          organize products for specific sales events.
        </p>
      </div>

      <TagManager />
    </div>
  );
}
