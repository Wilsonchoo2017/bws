import { useSignal } from "@preact/signals";
import { useEffect } from "preact/hooks";
import {
  addCartItem,
  calculateCartDiscountPercentage,
  calculateCartSubtotal,
  calculateCartTotal,
  calculateItemFinalPrice,
  calculateItemSavings,
  calculateTotalSavings,
  type CartItem,
  clearCart,
  loadCartItems,
  loadTotalCartPrice,
  removeCartItem,
  saveTotalCartPrice,
  updateCartItem,
} from "../utils/cart.ts";
import { formatPrice } from "../utils/formatters.ts";

export default function CartManager() {
  const cartItems = useSignal<CartItem[]>([]);
  const isAddingNew = useSignal(false);
  const editingId = useSignal<string | null>(null);

  // Form state
  const formLegoId = useSignal("");
  const formUnitPrice = useSignal("");
  const formQuantity = useSignal("1");
  const formPurchaseDate = useSignal("");
  const formPlatform = useSignal("");
  const formNotes = useSignal("");

  // Cart-level total price (applies to all items)
  const totalCartPriceInput = useSignal("");

  // Load cart items and total price on mount
  useEffect(() => {
    cartItems.value = loadCartItems();
    const savedTotal = loadTotalCartPrice();
    if (savedTotal > 0) {
      totalCartPriceInput.value = (savedTotal / 100).toFixed(2);
    }
  }, []);

  const resetForm = () => {
    formLegoId.value = "";
    formUnitPrice.value = "";
    formQuantity.value = "1";
    formPurchaseDate.value = "";
    formPlatform.value = "";
    formNotes.value = "";
    isAddingNew.value = false;
    editingId.value = null;
  };

  const handleAddItem = (e: Event) => {
    e.preventDefault();

    const unitPrice = Math.round(parseFloat(formUnitPrice.value) * 100);

    if (
      !formLegoId.value || isNaN(unitPrice) || unitPrice <= 0
    ) {
      alert("Please fill in all required fields with valid values");
      return;
    }

    const newItem = addCartItem({
      legoId: formLegoId.value,
      unitPrice,
      quantity: formQuantity.value ? parseInt(formQuantity.value) : 1,
      purchaseDate: formPurchaseDate.value || undefined,
      platform: formPlatform.value || undefined,
      notes: formNotes.value || undefined,
    });

    cartItems.value = [...cartItems.value, newItem];
    resetForm();
  };

  const handleUpdateItem = (e: Event) => {
    e.preventDefault();

    if (!editingId.value) return;

    const unitPrice = Math.round(parseFloat(formUnitPrice.value) * 100);

    if (
      !formLegoId.value || isNaN(unitPrice) || unitPrice <= 0
    ) {
      alert("Please fill in all required fields with valid values");
      return;
    }

    const success = updateCartItem(editingId.value, {
      legoId: formLegoId.value,
      unitPrice,
      quantity: formQuantity.value ? parseInt(formQuantity.value) : undefined,
      purchaseDate: formPurchaseDate.value || undefined,
      platform: formPlatform.value || undefined,
      notes: formNotes.value || undefined,
    });

    if (success) {
      cartItems.value = loadCartItems();
      resetForm();
    }
  };

  const handleEdit = (item: CartItem) => {
    editingId.value = item.id;
    formLegoId.value = item.legoId;
    formUnitPrice.value = (item.unitPrice / 100).toFixed(2);
    formQuantity.value = String(item.quantity || 1);
    formPurchaseDate.value = item.purchaseDate || "";
    formPlatform.value = item.platform || "";
    formNotes.value = item.notes || "";
    isAddingNew.value = true;
  };

  const handleRemove = (id: string) => {
    if (confirm("Are you sure you want to remove this item from the cart?")) {
      const success = removeCartItem(id);
      if (success) {
        cartItems.value = loadCartItems();
      }
    }
  };

  const handleClearCart = () => {
    if (
      confirm(
        "Are you sure you want to clear all items from the cart? This cannot be undone.",
      )
    ) {
      clearCart();
      saveTotalCartPrice(0);
      cartItems.value = [];
      totalCartPriceInput.value = "";
    }
  };

  const handleTotalCartPriceChange = (e: Event) => {
    const input = (e.target as HTMLInputElement).value;
    totalCartPriceInput.value = input;

    const priceInCents = Math.round(parseFloat(input) * 100);
    if (!isNaN(priceInCents) && priceInCents > 0) {
      saveTotalCartPrice(priceInCents);
    } else {
      saveTotalCartPrice(0);
    }
  };

  const subtotal = calculateCartSubtotal(cartItems.value);
  const total = calculateCartTotal(cartItems.value);
  const totalSavings = calculateTotalSavings(cartItems.value);
  const cartDiscountPct = calculateCartDiscountPercentage(cartItems.value);

  return (
    <div class="space-y-6">
      {/* Add New Item Button */}
      {!isAddingNew.value && (
        <div class="flex justify-between items-center">
          <h2 class="text-2xl font-bold">Shopping Cart</h2>
          <button
            class="btn btn-primary"
            onClick={() => isAddingNew.value = true}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-5 w-5"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fill-rule="evenodd"
                d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z"
                clip-rule="evenodd"
              />
            </svg>
            Add Item
          </button>
        </div>
      )}

      {/* Add/Edit Form */}
      {isAddingNew.value && (
        <div class="card bg-base-200 shadow-lg">
          <div class="card-body">
            <h3 class="card-title">
              {editingId.value ? "Edit Item" : "Add New Item"}
            </h3>
            <form
              onSubmit={editingId.value ? handleUpdateItem : handleAddItem}
              class="space-y-4"
            >
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* LEGO ID */}
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">
                      LEGO Set Number <span class="text-error">*</span>
                    </span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g., 10497, 21348"
                    class="input input-bordered"
                    value={formLegoId.value}
                    onInput={(e) =>
                      formLegoId.value = (e.target as HTMLInputElement).value}
                    required
                  />
                </div>

                {/* Unit Price */}
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">
                      Unit Price (RM) <span class="text-error">*</span>
                    </span>
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    min="0.01"
                    placeholder="199.90"
                    class="input input-bordered"
                    value={formUnitPrice.value}
                    onInput={(e) =>
                      formUnitPrice.value =
                        (e.target as HTMLInputElement).value}
                    required
                  />
                  <label class="label">
                    <span class="label-text-alt text-info">
                      Per item price (already discounted at item level)
                    </span>
                  </label>
                </div>

                {/* Quantity */}
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">Quantity</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    placeholder="1"
                    class="input input-bordered"
                    value={formQuantity.value}
                    onInput={(e) =>
                      formQuantity.value = (e.target as HTMLInputElement).value}
                  />
                </div>

                {/* Purchase Date */}
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">Purchase Date</span>
                  </label>
                  <input
                    type="date"
                    class="input input-bordered"
                    value={formPurchaseDate.value}
                    onInput={(e) =>
                      formPurchaseDate.value =
                        (e.target as HTMLInputElement).value}
                  />
                </div>

                {/* Platform */}
                <div class="form-control">
                  <label class="label">
                    <span class="label-text">Platform/Seller</span>
                  </label>
                  <input
                    type="text"
                    placeholder="e.g., Shopee, ToysRUs"
                    class="input input-bordered"
                    value={formPlatform.value}
                    onInput={(e) =>
                      formPlatform.value = (e.target as HTMLInputElement).value}
                  />
                </div>
              </div>

              {/* Notes */}
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Notes</span>
                </label>
                <textarea
                  class="textarea textarea-bordered"
                  placeholder="Voucher details, promo codes, or other notes..."
                  rows={2}
                  value={formNotes.value}
                  onInput={(e) =>
                    formNotes.value = (e.target as HTMLTextAreaElement).value}
                />
              </div>

              {/* Form Actions */}
              <div class="flex gap-2 justify-end">
                <button
                  type="button"
                  class="btn btn-ghost"
                  onClick={resetForm}
                >
                  Cancel
                </button>
                <button type="submit" class="btn btn-primary">
                  {editingId.value ? "Update Item" : "Add to Cart"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Total Cart Price Input (Cart-Level Discount) */}
      {cartItems.value.length > 0 && (
        <div class="card bg-gradient-to-br from-accent/10 to-accent/5 border-2 border-accent/30 shadow-lg">
          <div class="card-body">
            <h3 class="card-title text-accent flex items-center gap-2">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                class="h-5 w-5"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path d="M8.433 7.418c.155-.103.346-.196.567-.267v1.698a2.305 2.305 0 01-.567-.267C8.07 8.34 8 8.114 8 8c0-.114.07-.34.433-.582zM11 12.849v-1.698c.22.071.412.164.567.267.364.243.433.468.433.582 0 .114-.07.34-.433.582a2.305 2.305 0 01-.567.267z" />
                <path
                  fill-rule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-13a1 1 0 10-2 0v.092a4.535 4.535 0 00-1.676.662C6.602 6.234 6 7.009 6 8c0 .99.602 1.765 1.324 2.246.48.32 1.054.545 1.676.662v1.941c-.391-.127-.68-.317-.843-.504a1 1 0 10-1.51 1.31c.562.649 1.413 1.076 2.353 1.253V15a1 1 0 102 0v-.092a4.535 4.535 0 001.676-.662C13.398 13.766 14 12.991 14 12c0-.99-.602-1.765-1.324-2.246A4.535 4.535 0 0011 9.092V7.151c.391.127.68.317.843.504a1 1 0 101.511-1.31c-.563-.649-1.413-1.076-2.354-1.253V5z"
                  clip-rule="evenodd"
                />
              </svg>
              Final Cart Price (After All Discounts)
            </h3>
            <div class="form-control">
              <label class="label">
                <span class="label-text">
                  Enter the total price you'll pay after cart-level vouchers,
                  platform discounts, etc.
                </span>
              </label>
              <div class="join">
                <span class="join-item btn btn-accent btn-disabled">RM</span>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  placeholder="Enter final cart total..."
                  class="input input-bordered input-accent join-item flex-1"
                  value={totalCartPriceInput.value}
                  onInput={handleTotalCartPriceChange}
                />
              </div>
              <label class="label">
                <span class="label-text-alt">
                  {totalCartPriceInput.value &&
                      !isNaN(parseFloat(totalCartPriceInput.value))
                    ? `Cart Discount: ${
                      cartDiscountPct.toFixed(1)
                    }% • Savings: ${formatPrice(totalSavings)}`
                    : "Leave empty if no cart-level discounts"}
                </span>
              </label>
            </div>
          </div>
        </div>
      )}

      {/* Cart Items */}
      {cartItems.value.length === 0
        ? (
          <div class="text-center py-12">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              class="h-24 w-24 mx-auto text-base-300"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
            <p class="text-lg text-base-content/70 mt-4">
              Your cart is empty
            </p>
            <button
              class="btn btn-primary mt-4"
              onClick={() => isAddingNew.value = true}
            >
              Add Your First Item
            </button>
          </div>
        )
        : (
          <>
            {/* Desktop Table View */}
            <div class="hidden lg:block overflow-x-auto">
              <table class="table table-zebra w-full">
                <thead>
                  <tr>
                    <th>LEGO Set</th>
                    <th>Item Total</th>
                    <th>Final Price</th>
                    <th>Qty</th>
                    <th>Discount</th>
                    <th>Savings</th>
                    <th>Platform</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {cartItems.value.map((item) => {
                    const totalCartPrice = loadTotalCartPrice();
                    const itemFinalPrice = calculateItemFinalPrice(
                      item,
                      subtotal,
                      totalCartPrice > 0 ? totalCartPrice : subtotal,
                    );
                    const savings = calculateItemSavings(
                      item,
                      subtotal,
                      totalCartPrice > 0 ? totalCartPrice : subtotal,
                    );
                    const itemSubtotal = item.unitPrice * (item.quantity || 1);
                    const discountPct = itemSubtotal > 0
                      ? ((itemSubtotal - itemFinalPrice) / itemSubtotal) * 100
                      : 0;

                    return (
                      <tr key={item.id}>
                        <td>
                          <div class="font-bold">{item.legoId}</div>
                          {item.purchaseDate && (
                            <div class="text-sm opacity-70">
                              {new Date(item.purchaseDate).toLocaleDateString()}
                            </div>
                          )}
                          {item.notes && (
                            <div class="text-xs opacity-60 mt-1">
                              {item.notes}
                            </div>
                          )}
                        </td>
                        <td>
                          {formatPrice(item.unitPrice * (item.quantity || 1))}
                        </td>
                        <td class="font-semibold">
                          {formatPrice(itemFinalPrice)}
                        </td>
                        <td>{item.quantity || 1}</td>
                        <td>
                          <span class="badge badge-success">
                            {discountPct.toFixed(1)}%
                          </span>
                        </td>
                        <td class="text-success font-medium">
                          {formatPrice(savings)}
                        </td>
                        <td>
                          {item.platform && (
                            <span class="badge badge-outline">
                              {item.platform}
                            </span>
                          )}
                        </td>
                        <td>
                          <div class="flex gap-2">
                            <button
                              class="btn btn-ghost btn-xs"
                              onClick={() => handleEdit(item)}
                              title="Edit"
                            >
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                class="h-4 w-4"
                                viewBox="0 0 20 20"
                                fill="currentColor"
                              >
                                <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zM11.379 5.793L3 14.172V17h2.828l8.38-8.379-2.83-2.828z" />
                              </svg>
                            </button>
                            <button
                              class="btn btn-ghost btn-xs text-error"
                              onClick={() => handleRemove(item.id)}
                              title="Remove"
                            >
                              <svg
                                xmlns="http://www.w3.org/2000/svg"
                                class="h-4 w-4"
                                viewBox="0 0 20 20"
                                fill="currentColor"
                              >
                                <path
                                  fill-rule="evenodd"
                                  d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z"
                                  clip-rule="evenodd"
                                />
                              </svg>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Card View */}
            <div class="lg:hidden space-y-4">
              {cartItems.value.map((item) => {
                const totalCartPrice = loadTotalCartPrice();
                const itemFinalPrice = calculateItemFinalPrice(
                  item,
                  subtotal,
                  totalCartPrice > 0 ? totalCartPrice : subtotal,
                );
                const savings = calculateItemSavings(
                  item,
                  subtotal,
                  totalCartPrice > 0 ? totalCartPrice : subtotal,
                );
                const itemSubtotal = item.unitPrice * (item.quantity || 1);
                const discountPct = itemSubtotal > 0
                  ? ((itemSubtotal - itemFinalPrice) / itemSubtotal) * 100
                  : 0;

                return (
                  <div key={item.id} class="card bg-base-100 shadow-lg">
                    <div class="card-body">
                      <div class="flex justify-between items-start">
                        <h3 class="card-title text-lg">{item.legoId}</h3>
                        <div class="flex gap-1">
                          <button
                            class="btn btn-ghost btn-sm"
                            onClick={() => handleEdit(item)}
                          >
                            Edit
                          </button>
                          <button
                            class="btn btn-ghost btn-sm text-error"
                            onClick={() => handleRemove(item.id)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>

                      <div class="space-y-2 text-sm">
                        <div class="flex justify-between">
                          <span class="text-base-content/70">
                            Unit Price (Total):
                          </span>
                          <span>{formatPrice(itemSubtotal)}</span>
                        </div>
                        <div class="flex justify-between font-semibold">
                          <span>Final Price:</span>
                          <span>{formatPrice(itemFinalPrice)}</span>
                        </div>
                        <div class="flex justify-between">
                          <span class="text-base-content/70">Quantity:</span>
                          <span>{item.quantity || 1}</span>
                        </div>
                        <div class="flex justify-between">
                          <span class="text-base-content/70">Discount:</span>
                          <span class="badge badge-success">
                            {discountPct.toFixed(1)}%
                          </span>
                        </div>
                        <div class="flex justify-between text-success font-medium">
                          <span>Savings:</span>
                          <span>{formatPrice(savings)}</span>
                        </div>
                        {item.platform && (
                          <div class="flex justify-between">
                            <span class="text-base-content/70">Platform:</span>
                            <span class="badge badge-outline">
                              {item.platform}
                            </span>
                          </div>
                        )}
                        {item.purchaseDate && (
                          <div class="flex justify-between">
                            <span class="text-base-content/70">
                              Purchase Date:
                            </span>
                            <span>
                              {new Date(item.purchaseDate).toLocaleDateString()}
                            </span>
                          </div>
                        )}
                        {item.notes && (
                          <div class="text-xs opacity-70 mt-2 p-2 bg-base-200 rounded">
                            {item.notes}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Cart Summary */}
            <div class="card bg-primary text-primary-content shadow-lg">
              <div class="card-body">
                <h3 class="card-title">Cart Summary</h3>
                <div class="space-y-2">
                  <div class="flex justify-between text-sm opacity-90">
                    <span>Subtotal (Unit Prices):</span>
                    <span>{formatPrice(subtotal)}</span>
                  </div>
                  <div class="flex justify-between text-lg font-bold">
                    <span>Total Savings:</span>
                    <span>{formatPrice(totalSavings)}</span>
                  </div>
                  <div class="divider my-1"></div>
                  <div class="flex justify-between text-2xl font-bold">
                    <span>Final Total:</span>
                    <span>{formatPrice(total)}</span>
                  </div>
                  <div class="text-sm opacity-90 text-center">
                    {cartItems.value.length} item
                    {cartItems.value.length !== 1 ? "s" : ""} in cart
                  </div>
                </div>

                <div class="card-actions justify-between mt-4">
                  <a href="/products" class="btn btn-ghost">
                    View Analytics
                  </a>
                  <button
                    class="btn btn-error btn-outline"
                    onClick={handleClearCart}
                  >
                    Clear Cart
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
    </div>
  );
}
