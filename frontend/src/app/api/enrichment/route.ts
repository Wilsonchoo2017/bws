import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/api/enrichment/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Enrichment failed' },
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
