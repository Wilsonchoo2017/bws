import type { Voucher } from "../../hooks/useVoucherList.ts";

interface VoucherTableRowProps {
  voucher: Voucher;
  onEdit: (voucher: Voucher) => void;
  onDuplicate: (voucher: Voucher) => void;
  onDelete: (voucher: Voucher) => void;
}

/**
 * Individual voucher table row component.
 * Displays voucher information and action buttons.
 * Follows Single Responsibility Principle - only handles row rendering.
 */
export function VoucherTableRow({
  voucher,
  onEdit,
  onDuplicate,
  onDelete,
}: VoucherTableRowProps) {
  // Format discount for display
  const formatDiscount = () => {
    if (voucher.discountType === "percentage") {
      return `${(voucher.discountValue / 100).toFixed(0)}%`;
    } else {
      return `RM ${(voucher.discountValue / 100).toFixed(2)}`;
    }
  };

  // Format min purchase
  const formatMinPurchase = () => {
    if (!voucher.minPurchase) return "-";
    return `RM ${(voucher.minPurchase / 100).toFixed(2)}`;
  };

  // Get status badge
  const getStatusBadge = () => {
    switch (voucher.status) {
      case "active":
        return <span class="badge badge-success badge-sm">Active</span>;
      case "soon":
        return <span class="badge badge-warning badge-sm">Starting Soon</span>;
      case "expired":
        return <span class="badge badge-error badge-sm">Expired</span>;
      default:
        return <span class="badge badge-ghost badge-sm">Inactive</span>;
    }
  };

  // Get voucher type badge
  const getTypeBadge = () => {
    const typeMap = {
      platform: "Platform",
      shop: "Shop",
      item_tag: "Tag-based",
    };
    return (
      <span class="badge badge-outline badge-sm">
        {typeMap[voucher.voucherType]}
      </span>
    );
  };

  // Format dates
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "-";
    return new Date(dateStr).toLocaleDateString();
  };

  return (
    <tr class="hover">
      <td>
        <div>
          <div class="font-semibold">{voucher.name}</div>
          {voucher.description && (
            <div class="text-sm text-gray-500 truncate max-w-xs">
              {voucher.description}
            </div>
          )}
        </div>
      </td>
      <td>
        <div class="flex gap-2">
          {getTypeBadge()}
          {getStatusBadge()}
        </div>
      </td>
      <td class="font-semibold">{formatDiscount()}</td>
      <td>{formatMinPurchase()}</td>
      <td>
        {voucher.platform && (
          <span class="badge badge-primary badge-sm capitalize">
            {voucher.platform}
          </span>
        )}
        {voucher.shopName && (
          <div class="text-sm text-gray-500 truncate max-w-xs">
            {voucher.shopName}
          </div>
        )}
        {!voucher.platform && !voucher.shopName && "-"}
      </td>
      <td>
        <div class="text-sm">
          <div>Start: {formatDate(voucher.startDate)}</div>
          <div>End: {formatDate(voucher.endDate)}</div>
        </div>
      </td>
      <td>
        <div class="flex gap-2">
          <button
            class="btn btn-ghost btn-xs"
            onClick={() => onEdit(voucher)}
            title="Edit voucher"
          >
            Edit
          </button>
          <button
            class="btn btn-ghost btn-xs"
            onClick={() => onDuplicate(voucher)}
            title="Duplicate voucher"
          >
            Duplicate
          </button>
          <button
            class="btn btn-error btn-xs"
            onClick={() => onDelete(voucher)}
            title="Delete voucher"
          >
            Delete
          </button>
        </div>
      </td>
    </tr>
  );
}
