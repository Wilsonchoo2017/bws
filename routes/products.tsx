import { Head } from "$fresh/runtime.ts";
import BricklinkProductsList from "../islands/BricklinkProductsList.tsx";

export default function ProductsPage() {
  return (
    <>
      <Head>
        <title>Bricklink Products - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          <div class="mb-6">
            <h1 class="text-3xl lg:text-4xl font-bold text-base-content">
              Bricklink Products
            </h1>
            <p class="text-base-content/70 mt-2">
              Monitor all tracked LEGO items from Bricklink with real-time sync
              status
            </p>
          </div>
          <BricklinkProductsList />
        </div>
      </div>
    </>
  );
}
