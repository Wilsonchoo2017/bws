/**
 * DemandAnalyzer - Analyzes market demand and community sentiment
 * Focuses on: sales velocity, engagement, Reddit buzz, resale activity
 */

import { BaseAnalyzer } from "./BaseAnalyzer.ts";
import type { AnalysisScore, DemandData } from "../types.ts";

export class DemandAnalyzer extends BaseAnalyzer<DemandData> {
  constructor() {
    super(
      "Demand Analyzer",
      "Evaluates market demand, sales velocity, and community interest",
    );
  }

  // deno-lint-ignore require-await
  async analyze(data: DemandData): Promise<AnalysisScore | null> {
    // PRIMARY: Check for Bricklink pricing data (market indicators)
    const hasBricklinkPricing = data.bricklinkCurrentNewAvg !== undefined ||
      data.bricklinkSixMonthNewAvg !== undefined;

    // SECONDARY: Check for market-driven Bricklink past sales data
    const hasPastSalesData = data.bricklinkPastSalesCount !== undefined &&
      data.bricklinkPastSalesCount > 0;

    // TERTIARY: Legacy data checks
    const hasSalesData = data.unitsSold !== undefined ||
      data.lifetimeSold !== undefined;
    const hasLegacyBricklinkData = data.bricklinkTimesSold !== undefined ||
      data.bricklinkTotalQty !== undefined;
    const hasRedditData = data.redditPosts !== undefined;
    const hasEngagementData = data.viewCount !== undefined ||
      data.likedCount !== undefined || data.commentCount !== undefined;

    // Require at least one demand signal (prioritize Bricklink pricing)
    if (
      !hasBricklinkPricing && !hasPastSalesData && !hasSalesData &&
      !hasLegacyBricklinkData && !hasRedditData && !hasEngagementData
    ) {
      return null; // Skip analysis - insufficient demand data
    }

    const scores: Array<{ score: number; weight: number }> = [];
    const reasons: string[] = [];
    const dataPoints: Record<string, unknown> = {};

    // PRIMARY: 1. Bricklink Market Pricing (60% weight) - Direct market indicators
    if (hasBricklinkPricing) {
      const pricingScore = this.analyzeBricklinkPricing(data);
      scores.push({ score: pricingScore, weight: 0.60 });

      // Add reasoning based on market data
      if (data.bricklinkCurrentNewAvg) {
        dataPoints.bricklinkCurrentNewAvg = data.bricklinkCurrentNewAvg;
        reasons.push(
          `Active market (Avg: $${data.bricklinkCurrentNewAvg.toFixed(2)})`,
        );
      }

      // Price trend analysis
      if (
        data.bricklinkCurrentNewAvg && data.bricklinkSixMonthNewAvg &&
        data.bricklinkCurrentNewAvg > data.bricklinkSixMonthNewAvg
      ) {
        const increase = ((data.bricklinkCurrentNewAvg -
          data.bricklinkSixMonthNewAvg) / data.bricklinkSixMonthNewAvg * 100)
          .toFixed(1);
        reasons.push(`Price trending up (+${increase}% vs 6mo avg)`);
      } else if (
        data.bricklinkCurrentNewAvg && data.bricklinkSixMonthNewAvg &&
        data.bricklinkCurrentNewAvg < data.bricklinkSixMonthNewAvg
      ) {
        const decrease = ((data.bricklinkSixMonthNewAvg -
          data.bricklinkCurrentNewAvg) / data.bricklinkSixMonthNewAvg * 100)
          .toFixed(1);
        reasons.push(`Price trending down (-${decrease}% vs 6mo avg)`);
      }

      // Market activity
      if (data.bricklinkCurrentNewLots) {
        dataPoints.bricklinkCurrentNewLots = data.bricklinkCurrentNewLots;
        if (data.bricklinkCurrentNewLots > 50) {
          reasons.push(
            `High market availability (${data.bricklinkCurrentNewLots} lots)`,
          );
        } else if (data.bricklinkCurrentNewLots < 10) {
          reasons.push(`Limited supply (${data.bricklinkCurrentNewLots} lots)`);
        }
      }

      if (data.bricklinkSixMonthNewTimesSold) {
        dataPoints.bricklinkSixMonthNewTimesSold =
          data.bricklinkSixMonthNewTimesSold;
        if (data.bricklinkSixMonthNewTimesSold > 100) {
          reasons.push(
            `Strong 6mo sales (${data.bricklinkSixMonthNewTimesSold} transactions)`,
          );
        }
      }
    }

    // SECONDARY: 2. Liquidity & Velocity (25% weight) - Like trading volume in stocks
    if (hasPastSalesData) {
      const liquidityScore = this.analyzeLiquidityVelocity(data);
      scores.push({ score: liquidityScore, weight: 0.25 });

      // Add reasoning based on velocity and liquidity
      if (data.bricklinkSalesVelocity !== undefined) {
        dataPoints.bricklinkSalesVelocity = data.bricklinkSalesVelocity;
        if (data.bricklinkSalesVelocity > 1) {
          reasons.push(
            `High liquidity (${
              data.bricklinkSalesVelocity.toFixed(2)
            } sales/day)`,
          );
        } else if (data.bricklinkSalesVelocity > 0.1) {
          reasons.push(
            `Moderate liquidity (${
              (data.bricklinkSalesVelocity * 30).toFixed(0)
            } sales/month)`,
          );
        } else {
          reasons.push("Low liquidity");
        }
      }

      if (data.bricklinkRecentSales30d !== undefined) {
        dataPoints.bricklinkRecentSales30d = data.bricklinkRecentSales30d;
        if (data.bricklinkRecentSales30d > 30) {
          reasons.push(
            `Active trading (${data.bricklinkRecentSales30d} sales in 30d)`,
          );
        }
      }
    } else if (hasLegacyBricklinkData && !hasBricklinkPricing) {
      // Fallback to legacy Bricklink data ONLY if no pricing data (reduced weight)
      const resaleScore = this.analyzeBricklinkActivity(
        data.bricklinkTimesSold,
        data.bricklinkTotalQty,
      );
      scores.push({ score: resaleScore, weight: 0.15 });

      if (data.bricklinkTimesSold !== undefined) {
        dataPoints.bricklinkTimesSold = data.bricklinkTimesSold;
        if (data.bricklinkTimesSold > 100) {
          reasons.push(
            `Active resale market (${data.bricklinkTimesSold} transactions)`,
          );
        }
      }
    }

    // 3. Momentum & Trends (10% weight) - Like price/volume trends
    if (hasPastSalesData && data.bricklinkPriceTrend) {
      const momentumScore = this.analyzeMomentumTrends(data);
      scores.push({ score: momentumScore, weight: 0.10 });

      // Add reasoning based on trends
      if (data.bricklinkPriceTrend === "increasing") {
        reasons.push("Bullish price trend (increasing demand)");
      } else if (data.bricklinkPriceTrend === "decreasing") {
        reasons.push("Bearish price trend (weakening demand)");
      }

      if (data.bricklinkVolumeTrend === "increasing") {
        reasons.push("Rising transaction volume");
      }

      if (data.bricklinkRSI !== undefined) {
        dataPoints.bricklinkRSI = data.bricklinkRSI;
        if (data.bricklinkRSI > 70) {
          reasons.push(`Overbought (RSI: ${data.bricklinkRSI.toFixed(0)})`);
        } else if (data.bricklinkRSI < 30) {
          reasons.push(`Oversold (RSI: ${data.bricklinkRSI.toFixed(0)})`);
        }
      }
    }

    // 4. Community Sentiment (3% weight) - Like analyst ratings
    if (hasRedditData) {
      const communityScore = this.analyzeCommunitySentiment(
        data.redditPosts,
        data.redditAverageScore,
        data.redditTotalComments,
      );
      scores.push({ score: communityScore, weight: 0.03 });

      if (data.redditPosts !== undefined && data.redditPosts > 0) {
        dataPoints.redditPosts = data.redditPosts;
        if (data.redditPosts > 20) {
          reasons.push(`Strong community buzz (${data.redditPosts} posts)`);
        }
      }
    }

    // 5. Retail Activity (2% weight) - Market awareness indicator
    if (hasSalesData) {
      const salesScore = this.analyzeSalesVelocity(
        data.unitsSold,
        data.lifetimeSold,
      );
      scores.push({ score: salesScore, weight: 0.02 });

      if (data.unitsSold !== undefined && data.unitsSold > 1000) {
        dataPoints.unitsSold = data.unitsSold;
        reasons.push(
          `High retail awareness (${data.unitsSold.toLocaleString()} sold)`,
        );
      }
    }

    // Calculate final score
    const finalScore = scores.length > 0 ? this.weightedAverage(scores) : 50;

    // Calculate confidence - boost if we have past sales data
    const confidenceFactors = [
      data.bricklinkPastSalesCount,
      data.bricklinkSalesVelocity,
      data.bricklinkPriceTrend,
      data.unitsSold,
      data.bricklinkTimesSold,
      data.redditPosts,
    ];
    let confidence = this.calculateConfidence(confidenceFactors);

    // Boost confidence significantly if we have rich past sales data
    if (hasPastSalesData && data.bricklinkPastSalesCount! > 50) {
      confidence = Math.min(1.0, confidence + 0.2); // +20% confidence boost
    }

    return {
      value: Math.round(finalScore),
      confidence,
      reasoning: reasons.length > 0
        ? this.formatReasoning(reasons)
        : "Insufficient demand data for analysis.",
      dataPoints,
    };
  }

