import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ setNumber: string }> }
) {
  try {
    const { setNumber } = await params;
    const res = await fetch(
      `${API_BASE}/api/items/${setNumber}/minifigures/value-history`
    );

    if (!res.ok) {
      let detail = 'Failed to fetch value history';
      try {
        const body = await res.json();
        detail = body.detail || detail;
      } catch {
        // non-JSON error body
      }
      return NextResponse.json(
        { success: false, error: detail },
        { status: res.status }
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch value history';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
