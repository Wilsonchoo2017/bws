import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { LiquidityPanel } from './liquidity-panel';

function mockFetchResponses(responses: Record<string, unknown>) {
  return vi.spyOn(global, 'fetch').mockImplementation((input) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : (input as Request).url;
    for (const [pattern, data] of Object.entries(responses)) {
      if (url.includes(pattern)) {
        return Promise.resolve({
          json: () => Promise.resolve(data),
        } as Response);
      }
    }
    return Promise.resolve({
      json: () => Promise.resolve({ success: false }),
    } as Response);
  });
}

const BL_DATA = {
  success: true,
  data: {
    set_number: '71043',
    source: 'bricklink',
    total_months: 5,
    months_with_sales: 5,
    consistency: 1.0,
    total_txns: 26,
    total_qty: 30,
    avg_monthly_txns: 5.2,
    avg_monthly_qty: 6.0,
    recent_avg_txns: 5.8,
    trend_ratio: 1.12,
    listing_ratio: 16.9,
    listing_lots: 88,
    metrics: {
      volume: { value: 5.2, pct: 79, label: 'Avg txns/mo' },
      quantity: { value: 6.0, pct: 67, label: 'Avg qty/mo' },
      consistency: { value: 1.0, pct: 50, label: 'Consistency' },
      listing_ratio: { value: 16.9, pct: 51, label: 'Listing ratio' },
    },
    composite_pct: 64,
    rank: 640,
    size: 2951,
    monthly: [
      { label: '2024-11', txns: 4 },
      { label: '2024-12', txns: 6 },
      { label: '2025-01', txns: 5 },
      { label: '2025-02', txns: 5 },
      { label: '2025-03', txns: 6 },
    ],
  },
};

const BE_DATA = {
  success: true,
  data: {
    set_number: '71043',
    source: 'brickeconomy',
    total_months: 16,
    months_with_sales: 16,
    consistency: 1.0,
    total_txns: 405,
    total_qty: null,
    avg_monthly_txns: 25.3,
    avg_monthly_qty: null,
    recent_avg_txns: 32.4,
    trend_ratio: 1.28,
    metrics: {
      volume: { value: 25.3, pct: 60, label: 'Avg txns/mo' },
      consistency: { value: 1.0, pct: 50, label: 'Consistency' },
    },
    composite_pct: 56,
    rank: 614,
    size: 1515,
    monthly: [
      { label: '2024-01', txns: 20 },
      { label: '2024-02', txns: 22 },
      { label: '2024-03', txns: 30 },
    ],
  },
};

const COHORT_DATA = {
  success: true,
  data: {
    half_year: {
      key: '2025-H1',
      size: 184,
      rank: 23,
      composite_pct: null,
      volume_pct: null,
      consistency_pct: null,
      trend_pct: null,
      listing_ratio_pct: null,
    },
    theme: {
      key: 'Ninjago',
      size: 123,
      rank: 65,
      composite_pct: 45,
      volume_pct: 70,
      consistency_pct: 50,
      trend_pct: 30,
      listing_ratio_pct: 40,
    },
  },
};

describe('LiquidityPanel', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  afterEach(() => {
    fetchSpy?.mockRestore();
  });

  describe('source-level liquidity cards', () => {
    it('given BrickLink composite_pct 64, when rendered, then shows P64 badge', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('P64')).toBeInTheDocument();
      });
    });

    it('given BrickLink size 2951, when rendered, then shows n=2951', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('n=2951')).toBeInTheDocument();
      });
      expect(screen.queryByText('#640/2951')).not.toBeInTheDocument();
    });

    it('given BrickEconomy composite_pct 56, when rendered, then shows P56 badge', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': { success: false },
        'source=brickeconomy': BE_DATA,
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('P56')).toBeInTheDocument();
      });
    });

    it('given both sources, when rendered, then shows both labels', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': BE_DATA,
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('BrickLink')).toBeInTheDocument();
        expect(screen.getByText('BrickEconomy')).toBeInTheDocument();
      });
    });

    it('given individual metric pct 79, when rendered, then shows P79 badge', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('P79')).toBeInTheDocument();
      });
    });
  });

  describe('liquidity cohort grid', () => {
    it('given cohort with null composite_pct and rank #23/184, when rendered, then shows P88 (rank-derived)', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('P88')).toBeInTheDocument();
      });
    });

    it('given cohort with composite_pct 45, when rendered, then shows inline P45', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('P45')).toBeInTheDocument();
      });
    });

    it('given cohort with null composite_pct, when rendered, then rank percentile badge is colored by rank pct (P88 = emerald)', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        const p88 = screen.getByText('P88');
        expect(p88.closest('span')).toHaveClass('text-emerald-400');
      });
    });

    it('given cohort with composite_pct 45, when rendered, then rank badge uses composite color (orange)', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        // theme: rank 65/123 => P47, colored by overall=composite_pct(45) => orange
        const badge = screen.getByText('P47');
        expect(badge.closest('span')).toHaveClass('text-orange-500');
      });
    });

    it('given cohort grid, when rendered, then shows "higher = better" header', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('percentile vs peer group (higher = better)')).toBeInTheDocument();
      });
    });

    it('given cohort inline metrics with values, when rendered, then shows P-prefixed values', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        // theme cohort: volume_pct=70
        expect(screen.getByText('P70')).toBeInTheDocument();
      });
    });

    it('given cohort inline metrics with null values, when rendered, then shows -- placeholder', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        // half_year has all null pct fields
        const dashes = screen.getAllByText('--');
        expect(dashes.length).toBeGreaterThan(0);
      });
    });

    it('given all data loaded, when rendered, then #X/Y format never appears', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': BE_DATA,
        'liquidity/cohorts': COHORT_DATA,
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('BrickLink')).toBeInTheDocument();
      });
      expect(screen.queryByText(/#\d+\/\d+/)).not.toBeInTheDocument();
    });
  });

  describe('empty states', () => {
    it('given no data from either source, when rendered, then shows empty message', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': { success: false },
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="99999" />);
      await waitFor(() => {
        expect(screen.getByText('No sales data available from either source.')).toBeInTheDocument();
      });
    });

    it('given one source has data and other does not, when rendered, then shows "No data available" for missing source', async () => {
      fetchSpy = mockFetchResponses({
        'source=bricklink': BL_DATA,
        'source=brickeconomy': { success: false },
        'liquidity/cohorts': { success: false },
      });

      render(<LiquidityPanel setNumber="71043" />);
      await waitFor(() => {
        expect(screen.getByText('No data available.')).toBeInTheDocument();
      });
    });
  });
});
