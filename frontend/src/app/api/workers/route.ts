import { NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/scrape/jobs`);
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to fetch jobs' },
        { status: res.status }
      );
    }

    // Backend returns { jobs, stats } -- pass through both
    return NextResponse.json({
      success: true,
      data: data.jobs ?? data,
      stats: data.stats ?? null,
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to connect to API';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}

export async function DELETE() {
  try {
    const res = await fetch(`${API_BASE}/api/scrape/jobs`, {
      method: 'DELETE',
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to clear jobs' },
        { status: res.status }
      );
    }

    return NextResponse.json({ success: true, data });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to connect to API';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
