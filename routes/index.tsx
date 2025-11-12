import { Head } from "$fresh/runtime.ts";
import ShopeeParser from "../islands/ShopeeParser.tsx";

export default function Home() {
  return (
    <>
      <Head>
        <title>Shopee Parser - LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="container mx-auto">
          {/* Header */}
          <div class="mb-8">
            <h1 class="text-4xl lg:text-5xl font-bold mb-2">Shopee Product Parser</h1>
            <p class="text-lg opacity-70">
              Extract and store Shopee product data from HTML
            </p>
          </div>

          {/* Parser Component */}
          <ShopeeParser />
        </div>
      </div>
    </>
  );
}