  /**
   * Score sales velocity on retail platforms
   */
  private analyzeSalesVelocity(
    unitsSold?: number,
    lifetimeSold?: number,
  ): number {
    const sold = unitsSold ?? lifetimeSold ?? 0;

    // Scoring based on sales volume
    // 0-10 = 0-30 (very low)
    // 10-50 = 30-50 (low)
    // 50-200 = 50-70 (moderate)
    // 200-1000 = 70-85 (good)
    // >1000 = 85-100 (excellent)

    if (sold === 0) return 0;
    if (sold < 10) return sold * 3; // 0-30
    if (sold < 50) return 30 + ((sold - 10) / 40) * 20; // 30-50
    if (sold < 200) return 50 + ((sold - 50) / 150) * 20; // 50-70
    if (sold < 1000) return 70 + ((sold - 200) / 800) * 15; // 70-85
    return Math.min(100, 85 + ((sold - 1000) / 1000) * 15); // 85-100
  }

  /**
   * Score Bricklink resale activity
   * Factors in both transaction count and total volume
   */
  private analyzeBricklinkActivity(
    timesSold?: number,
    totalQty?: number,
  ): number {
    const transactions = timesSold ?? 0;
    const volume = totalQty ?? 0;

    // If we have both metrics, combine them with weights
    // Transaction count (60% weight) - shows market liquidity
    // Total volume (40% weight) - shows actual demand magnitude

    if (transactions === 0 && volume === 0) return 0;

    let transactionScore = 0;
    let volumeScore = 0;

    // Transaction score (0-100)
    // 0 = 0 (no activity)
    // 1-10 = 20-40 (minimal)
    // 10-50 = 40-60 (low)
    // 50-100 = 60-80 (moderate)
    // >100 = 80-100 (active market)
    if (transactions === 0) {
      transactionScore = 0;
    } else if (transactions < 10) {
      transactionScore = 20 + (transactions / 10) * 20; // 20-40
    } else if (transactions < 50) {
      transactionScore = 40 + ((transactions - 10) / 40) * 20; // 40-60
    } else if (transactions < 100) {
      transactionScore = 60 + ((transactions - 50) / 50) * 20; // 60-80
    } else {
      transactionScore = Math.min(100, 80 + ((transactions - 100) / 100) * 20); // 80-100
    }

    // Volume score (0-100)
    // 0 = 0 (no volume)
    // 1-50 = 20-40 (minimal volume)
    // 50-200 = 40-60 (low volume)
    // 200-500 = 60-75 (moderate volume)
    // 500-1000 = 75-85 (high volume)
    // >1000 = 85-100 (very high volume)
    if (volume === 0) {
      volumeScore = 0;
    } else if (volume < 50) {
      volumeScore = 20 + (volume / 50) * 20; // 20-40
    } else if (volume < 200) {
      volumeScore = 40 + ((volume - 50) / 150) * 20; // 40-60
    } else if (volume < 500) {
      volumeScore = 60 + ((volume - 200) / 300) * 15; // 60-75
    } else if (volume < 1000) {
      volumeScore = 75 + ((volume - 500) / 500) * 10; // 75-85
    } else {
      volumeScore = Math.min(100, 85 + ((volume - 1000) / 1000) * 15); // 85-100
    }

    // If only one metric is available, use it at full weight
    if (transactions === 0 && volume > 0) return volumeScore;
    if (volume === 0 && transactions > 0) return transactionScore;

    // Weighted average: 60% transactions, 40% volume
    return Math.round(transactionScore * 0.6 + volumeScore * 0.4);
  }

