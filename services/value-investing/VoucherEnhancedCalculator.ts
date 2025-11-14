import type { Cents } from "../../types/price.ts";
import type { ValueMetrics } from "../../types/value-investing.ts";
import type { VoucherTemplate } from "../../types/voucher.ts";
import {
  findOptimalVoucherOrder,
} from "../../utils/voucher.ts";
import type { TaggedCartItem } from "../../types/voucher.ts";
import { ValueCalculator } from "./ValueCalculator.ts";

/**
 * Extended value metrics that include voucher-adjusted calculations
 */
export interface VoucherEnhancedMetrics extends ValueMetrics {
  // Original metrics (base values without vouchers)
  originalPrice: Cents;
  originalExpectedROI: number;
  originalMarginOfSafety: number;

  // Voucher-adjusted metrics
  voucherDiscountedPrice: Cents;
  voucherSavings: Cents;
  voucherEnhancedROI: number;
  voucherEnhancedMarginOfSafety: number;

  // Comparison metrics
  roiImprovement: number; // Percentage point improvement
  worthItWithVoucher: boolean; // Whether deal becomes good with voucher
  optimalVoucherOrder: VoucherTemplate[]; // Best order to apply vouchers
}

/**
 * Input for calculating voucher-enhanced metrics
 */
export interface VoucherEnhancedInput {
  productId: string;
  legoSetNumber?: string;
  currentPrice: Cents;
  tags?: string[];
  valueMetrics: ValueMetrics; // Original metrics without vouchers
  selectedVouchers: VoucherTemplate[];
}

/**
 * VoucherEnhancedCalculator adds voucher simulation to value investing analysis.
 * It recalculates ROI and margin of safety based on voucher-discounted prices.
 *
 * UNIT CONVENTION: All prices are in CENTS (matching ValueCalculator)
 */
export class VoucherEnhancedCalculator {
  /**
   * Calculate voucher-enhanced metrics for a product
   * Returns both original and voucher-adjusted metrics for comparison
   */
  static calculateVoucherEnhancedMetrics(
    input: VoucherEnhancedInput,
  ): VoucherEnhancedMetrics {
    const {
      productId,
      legoSetNumber,
      currentPrice,
      tags,
      valueMetrics,
      selectedVouchers,
    } = input;

    // If no vouchers selected, return original metrics with zero enhancements
    if (!selectedVouchers || selectedVouchers.length === 0) {
      return {
        ...valueMetrics,
        originalPrice: currentPrice,
        originalExpectedROI: valueMetrics.expectedROI,
        originalMarginOfSafety: valueMetrics.marginOfSafety,
        voucherDiscountedPrice: currentPrice,
        voucherSavings: 0 as Cents,
        voucherEnhancedROI: valueMetrics.expectedROI,
        voucherEnhancedMarginOfSafety: valueMetrics.marginOfSafety,
        roiImprovement: 0,
        worthItWithVoucher: false,
        optimalVoucherOrder: [],
      };
    }

    // Create cart item for voucher calculation
    const cartItem: TaggedCartItem = {
      id: productId,
      legoId: legoSetNumber || productId,
      unitPrice: currentPrice,
      quantity: 1,
      tags: tags,
    };

    // Find optimal voucher order for maximum savings
    const voucherResult = findOptimalVoucherOrder(
      [cartItem],
      selectedVouchers,
    );

    const voucherDiscountedPrice = voucherResult.finalTotal as Cents;
    const voucherSavings = voucherResult.totalDiscount as Cents;

    // Recalculate ROI with voucher-discounted price
    // ROI = (intrinsicValue - effectivePrice) / effectivePrice * 100
    const voucherEnhancedROI = ValueCalculator.calculateExpectedROI(
      voucherDiscountedPrice,
      valueMetrics.intrinsicValue,
    );

    // Recalculate margin of safety with voucher-discounted price
    // Margin = (intrinsicValue - effectivePrice) / intrinsicValue * 100
    const voucherEnhancedMarginOfSafety = ValueCalculator
      .calculateMarginOfSafety(
        voucherDiscountedPrice,
        valueMetrics.intrinsicValue,
      );

    // Calculate improvement metrics
    const roiImprovement = voucherEnhancedROI - valueMetrics.expectedROI;

    // Determine if deal becomes worthwhile with vouchers
    // Using 15% margin of safety as threshold (reasonable value investing standard)
    const WORTHWHILE_MARGIN_THRESHOLD = 15;
    const wasNotWorthwhile = valueMetrics.marginOfSafety <
      WORTHWHILE_MARGIN_THRESHOLD;
    const isNowWorthwhile = voucherEnhancedMarginOfSafety >=
      WORTHWHILE_MARGIN_THRESHOLD;
    const worthItWithVoucher = wasNotWorthwhile && isNowWorthwhile;

    // Extract optimal voucher order from result
    const optimalVoucherOrder = voucherResult.appliedVouchers
      .filter((v) => v.isValid && v.calculatedDiscount > 0)
      .map((av) => {
        // Reconstruct VoucherTemplate from AppliedVoucher
        const { calculatedDiscount: _calculatedDiscount, isCapped: _isCapped, originalDiscount: _originalDiscount, isValid: _isValid, validationMessage: _validationMessage, ...template } = av;
        return template as VoucherTemplate;
      });

    return {
      ...valueMetrics,
      originalPrice: currentPrice,
      originalExpectedROI: valueMetrics.expectedROI,
      originalMarginOfSafety: valueMetrics.marginOfSafety,
      voucherDiscountedPrice,
      voucherSavings,
      voucherEnhancedROI,
      voucherEnhancedMarginOfSafety,
      roiImprovement,
      worthItWithVoucher,
      optimalVoucherOrder,
    };
  }

