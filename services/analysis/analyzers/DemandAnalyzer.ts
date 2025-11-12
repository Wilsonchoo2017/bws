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

  async analyze(data: DemandData): Promise<AnalysisScore> {
    const scores: Array<{ score: number; weight: number }> = [];
    const reasons: string[] = [];
    const dataPoints: Record<string, unknown> = {};

    // 1. Sales velocity analysis (Shopee)
    if (data.unitsSold !== undefined || data.lifetimeSold !== undefined) {
      const salesScore = this.analyzeSalesVelocity(
        data.unitsSold,
        data.lifetimeSold,
      );
      scores.push({ score: salesScore, weight: 0.3 });

      if (data.unitsSold !== undefined) {
        dataPoints.unitsSold = data.unitsSold;
        if (data.unitsSold > 1000) {
          reasons.push(
            `High sales volume (${data.unitsSold.toLocaleString()} units sold)`,
          );
        } else if (data.unitsSold > 100) {
          reasons.push(
            `Moderate sales (${data.unitsSold.toLocaleString()} sold)`,
          );
        } else if (data.unitsSold < 10) {
          reasons.push("Low sales volume");
        }
      }
    }

    // 2. Bricklink resale activity
    if (
      data.bricklinkTimesSold !== undefined ||
      data.bricklinkTotalQty !== undefined
    ) {
      const resaleScore = this.analyzeBricklinkActivity(
        data.bricklinkTimesSold,
        data.bricklinkTotalQty,
      );
      scores.push({ score: resaleScore, weight: 0.25 });

      if (data.bricklinkTimesSold !== undefined) {
        dataPoints.bricklinkTimesSold = data.bricklinkTimesSold;
        if (data.bricklinkTimesSold > 100) {
          reasons.push(
            `Active resale market (${data.bricklinkTimesSold} transactions)`,
          );
        } else if (data.bricklinkTimesSold < 10) {
          reasons.push("Limited resale activity on Bricklink");
        }
      }
    }

    // 3. Community engagement (Reddit sentiment)
    if (
      data.redditPosts !== undefined ||
      data.redditTotalScore !== undefined
    ) {
      const communityScore = this.analyzeCommunitySentiment(
        data.redditPosts,
        data.redditAverageScore,
        data.redditTotalComments,
      );
      scores.push({ score: communityScore, weight: 0.25 });

      if (data.redditPosts !== undefined && data.redditPosts > 0) {
        dataPoints.redditPosts = data.redditPosts;
        dataPoints.redditAverageScore = data.redditAverageScore;

        if (data.redditPosts > 20) {
          reasons.push(
            `Strong community interest (${data.redditPosts} Reddit posts)`,
          );
        } else if (data.redditPosts > 5) {
          reasons.push(
            `Moderate community discussion (${data.redditPosts} posts)`,
          );
        }

        if (
          data.redditAverageScore !== undefined &&
          data.redditAverageScore > 100
        ) {
          reasons.push(
            `Positive community sentiment (avg ${
              Math.round(data.redditAverageScore)
            } upvotes)`,
          );
        }
      } else {
        reasons.push("No Reddit community discussion found");
      }
    }

    // 4. Engagement metrics (views, likes, comments)
    if (
      data.viewCount !== undefined ||
      data.likedCount !== undefined ||
      data.commentCount !== undefined
    ) {
      const engagementScore = this.analyzeEngagement(
        data.viewCount,
        data.likedCount,
        data.commentCount,
      );
      scores.push({ score: engagementScore, weight: 0.2 });

      if (data.viewCount !== undefined && data.viewCount > 10000) {
        dataPoints.viewCount = data.viewCount;
        reasons.push(
          `High visibility (${(data.viewCount / 1000).toFixed(0)}K views)`,
        );
      }

      if (data.likedCount !== undefined && data.likedCount > 500) {
        dataPoints.likedCount = data.likedCount;
        reasons.push(`Popular listing (${data.likedCount} likes)`);
      }
    }

    // Calculate final score
    const finalScore = scores.length > 0 ? this.weightedAverage(scores) : 50; // Neutral if no data

    // Calculate confidence based on data availability
    const confidence = this.calculateConfidence([
      data.unitsSold,
      data.lifetimeSold,
      data.bricklinkTimesSold,
      data.redditPosts,
      data.viewCount,
      data.likedCount,
    ]);

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
   */
  private analyzeBricklinkActivity(
    timesSold?: number,
    totalQty?: number,
  ): number {
    const transactions = timesSold ?? 0;
    const quantity = totalQty ?? 0;

    // Scoring based on transaction count
    // 0 = 0 (no activity)
    // 1-10 = 20-40 (minimal)
    // 10-50 = 40-60 (low)
    // 50-100 = 60-80 (moderate)
    // >100 = 80-100 (active market)

    if (transactions === 0) return 0;
    if (transactions < 10) return 20 + (transactions / 10) * 20; // 20-40
    if (transactions < 50) return 40 + ((transactions - 10) / 40) * 20; // 40-60
    if (transactions < 100) return 60 + ((transactions - 50) / 50) * 20; // 60-80
    return Math.min(100, 80 + ((transactions - 100) / 100) * 20); // 80-100
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
}