  /**
   * Score community sentiment from Reddit
   */
  private analyzeCommunitySentiment(
    posts?: number,
    averageScore?: number,
    totalComments?: number,
  ): number {
    if (!posts || posts === 0) return 20; // Some score for no data (neutral-low)

    const scores: number[] = [];

    // Post volume score (0-100)
    if (posts < 5) {
      scores.push(30 + posts * 5); // 30-55
    } else if (posts < 20) {
      scores.push(55 + ((posts - 5) / 15) * 25); // 55-80
    } else {
      scores.push(Math.min(100, 80 + ((posts - 20) / 20) * 20)); // 80-100
    }

    // Average score sentiment (if available)
    if (averageScore !== undefined) {
      if (averageScore < 10) {
        scores.push(30); // Low engagement
      } else if (averageScore < 50) {
        scores.push(50 + (averageScore / 50) * 20); // 50-70
      } else if (averageScore < 200) {
        scores.push(70 + ((averageScore - 50) / 150) * 20); // 70-90
      } else {
        scores.push(Math.min(100, 90 + ((averageScore - 200) / 100))); // 90-100
      }
    }

    // Comment engagement (if available)
    if (totalComments !== undefined && totalComments > 0) {
      const avgCommentsPerPost = totalComments / posts;
      if (avgCommentsPerPost > 20) {
        scores.push(90); // High discussion
      } else if (avgCommentsPerPost > 10) {
        scores.push(70); // Good discussion
      } else {
        scores.push(50); // Moderate discussion
      }
    }

    // Return average of available scores
    if (scores.length === 0) return 20; // Default neutral-low score
    return scores.reduce((sum, s) => sum + s, 0) / scores.length;
  }

