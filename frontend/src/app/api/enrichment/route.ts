import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const payload: { set_number: string; source?: string } = {
      set_number: body.set_number,
    };
    if (body.source) {
      payload.source = body.source;
    }

    const res = await fetch(`${API_BASE}/api/enrichment/enrich`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
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
