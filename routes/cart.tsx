import { PageProps } from "$fresh/server.ts";
import CartManager from "../islands/CartManager.tsx";

export default function CartPage(_props: PageProps) {
  return (
    <div class="container mx-auto px-4 py-8 max-w-7xl">
      <div class="mb-6">
        <h1 class="text-3xl font-bold mb-2">Shopping Cart</h1>
        <p class="text-base-content/70">
          Track your LEGO purchases and calculate real discounts after vouchers
          and promos
        </p>
      </div>

      <CartManager />
    </div>
  );
}