  /**
   * Score engagement metrics (views, likes, comments)
   */
  private analyzeEngagement(
    views?: number,
    likes?: number,
    comments?: number,
  ): number {
    const scores: number[] = [];

    // Views score
    if (views !== undefined) {
      if (views < 1000) {
        scores.push(views / 1000 * 40); // 0-40
      } else if (views < 10000) {
        scores.push(40 + ((views - 1000) / 9000) * 30); // 40-70
      } else {
        scores.push(Math.min(100, 70 + ((views - 10000) / 10000) * 30)); // 70-100
      }
    }

    // Likes score
    if (likes !== undefined) {
      if (likes < 50) {
        scores.push(likes / 50 * 40); // 0-40
      } else if (likes < 500) {
        scores.push(40 + ((likes - 50) / 450) * 40); // 40-80
      } else {
        scores.push(Math.min(100, 80 + ((likes - 500) / 500) * 20)); // 80-100
      }
    }

    // Comments score (indicator of interest)
    if (comments !== undefined) {
      if (comments < 10) {
        scores.push(comments * 5); // 0-50
      } else if (comments < 50) {
        scores.push(50 + ((comments - 10) / 40) * 30); // 50-80
      } else {
        scores.push(Math.min(100, 80 + ((comments - 50) / 50) * 20)); // 80-100
      }
    }

    // Return average or neutral if no data
    return scores.length > 0
      ? scores.reduce((sum, s) => sum + s, 0) / scores.length
      : 50;
  }

