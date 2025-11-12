/**
 * Base analyzer class providing common functionality
 * Following SOLID principles: Single Responsibility, Open/Closed
 */

import type { AnalysisScore, IAnalyzer } from "../types.ts";

export abstract class BaseAnalyzer<T> implements IAnalyzer<T> {
  protected name: string;
  protected description: string;

  constructor(name: string, description: string) {
    this.name = name;
    this.description = description;
  }

  abstract analyze(data: T): Promise<AnalysisScore>;

  getName(): string {
    return this.name;
  }

  getDescription(): string {
    return this.description;
  }

  /**
   * Helper: Normalize a value to 0-100 scale
   */
  protected normalizeScore(
    value: number,
    min: number,
    max: number,
  ): number {
    if (max === min) return 50; // Neutral score if no range
    const normalized = ((value - min) / (max - min)) * 100;
    return Math.max(0, Math.min(100, normalized)); // Clamp to 0-100
  }

  /**
   * Helper: Calculate weighted average of multiple scores
   */
  protected weightedAverage(
    scores: Array<{ score: number; weight: number }>,
  ): number {
    const totalWeight = scores.reduce((sum, s) => sum + s.weight, 0);
    if (totalWeight === 0) return 0;

    const weightedSum = scores.reduce(
      (sum, s) => sum + s.score * s.weight,
      0,
    );
    return weightedSum / totalWeight;
  }

  /**
   * Helper: Calculate confidence based on data availability
   */
  protected calculateConfidence(
    dataPoints: Array<unknown | undefined>,
  ): number {
    const available = dataPoints.filter((d) => d !== undefined && d !== null)
      .length;
    const total = dataPoints.length;
    return available / total;
  }

  /**
   * Helper: Safely get a number value with fallback
   */
  protected safeNumber(
    value: number | undefined | null,
    fallback = 0,
  ): number {
    return value ?? fallback;
  }

  /**
   * Helper: Check if a date is in the future
   */
  protected isFuture(date: Date | undefined | null): boolean {
    if (!date) return false;
    return new Date(date).getTime() > Date.now();
  }

  /**
   * Helper: Calculate days between two dates
   */
  protected daysBetween(date1: Date, date2: Date): number {
    const diff = Math.abs(date2.getTime() - date1.getTime());
    return Math.floor(diff / (1000 * 60 * 60 * 24));
  }

  /**
   * Helper: Calculate percentage change
   */
  protected percentageChange(oldValue: number, newValue: number): number {
    if (oldValue === 0) return 0;
    return ((newValue - oldValue) / oldValue) * 100;
  }

  /**
   * Helper: Format reasoning string
   */
  protected formatReasoning(reasons: string[]): string {
    return reasons.filter((r) => r.length > 0).join(". ") + ".";
  }
}
