import { Head } from "$fresh/runtime.ts";
import ProductsList from "../islands/ProductsList.tsx";

export default function ProductsPage() {
  return (
    <>
      <Head>
        <title>Products - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          <div class="mb-6">
            <h1 class="text-3xl lg:text-4xl font-bold text-base-content">Products</h1>
            <p class="text-base-content/70 mt-2">
              Browse all tracked LEGO products from Shopee
            </p>
          </div>
          <ProductsList />
        </div>
      </div>
    </>
  );
}