  /**
   * NEW: Analyze liquidity and velocity metrics
   * Inspired by trading volume analysis in stock markets
   * Higher velocity = more liquid market = better for investment
   */
  private analyzeLiquidityVelocity(data: DemandData): number {
    const scores: number[] = [];

    // 1. Sales velocity score (transactions per day)
    if (data.bricklinkSalesVelocity !== undefined) {
      const velocity = data.bricklinkSalesVelocity;

      // Scoring based on daily transaction rate
      // >2/day = 90-100 (very high liquidity)
      // 1-2/day = 80-90 (high liquidity)
      // 0.5-1/day = 70-80 (good liquidity)
      // 0.1-0.5/day = 50-70 (moderate)
      // 0.03-0.1/day (1-3/month) = 30-50 (low)
      // <0.03/day (<1/month) = 0-30 (very low)

      if (velocity >= 2) {
        scores.push(Math.min(100, 90 + (velocity - 2) * 5));
      } else if (velocity >= 1) {
        scores.push(80 + (velocity - 1) * 10);
      } else if (velocity >= 0.5) {
        scores.push(70 + (velocity - 0.5) * 20);
      } else if (velocity >= 0.1) {
        scores.push(50 + (velocity - 0.1) * 50);
      } else if (velocity >= 0.03) {
        scores.push(30 + (velocity - 0.03) * 285);
      } else {
        scores.push(velocity * 1000); // 0-30 range
      }
    }

    // 2. Recent activity trend (weighted towards recent)
    // Compare 30d vs 60d vs 90d to detect acceleration/deceleration
    if (
      data.bricklinkRecentSales30d !== undefined &&
      data.bricklinkRecentSales90d !== undefined
    ) {
      const recent30d = data.bricklinkRecentSales30d;
      const recent90d = data.bricklinkRecentSales90d;

      // Normalize to per-30-day rates
      const rate30d = recent30d;
      const rate90d = recent90d / 3;

      // Score based on recent acceleration
      // Accelerating (30d > 90d avg) = bonus points
      // Decelerating (30d < 90d avg) = penalty

      const acceleration = rate30d / (rate90d || 1);

      if (acceleration > 1.5) {
        scores.push(90); // Strong acceleration
      } else if (acceleration > 1.2) {
        scores.push(75); // Moderate acceleration
      } else if (acceleration > 0.8) {
        scores.push(60); // Stable
      } else if (acceleration > 0.5) {
        scores.push(40); // Decelerating
      } else {
        scores.push(20); // Strongly decelerating
      }
    }

    // 3. Average days between sales (inverse of velocity, but complementary)
    if (data.bricklinkAvgDaysBetweenSales !== undefined) {
      const daysBetween = data.bricklinkAvgDaysBetweenSales;

      // Scoring based on time between transactions
      // <1 day = 95-100 (excellent)
      // 1-3 days = 80-95 (very good)
      // 3-7 days = 65-80 (good)
      // 7-30 days = 40-65 (moderate)
      // >30 days = 0-40 (poor)

      if (daysBetween < 1) {
        scores.push(95 + (1 - daysBetween) * 5);
      } else if (daysBetween < 3) {
        scores.push(80 + (3 - daysBetween) * 7.5);
      } else if (daysBetween < 7) {
        scores.push(65 + (7 - daysBetween) * 3.75);
      } else if (daysBetween < 30) {
        scores.push(40 + (30 - daysBetween) * 1.1);
      } else {
        scores.push(Math.max(0, 40 - (daysBetween - 30) / 2));
      }
    }

    // Return weighted average
    return scores.length > 0
      ? scores.reduce((sum, s) => sum + s, 0) / scores.length
      : 50;
  }