  /**
   * Batch calculate voucher-enhanced metrics for multiple products
   * Useful for enhancing a full list of value investing opportunities
   */
  static calculateBatchVoucherEnhancedMetrics(
    inputs: VoucherEnhancedInput[],
  ): VoucherEnhancedMetrics[] {
    return inputs.map((input) => this.calculateVoucherEnhancedMetrics(input));
  }

  /**
   * Calculate potential savings across all products with given vouchers
   * Useful for showing total impact of voucher selection
   */
  static calculateTotalPotentialSavings(
    inputs: VoucherEnhancedInput[],
  ): {
    totalOriginalPrice: Cents;
    totalVoucherPrice: Cents;
    totalSavings: Cents;
    averageROIImprovement: number;
    productsImproved: number;
  } {
    const metrics = this.calculateBatchVoucherEnhancedMetrics(inputs);

    const totalOriginalPrice = metrics.reduce(
      (sum, m) => sum + m.originalPrice,
      0,
    ) as Cents;

    const totalVoucherPrice = metrics.reduce(
      (sum, m) => sum + m.voucherDiscountedPrice,
      0,
    ) as Cents;

    const totalSavings = (totalOriginalPrice - totalVoucherPrice) as Cents;

    const averageROIImprovement = metrics.length > 0
      ? metrics.reduce((sum, m) => sum + m.roiImprovement, 0) / metrics.length
      : 0;

    const productsImproved = metrics.filter((m) => m.worthItWithVoucher).length;

    return {
      totalOriginalPrice,
      totalVoucherPrice,
      totalSavings,
      averageROIImprovement,
      productsImproved,
    };
  }

  /**
   * Determine if a product becomes a "buy" with vouchers applied
   * Returns recommendation based on voucher-enhanced margin of safety
   */
  static getVoucherEnhancedRecommendation(
    metrics: VoucherEnhancedMetrics,
  ): {
    action: "strong_buy" | "buy" | "hold" | "pass";
    reasoning: string;
  } {
    const margin = metrics.voucherEnhancedMarginOfSafety;
    const roiImprovement = metrics.roiImprovement;

    // Strong buy: margin > 30% OR significant improvement (>20pp)
    if (margin >= 30 || (margin >= 20 && roiImprovement >= 20)) {
      return {
        action: "strong_buy",
        reasoning:
          `Excellent deal with vouchers applied. ${margin.toFixed(1)}% margin of safety, ${roiImprovement.toFixed(1)}pp ROI improvement.`,
      };
    }

    // Buy: margin 15-30%
    if (margin >= 15) {
      return {
        action: "buy",
        reasoning:
          `Good value investing opportunity with vouchers. ${margin.toFixed(1)}% margin of safety.`,
      };
    }

    // Hold: margin 5-15% (close but not quite there)
    if (margin >= 5) {
      return {
        action: "hold",
        reasoning:
          `Close to worthwhile with vouchers, but margin (${margin.toFixed(1)}%) is below recommended threshold.`,
      };
    }

    // Pass: margin < 5%
    return {
      action: "pass",
      reasoning:
        `Not a good deal even with vouchers. Margin of safety (${margin.toFixed(1)}%) is too low.`,
    };
  }
}
