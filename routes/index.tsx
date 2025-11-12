import { Head } from "$fresh/runtime.ts";
import UnifiedParser from "../islands/UnifiedParser.tsx";

export default function Home() {
  return (
    <>
      <Head>
        <title>Multi-Platform LEGO Price Tracker</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="container mx-auto">
          {/* Header */}
          <div class="mb-8">
            <h1 class="text-4xl lg:text-5xl font-bold mb-2">
              LEGO Price Tracker
            </h1>
            <p class="text-lg opacity-70">
              Extract and store product data from Shopee and Toys"R"Us
            </p>
          </div>

          {/* Parser Component */}
          <UnifiedParser />
        </div>
      </div>
    </>
  );
}