  /**
   * NEW: Analyze momentum and trend metrics
   * Inspired by technical analysis in stock trading
   * Considers price trends, volume trends, and RSI
   */
  private analyzeMomentumTrends(data: DemandData): number {
    const scores: number[] = [];

    // 1. Price trend direction (bullish/bearish/neutral)
    if (data.bricklinkPriceTrend !== undefined) {
      const trend = data.bricklinkPriceTrend;
      const percentChange = data.bricklinkPriceChangePercent || 0;

      if (trend === "increasing") {
        // Bullish trend - positive for demand
        // Higher percent change = stronger signal
        if (percentChange > 20) {
          scores.push(90); // Strong bullish
        } else if (percentChange > 10) {
          scores.push(75); // Moderate bullish
        } else {
          scores.push(60); // Weak bullish
        }
      } else if (trend === "stable") {
        scores.push(50); // Neutral
      } else {
        // Bearish trend - negative for demand
        if (percentChange < -20) {
          scores.push(10); // Strong bearish
        } else if (percentChange < -10) {
          scores.push(25); // Moderate bearish
        } else {
          scores.push(40); // Weak bearish
        }
      }
    }

    // 2. Volume trend (increasing volume = stronger demand signal)
    if (data.bricklinkVolumeTrend !== undefined) {
      const volumeTrend = data.bricklinkVolumeTrend;

      if (volumeTrend === "increasing") {
        scores.push(80); // Rising volume confirms trend strength
      } else if (volumeTrend === "stable") {
        scores.push(50); // Stable volume
      } else {
        scores.push(30); // Declining volume weakens trend
      }
    }

    // 3. Relative Strength Index (RSI)
    // RSI 30-70 is healthy range
    // >70 = overbought (may correct downward)
    // <30 = oversold (may bounce upward)
    if (data.bricklinkRSI !== undefined) {
      const rsi = data.bricklinkRSI;

      if (rsi >= 50 && rsi <= 70) {
        scores.push(85); // Strong, not overbought
      } else if (rsi > 70 && rsi <= 80) {
        scores.push(70); // Overbought, caution
      } else if (rsi > 80) {
        scores.push(50); // Very overbought, high risk
      } else if (rsi >= 30 && rsi < 50) {
        scores.push(60); // Weak but not oversold
      } else if (rsi >= 20 && rsi < 30) {
        scores.push(55); // Oversold, potential opportunity
      } else {
        scores.push(40); // Very oversold
      }
    }

    // 4. Price momentum (linear regression slope)
    if (data.bricklinkPriceMomentum !== undefined) {
      const momentum = data.bricklinkPriceMomentum;

      // Positive momentum = bullish, negative = bearish
      // Normalized scoring
      if (momentum > 100) {
        scores.push(90); // Strong positive momentum
      } else if (momentum > 50) {
        scores.push(75);
      } else if (momentum > 0) {
        scores.push(60);
      } else if (momentum > -50) {
        scores.push(40);
      } else if (momentum > -100) {
        scores.push(25);
      } else {
        scores.push(10); // Strong negative momentum
      }
    }

    // 5. Price volatility (lower is better for investment)
    if (data.bricklinkPriceVolatility !== undefined) {
      const volatility = data.bricklinkPriceVolatility;

      // Coefficient of variation: 0-1+ range
      // <0.1 = very stable (90-100)
      // 0.1-0.2 = stable (75-90)
      // 0.2-0.4 = moderate volatility (50-75)
      // >0.4 = high volatility (0-50)

      if (volatility < 0.1) {
        scores.push(90 + (0.1 - volatility) * 100);
      } else if (volatility < 0.2) {
        scores.push(75 + (0.2 - volatility) * 150);
      } else if (volatility < 0.4) {
        scores.push(50 + (0.4 - volatility) * 125);
      } else {
        scores.push(Math.max(0, 50 - (volatility - 0.4) * 100));
      }
    }

    // Return weighted average
    return scores.length > 0
      ? scores.reduce((sum, s) => sum + s, 0) / scores.length
      : 50;
  }

