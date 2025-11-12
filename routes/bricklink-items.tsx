import { Head } from "$fresh/runtime.ts";
import BricklinkProductsList from "../islands/BricklinkProductsList.tsx";

export default function BricklinkItemsPage() {
  return (
    <>
      <Head>
        <title>Bricklink Items - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          <div class="mb-6">
            <h1 class="text-3xl lg:text-4xl font-bold text-base-content">
              Bricklink Items
            </h1>
            <p class="text-base-content/70 mt-2">
              Monitor LEGO item prices from Bricklink marketplace with real-time
              sync status
            </p>
          </div>
          <BricklinkProductsList />
        </div>
      </div>
    </>
  );
}
