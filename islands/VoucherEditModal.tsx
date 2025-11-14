import type { UseVoucherFormReturn } from "../hooks/useVoucherForm.ts";

interface ProductTag {
  id: string;
  name: string;
}

interface VoucherEditModalProps {
  isOpen: boolean;
  availableTags: ProductTag[];
  voucherForm: UseVoucherFormReturn;
  onClose: () => void;
  onSave: (payload: Record<string, unknown>) => Promise<void>;
}

/**
 * Voucher edit/create modal component.
 * Handles form state and validation using passed form hook.
 */
export default function VoucherEditModal({
  isOpen,
  availableTags,
  voucherForm,
  onClose,
  onSave,
}: VoucherEditModalProps) {
  const { form, actions, isEditing } = voucherForm;

  const handleSubmit = async (e: Event) => {
    e.preventDefault();

    const validationError = actions.validateForm();
    if (validationError) {
      alert(validationError);
      return;
    }

    try {
      const payload = actions.toApiPayload();
      await onSave(payload);
      actions.resetForm();
      onClose();
    } catch (error) {
      console.error("Error saving voucher:", error);
      alert(error instanceof Error ? error.message : "Failed to save voucher");
    }
  };

  const handleCancel = () => {
    actions.resetForm();
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div class="modal modal-open">
      <div class="modal-box max-w-2xl">
        <h3 class="font-bold text-lg mb-4">
          {isEditing ? "Edit Voucher" : "Create New Voucher"}
        </h3>

        <form onSubmit={handleSubmit} class="space-y-4">
          {/* Name */}
          <div class="form-control">
            <label class="label">
              <span class="label-text">Voucher Name *</span>
            </label>
            <input
              type="text"
              class="input input-bordered w-full"
              value={form.name}
              onInput={(e) => actions.setName((e.target as HTMLInputElement).value)}
              placeholder="e.g., Shopee 11.11 15% off"
              required
            />
          </div>

          {/* Description */}
          <div class="form-control">
            <label class="label">
              <span class="label-text">Description</span>
            </label>
            <textarea
              class="textarea textarea-bordered w-full"
              value={form.description}
              onInput={(e) => actions.setDescription((e.target as HTMLTextAreaElement).value)}
              placeholder="Optional description"
              rows={2}
            />
          </div>

          {/* Voucher Type & Discount Type */}
          <div class="grid grid-cols-2 gap-4">
            <div class="form-control">
              <label class="label">
                <span class="label-text">Voucher Type *</span>
              </label>
              <select
                class="select select-bordered w-full"
                value={form.voucherType}
                onChange={(e) =>
                  actions.setVoucherType(
                    (e.target as HTMLSelectElement).value as "platform" | "shop" | "item_tag"
                  )}
              >
                <option value="platform">Platform</option>
                <option value="shop">Shop</option>
                <option value="item_tag">Tag-based</option>
              </select>
            </div>

            <div class="form-control">
              <label class="label">
                <span class="label-text">Discount Type *</span>
              </label>
              <select
                class="select select-bordered w-full"
                value={form.discountType}
                onChange={(e) =>
                  actions.setDiscountType(
                    (e.target as HTMLSelectElement).value as "percentage" | "fixed"
                  )}
              >
                <option value="percentage">Percentage</option>
                <option value="fixed">Fixed Amount</option>
              </select>
            </div>
          </div>

          {/* Discount Value */}
          <div class="form-control">
            <label class="label">
              <span class="label-text">
                Discount Value * {form.discountType === "percentage" ? "(%)" : "(RM)"}
              </span>
            </label>
            <input
              type="number"
              step={form.discountType === "percentage" ? "1" : "0.01"}
              class="input input-bordered w-full"
              value={form.discountValue}
              onInput={(e) => actions.setDiscountValue((e.target as HTMLInputElement).value)}
              placeholder={form.discountType === "percentage" ? "e.g., 15" : "e.g., 10.00"}
              required
            />
          </div>

          {/* Platform (conditional) */}
          {form.voucherType === "platform" && (
            <div class="form-control">
              <label class="label">
                <span class="label-text">Platform *</span>
              </label>
              <select
                class="select select-bordered w-full"
                value={form.platform}
                onChange={(e) => actions.setPlatform((e.target as HTMLSelectElement).value)}
                required
              >
                <option value="">Select platform</option>
                <option value="shopee">Shopee</option>
                <option value="toysrus">Toys"R"Us</option>
              </select>
            </div>
          )}

          {/* Shop details (conditional) */}
          {form.voucherType === "shop" && (
            <div class="grid grid-cols-2 gap-4">
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Shop ID *</span>
                </label>
                <input
                  type="number"
                  class="input input-bordered w-full"
                  value={form.shopId}
                  onInput={(e) => actions.setShopId((e.target as HTMLInputElement).value)}
                  placeholder="e.g., 123456"
                  required
                />
              </div>
              <div class="form-control">
                <label class="label">
                  <span class="label-text">Shop Name</span>
                </label>
                <input
                  type="text"
                  class="input input-bordered w-full"
                  value={form.shopName}
                  onInput={(e) => actions.setShopName((e.target as HTMLInputElement).value)}
                  placeholder="Optional"
                />
              </div>
            </div>
          )}

          {/* Tags (conditional) */}
          {form.voucherType === "item_tag" && (
            <div class="form-control">
              <label class="label">
                <span class="label-text">Required Tags *</span>
              </label>
              <select
                class="select select-bordered w-full"
                multiple
                size={5}
                value={form.requiredTagIds}
                onChange={(e) => {
                  const selected = Array.from((e.target as HTMLSelectElement).selectedOptions)
                    .map((opt) => opt.value);
                  actions.setRequiredTagIds(selected);
                }}
              >
                {availableTags.map((tag) => (
                  <option key={tag.id} value={tag.id}>
                    {tag.name}
                  </option>
                ))}
              </select>
              <label class="label">
                <span class="label-text-alt">Hold Ctrl/Cmd to select multiple</span>
              </label>
            </div>
          )}

          {/* Conditions */}
          <div class="grid grid-cols-2 gap-4">
            <div class="form-control">
              <label class="label">
                <span class="label-text">Min Purchase (RM)</span>
              </label>
              <input
                type="number"
                step="0.01"
                class="input input-bordered w-full"
                value={form.minPurchase}
                onInput={(e) => actions.setMinPurchase((e.target as HTMLInputElement).value)}
                placeholder="Optional"
              />
            </div>
            <div class="form-control">
              <label class="label">
                <span class="label-text">Max Discount (RM)</span>
              </label>
              <input
                type="number"
                step="0.01"
                class="input input-bordered w-full"
                value={form.maxDiscount}
                onInput={(e) => actions.setMaxDiscount((e.target as HTMLInputElement).value)}
                placeholder="Optional cap"
              />
            </div>
          </div>

          {/* Dates */}
          <div class="grid grid-cols-2 gap-4">
            <div class="form-control">
              <label class="label">
                <span class="label-text">Start Date</span>
              </label>
              <input
                type="date"
                class="input input-bordered w-full"
                value={form.startDate}
                onInput={(e) => actions.setStartDate((e.target as HTMLInputElement).value)}
              />
            </div>
            <div class="form-control">
              <label class="label">
                <span class="label-text">End Date</span>
              </label>
              <input
                type="date"
                class="input input-bordered w-full"
                value={form.endDate}
                onInput={(e) => actions.setEndDate((e.target as HTMLInputElement).value)}
              />
            </div>
          </div>

          {/* Active status */}
          <div class="form-control">
            <label class="label cursor-pointer justify-start gap-4">
              <input
                type="checkbox"
                class="checkbox"
                checked={form.isActive}
                onChange={(e) => actions.setIsActive((e.target as HTMLInputElement).checked)}
              />
              <span class="label-text">Active</span>
            </label>
          </div>

          {/* Actions */}
          <div class="modal-action">
            <button type="button" class="btn btn-ghost" onClick={handleCancel}>
              Cancel
            </button>
            <button type="submit" class="btn btn-primary">
              {isEditing ? "Update" : "Create"} Voucher
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
