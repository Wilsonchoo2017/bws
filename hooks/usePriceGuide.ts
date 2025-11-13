import { useEffect, useState } from "preact/hooks";

export interface RecommendedBuyPrice {
  price: number; // In dollars (not cents)
  reasoning: string;
  confidence: number; // 0-1
}

export interface PriceGuideData {
  recommendedBuyPrice?: RecommendedBuyPrice;
  loading: boolean;
  error?: string;
}

/**
 * Hook to fetch price guide data for multiple LEGO products
 * @param legoIds Array of LEGO set numbers to fetch price guide for
 * @returns Map of legoId to price guide data
 */
export function usePriceGuide(legoIds: string[]): Map<string, PriceGuideData> {
  const [priceGuideMap, setPriceGuideMap] = useState<
    Map<string, PriceGuideData>
  >(
    new Map(),
  );

  useEffect(() => {
    // Initialize loading state for all items
    const initialMap = new Map<string, PriceGuideData>();
    legoIds.forEach((legoId) => {
      initialMap.set(legoId, { loading: true });
    });
    setPriceGuideMap(initialMap);

    // Fetch price guide data for each item
    const fetchPriceGuide = async (legoId: string) => {
      try {
        const response = await fetch(
          `/api/analysis/${legoId}?strategy=Investment Focus`,
        );

        if (!response.ok) {
          throw new Error(`Failed to fetch price guide for ${legoId}`);
        }

        const data = await response.json();

        setPriceGuideMap((prev) => {
          const newMap = new Map(prev);
          newMap.set(legoId, {
            recommendedBuyPrice: data.recommendedBuyPrice,
            loading: false,
          });
          return newMap;
        });
      } catch (error) {
        setPriceGuideMap((prev) => {
          const newMap = new Map(prev);
          newMap.set(legoId, {
            loading: false,
            error: error instanceof Error ? error.message : "Unknown error",
          });
          return newMap;
        });
      }
    };

    // Fetch all price guides in parallel
    Promise.all(legoIds.map(fetchPriceGuide));
  }, [legoIds.join(",")]); // Re-fetch when the list of IDs changes

  return priceGuideMap;
}
