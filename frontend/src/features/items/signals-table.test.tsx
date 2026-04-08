import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CohortSection } from './signals-table';
import type { CohortRank } from './types';

describe('CohortSection', () => {
  const baseCohort: CohortRank = {
    key: '2025-H1',
    size: 184,
    rank: 23,
    composite_score_pct: 88,
    demand_pressure_pct: 86,
    theme_growth_pct: 87,
  };

  it('given cohort rank #23/184, when rendered, then displays P88 percentile (higher = better)', () => {
    render(
      <CohortSection cohorts={{ half_year: baseCohort }} />
    );
    // rank badge P88 + inline composite P88 = 2 matches
    const matches = screen.getAllByText('P88');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('given cohort rank #23/184, when rendered, then shows peer group size n=184', () => {
    render(
      <CohortSection cohorts={{ half_year: baseCohort }} />
    );
    expect(screen.getByText('n=184')).toBeInTheDocument();
  });

  it('given cohort rank #23/184, when rendered, then does NOT display raw rank format #23/184', () => {
    render(
      <CohortSection cohorts={{ half_year: baseCohort }} />
    );
    expect(screen.queryByText('#23/184')).not.toBeInTheDocument();
  });

  it('given cohort with demand_pressure_pct 86, when rendered, then shows P86 with P prefix', () => {
    render(
      <CohortSection cohorts={{ half_year: baseCohort }} />
    );
    expect(screen.getByText('P86')).toBeInTheDocument();
  });

  it('given source label BrickLink, when rendered, then shows source label', () => {
    render(
      <CohortSection cohorts={{ half_year: baseCohort }} sourceLabel="BrickLink" />
    );
    expect(screen.getByText('BrickLink')).toBeInTheDocument();
  });

  it('given cohort section, when rendered, then shows "higher = better" label', () => {
    render(
      <CohortSection cohorts={{ half_year: baseCohort }} />
    );
    expect(screen.getByText('percentile vs peer group (higher = better)')).toBeInTheDocument();
  });

  it('given empty cohorts, when rendered, then returns null', () => {
    const { container } = render(
      <CohortSection cohorts={{}} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('given unknown cohort strategy, when rendered, then filters it out', () => {
    const { container } = render(
      <CohortSection cohorts={{ unknown_strategy: baseCohort }} />
    );
    expect(container.firstChild).toBeNull();
  });

  it('given cohort with null rank, when rendered, then does not show rank percentile badge or n= label', () => {
    const noRank: CohortRank = { ...baseCohort, rank: null };
    render(
      <CohortSection cohorts={{ half_year: noRank }} />
    );
    // No n= label means no rank badge rendered
    expect(screen.queryByText(/^n=/)).not.toBeInTheDocument();
  });

  it('given multiple cohort strategies, when rendered, then shows all strategy labels', () => {
    const cohorts = {
      half_year: { ...baseCohort, key: '2025-H1' },
      year: { ...baseCohort, key: '2025', size: 229, rank: 30, composite_score_pct: 87 },
    };
    render(<CohortSection cohorts={cohorts} />);
    expect(screen.getByText('Half-Year')).toBeInTheDocument();
    expect(screen.getByText('Year')).toBeInTheDocument();
  });

  it('given rank #1/200 (best), when rendered, then shows P100 with emerald color class', () => {
    const best: CohortRank = { key: 'test', rank: 1, size: 200, composite_score_pct: 99 };
    render(<CohortSection cohorts={{ half_year: best }} />);
    const badge = screen.getByText('P100');
    expect(badge).toBeInTheDocument();
    expect(badge.closest('span')).toHaveClass('text-emerald-400');
  });

  it('given rank #200/200 (worst), when rendered, then shows P0 with red color class', () => {
    const worst: CohortRank = { key: 'test', rank: 200, size: 200, composite_score_pct: 2 };
    render(<CohortSection cohorts={{ half_year: worst }} />);
    const badge = screen.getByText('P0');
    expect(badge).toBeInTheDocument();
    expect(badge.closest('span')).toHaveClass('text-red-500');
  });
});
