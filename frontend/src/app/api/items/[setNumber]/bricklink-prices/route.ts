import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ setNumber: string }> }
) {
  try {
    const { setNumber } = await params;
    const res = await fetch(
      `${API_BASE}/api/items/${setNumber}/bricklink-prices`
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to fetch prices' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch BrickLink prices';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
