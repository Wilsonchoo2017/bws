import ShopeeParser from "../islands/ShopeeParser.tsx";

export default function Home() {
  return (
    <div class="min-h-screen bg-base-200">
      <div class="container mx-auto px-4 py-8">
        {/* Header */}
        <div class="text-center mb-8">
          <h1 class="text-5xl font-bold mb-2">Shopee Product Parser</h1>
          <p class="text-lg opacity-70">
            Extract and store Shopee product data from HTML
          </p>
        </div>

        {/* Parser Component */}
        <ShopeeParser />

        {/* Instructions */}
        <div class="mt-8 max-w-4xl mx-auto">
          <div class="alert alert-info shadow-lg">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              class="stroke-current shrink-0 w-6 h-6"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <div class="text-sm">
              <div class="font-bold mb-1">How to use:</div>
              <ol class="list-decimal list-inside space-y-1">
                <li>Open a Shopee product listing page in your browser</li>
                <li>Right-click on the page and select "Inspect" or "Inspect Element"</li>
                <li>Find the main product listing container (usually has class like "shop-search-result-view__item")</li>
                <li>Right-click the element → Copy → Copy outerHTML</li>
                <li>Paste the HTML into the textarea above and submit</li>
              </ol>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
