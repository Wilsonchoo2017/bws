/**
 * ThemeMultiplierCalculator - Extract theme-based multiplier logic
 *
 * EXTRACTED FROM:
 * - services/value-investing/ValueCalculator.ts (lines 584-633)
 *
 * SOLID Principles:
 * - Single Responsibility: Only calculates theme multipliers
 * - Open/Closed: Easy to add new themes or change multipliers
 * - Dependency Inversion: Depends on configuration, not hardcoded values
 *
 * DRY Principle:
 * - Single source of truth for theme multiplier calculation
 */

import { VALUE_INVESTING_CONFIG as CONFIG } from "../../value-investing/ValueInvestingConfig.ts";

/**
 * Theme multiplier calculation result
 */
export interface ThemeMultiplierResult {
  /** Final multiplier (0.7-1.4 range) */
  multiplier: number;
  /** Matched theme name (or "Default") */
  theme: string;
  /** Human-readable explanation */
  explanation: string;
}

/**
 * Theme multiplier configuration
 */
const THEME_MULTIPLIERS = CONFIG.INTRINSIC_VALUE.THEME_MULTIPLIERS;

/**
 * ThemeMultiplierCalculator - Instance-based service for testability
 */
export class ThemeMultiplierCalculator {
  constructor(
    private config = THEME_MULTIPLIERS,
  ) {}

  /**
   * Calculate theme-based multiplier
   *
   * Premium themes (Star Wars, Architecture) command higher values
   * Budget themes (City, Friends) have lower resale value
   */
  calculate(theme?: string): ThemeMultiplierResult {
    if (!theme || theme.length === 0) {
      return {
        multiplier: this.config.DEFAULT,
        theme: "Default",
        explanation: `No theme specified, using default multiplier (${this.config.DEFAULT}×)`,
      };
    }

    // Normalize theme name (trim, lowercase for matching)
    const normalizedTheme = theme.trim();
    const lowercaseTheme = normalizedTheme.toLowerCase();

    // Direct match (case-insensitive)
    const directMatch = Object.keys(this.config).find(
      (key) => key !== "DEFAULT" && key.toLowerCase() === lowercaseTheme,
    );

    if (directMatch) {
      const multiplier = this.config[
        directMatch as keyof typeof this.config
      ] as number;
      return {
        multiplier,
        theme: directMatch,
        explanation: `${directMatch} theme (${multiplier}× multiplier)`,
      };
    }

    // Try alias matching (for variations like "Star Wars: The Clone Wars")
    if (lowercaseTheme.includes("star wars")) {
      return {
        multiplier: this.config["Star Wars"],
        theme: "Star Wars",
        explanation: `Star Wars variant detected (${this.config["Star Wars"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("harry potter")) {
      return {
        multiplier: this.config["Harry Potter"],
        theme: "Harry Potter",
        explanation: `Harry Potter variant detected (${this.config["Harry Potter"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("architecture")) {
      return {
        multiplier: this.config["Architecture"],
        theme: "Architecture",
        explanation: `Architecture variant detected (${this.config["Architecture"]}× multiplier)`,
      };
    }

    if (
      lowercaseTheme.includes("creator expert") ||
      lowercaseTheme.includes("creator")
    ) {
      return {
        multiplier: this.config["Creator Expert"],
        theme: "Creator Expert",
        explanation: `Creator Expert variant detected (${this.config["Creator Expert"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("technic")) {
      return {
        multiplier: this.config["Technic"],
        theme: "Technic",
        explanation: `Technic variant detected (${this.config["Technic"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("ideas") || lowercaseTheme.includes("cuusoo")) {
      return {
        multiplier: this.config["Ideas"],
        theme: "Ideas",
        explanation: `Ideas/CUUSOO variant detected (${this.config["Ideas"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("city")) {
      return {
        multiplier: this.config["City"],
        theme: "City",
        explanation: `City variant detected (${this.config["City"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("friends")) {
      return {
        multiplier: this.config["Friends"],
        theme: "Friends",
        explanation: `Friends variant detected (${this.config["Friends"]}× multiplier)`,
      };
    }

    if (lowercaseTheme.includes("duplo")) {
      return {
        multiplier: this.config["Duplo"],
        theme: "Duplo",
        explanation: `Duplo variant detected (${this.config["Duplo"]}× multiplier)`,
      };
    }

    // No match - return default
    return {
      multiplier: this.config.DEFAULT,
      theme: "Default",
      explanation: `Unknown theme "${normalizedTheme}", using default multiplier (${this.config.DEFAULT}×)`,
    };
  }

  /**
   * Get all supported themes and their multipliers
   */
  getSupportedThemes(): Record<string, number> {
    return { ...this.config };
  }

  /**
   * Check if a theme is premium (multiplier > 1.0)
   */
  isPremiumTheme(theme: string): boolean {
    const result = this.calculate(theme);
    return result.multiplier > 1.0;
  }
}
