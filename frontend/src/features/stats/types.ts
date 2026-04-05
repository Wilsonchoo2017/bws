export interface SourceCoverage {
  source: string;
  total_rows: number;
  distinct_sets: number;
  missing_sets: number;
  coverage_pct: number;
  latest_scraped: string | null;
}

export interface CoverageData {
  total_sets: number;
  sources: SourceCoverage[];
}