  /**
   * PRIMARY: Analyze Bricklink market pricing data
   * Treats pricing as a direct indicator of market demand
   * Higher prices + limited supply = higher demand score
   * Price growth trends = increasing demand
   */
  private analyzeBricklinkPricing(data: DemandData): number {
    const scores: number[] = [];

    // 1. Price trend score (comparing current vs 6-month average)
    if (data.bricklinkCurrentNewAvg && data.bricklinkSixMonthNewAvg) {
      const current = data.bricklinkCurrentNewAvg;
      const sixMonth = data.bricklinkSixMonthNewAvg;
      const percentChange = ((current - sixMonth) / sixMonth) * 100;

      // Positive trend = increasing demand
      // >20% increase = 90-100 (very strong demand)
      // 10-20% increase = 75-90 (strong demand)
      // 0-10% increase = 60-75 (moderate demand)
      // Stable (-5 to 0%) = 50-60 (stable demand)
      // Declining = 20-50 (weakening demand)

      if (percentChange > 20) {
        scores.push(Math.min(100, 90 + percentChange / 2));
      } else if (percentChange > 10) {
        scores.push(75 + (percentChange - 10) * 1.5);
      } else if (percentChange > 0) {
        scores.push(60 + percentChange * 1.5);
      } else if (percentChange > -5) {
        scores.push(50 + percentChange * 2);
      } else if (percentChange > -15) {
        scores.push(35 + (percentChange + 15) * 1.5);
      } else {
        scores.push(Math.max(10, 35 + (percentChange + 15)));
      }
    } else if (data.bricklinkCurrentNewAvg) {
      // Only current price available - assume moderate demand
      scores.push(60);
    }

    // 2. Market liquidity score (based on lots available)
    if (data.bricklinkCurrentNewLots !== undefined) {
      const lots = data.bricklinkCurrentNewLots;

      // Interpret lots in context of demand:
      // Very few lots (<5) = HIGH demand (items selling fast) = 80-100
      // Few lots (5-15) = Good demand = 65-80
      // Moderate lots (15-30) = Moderate demand = 50-65
      // Many lots (30-70) = Lower demand = 35-50
      // Excessive lots (>70) = Oversupply/low demand = 20-35

      if (lots < 5) {
        scores.push(Math.max(80, 100 - lots * 4));
      } else if (lots < 15) {
        scores.push(65 + (15 - lots) * 1.5);
      } else if (lots < 30) {
        scores.push(50 + (30 - lots) * 1);
      } else if (lots < 70) {
        scores.push(35 + (70 - lots) * 0.375);
      } else {
        scores.push(Math.max(10, 35 - (lots - 70) * 0.25));
      }
    }

    // 3. Transaction volume score (6-month times sold)
    if (data.bricklinkSixMonthNewTimesSold !== undefined) {
      const timesSold = data.bricklinkSixMonthNewTimesSold;

      // More transactions = higher demand
      // >200 times = 90-100 (very high demand)
      // 100-200 = 75-90 (high demand)
      // 50-100 = 60-75 (moderate-high demand)
      // 20-50 = 45-60 (moderate demand)
      // 5-20 = 30-45 (low-moderate demand)
      // <5 = 10-30 (low demand)

      if (timesSold > 200) {
        scores.push(Math.min(100, 90 + (timesSold - 200) / 20));
      } else if (timesSold > 100) {
        scores.push(75 + (timesSold - 100) * 0.15);
      } else if (timesSold > 50) {
        scores.push(60 + (timesSold - 50) * 0.3);
      } else if (timesSold > 20) {
        scores.push(45 + (timesSold - 20) * 0.5);
      } else if (timesSold > 5) {
        scores.push(30 + (timesSold - 5) * 1);
      } else {
        scores.push(10 + timesSold * 4);
      }
    }

    // 4. Quantity sold score (total quantity in 6 months)
    if (data.bricklinkSixMonthNewQty !== undefined) {
      const qty = data.bricklinkSixMonthNewQty;

      // Higher quantity = higher market interest
      // >500 units = 90-100 (very high demand)
      // 200-500 = 75-90 (high demand)
      // 100-200 = 60-75 (moderate-high demand)
      // 50-100 = 45-60 (moderate demand)
      // 20-50 = 30-45 (low-moderate demand)
      // <20 = 10-30 (low demand)

      if (qty > 500) {
        scores.push(Math.min(100, 90 + (qty - 500) / 50));
      } else if (qty > 200) {
        scores.push(75 + (qty - 200) * 0.05);
      } else if (qty > 100) {
        scores.push(60 + (qty - 100) * 0.15);
      } else if (qty > 50) {
        scores.push(45 + (qty - 50) * 0.3);
      } else if (qty > 20) {
        scores.push(30 + (qty - 20) * 0.5);
      } else {
        scores.push(10 + qty);
      }
    }

    // 5. Price spread score (min vs max indicates market competitiveness)
    if (data.bricklinkCurrentNewMin && data.bricklinkCurrentNewMax) {
      const min = data.bricklinkCurrentNewMin;
      const max = data.bricklinkCurrentNewMax;
      const spread = (max - min) / min * 100;

      // Narrow spread (<20%) = competitive market, high demand = 80-100
      // Moderate spread (20-50%) = normal market = 60-80
      // Wide spread (>50%) = fragmented market, uncertain demand = 40-60

      if (spread < 20) {
        scores.push(80 + (20 - spread));
      } else if (spread < 50) {
        scores.push(60 + (50 - spread) * 0.67);
      } else {
        scores.push(Math.max(30, 60 - (spread - 50) * 0.4));
      }
    }

    // Return average of available scores, or neutral score if no data
    return scores.length > 0
      ? scores.reduce((sum, s) => sum + s, 0) / scores.length
      : 50;
  }
}
