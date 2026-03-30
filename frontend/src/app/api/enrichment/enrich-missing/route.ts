import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function POST(request: NextRequest) {
  try {
    const res = await fetch(
      `${API_BASE}/api/enrichment/enrich-missing`,
      { method: 'POST' }
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to enrich missing' },
        { status: res.status }
      );
    }

    return NextResponse.json({ success: true, data });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to start enrichment';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
