/**
 * String similarity utilities using Levenshtein distance algorithm.
 * Used for fuzzy matching product names to detect duplicates across sources.
 * Follows Single Responsibility Principle - focused on string comparison only.
 */

/**
 * Calculates Levenshtein distance between two strings
 * The Levenshtein distance is the minimum number of single-character edits
 * (insertions, deletions, or substitutions) required to change one string into another.
 *
 * @param str1 - First string
 * @param str2 - Second string
 * @returns Number of edits required (lower is more similar)
 */
export function levenshteinDistance(str1: string, str2: string): number {
  const len1 = str1.length;
  const len2 = str2.length;

  // Create a 2D array to store distances
  const matrix: number[][] = Array(len1 + 1)
    .fill(null)
    .map(() => Array(len2 + 1).fill(0));

  // Initialize first column and row
  for (let i = 0; i <= len1; i++) {
    matrix[i][0] = i;
  }
  for (let j = 0; j <= len2; j++) {
    matrix[0][j] = j;
  }

  // Fill in the rest of the matrix
  for (let i = 1; i <= len1; i++) {
    for (let j = 1; j <= len2; j++) {
      const cost = str1[i - 1] === str2[j - 1] ? 0 : 1;
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1, // Deletion
        matrix[i][j - 1] + 1, // Insertion
        matrix[i - 1][j - 1] + cost, // Substitution
      );
    }
  }

  return matrix[len1][len2];
}

/**
 * Normalizes a string for comparison
 * Converts to lowercase, removes extra whitespace, and strips common LEGO-related words
 *
 * @param str - String to normalize
 * @returns Normalized string
 */
export function normalizeString(str: string): string {
  return str
    .toLowerCase()
    .replace(/\blego\b/gi, "") // Remove "LEGO" word
    .replace(/\bset\b/gi, "") // Remove "Set" word
    .replace(/\s+/g, " ") // Normalize whitespace
    .trim();
}

/**
 * Calculates similarity score between two strings (0 to 1)
 * 0 = completely different, 1 = identical
 * Uses normalized Levenshtein distance
 *
 * @param str1 - First string
 * @param str2 - Second string
 * @returns Similarity score between 0 and 1
 */
export function calculateSimilarity(str1: string, str2: string): number {
  // Normalize both strings
  const normalized1 = normalizeString(str1);
  const normalized2 = normalizeString(str2);

  // Handle edge cases
  if (normalized1 === normalized2) return 1.0;
  if (normalized1.length === 0 || normalized2.length === 0) return 0.0;

  // Calculate Levenshtein distance
  const distance = levenshteinDistance(normalized1, normalized2);

  // Convert distance to similarity score (0-1)
  const maxLength = Math.max(normalized1.length, normalized2.length);
  const similarity = 1 - distance / maxLength;

  return similarity;
}

/**
 * Checks if two strings are similar enough based on a threshold
 *
 * @param str1 - First string
 * @param str2 - Second string
 * @param threshold - Minimum similarity score (0-1) to consider strings similar (default 0.7)
 * @returns True if strings are similar enough, false otherwise
 */
export function isSimilarEnough(
  str1: string,
  str2: string,
  threshold = 0.7,
): boolean {
  const similarity = calculateSimilarity(str1, str2);
  return similarity >= threshold;
}

/**
 * Finds the best match from an array of candidate strings
 *
 * @param target - String to match against
 * @param candidates - Array of candidate strings
 * @param threshold - Minimum similarity threshold (default 0.7)
 * @returns Object with bestMatch, similarity score, and index, or null if no match above threshold
 */
export function findBestMatch(
  target: string,
  candidates: string[],
  threshold = 0.7,
): { match: string; similarity: number; index: number } | null {
  let bestMatch: { match: string; similarity: number; index: number } | null =
    null;

  candidates.forEach((candidate, index) => {
    const similarity = calculateSimilarity(target, candidate);

    if (
      similarity >= threshold &&
      (!bestMatch || similarity > bestMatch.similarity)
    ) {
      bestMatch = { match: candidate, similarity, index };
    }
  });

  return bestMatch;
}
