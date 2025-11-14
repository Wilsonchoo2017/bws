import { Head } from "$fresh/runtime.ts";
import VouchersList from "../islands/VouchersList.tsx";

export default function VouchersPage() {
  return (
    <>
      <Head>
        <title>Vouchers - BWS</title>
      </Head>
      <div class="min-h-screen bg-base-200 p-4 lg:p-8">
        <div class="max-w-7xl mx-auto">
          <div class="mb-6">
            <h1 class="text-3xl lg:text-4xl font-bold text-base-content">
              Vouchers
            </h1>
            <p class="text-base-content/70 mt-2">
              Manage platform, shop, and tag-based vouchers for your products
            </p>
          </div>
          <VouchersList />
        </div>
      </div>
    </>
  );
}
