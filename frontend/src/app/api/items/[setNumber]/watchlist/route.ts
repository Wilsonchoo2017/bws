import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function PATCH(
  _request: NextRequest,
  { params }: { params: Promise<{ setNumber: string }> }
) {
  try {
    const { setNumber } = await params;
    if (!/^\d{3,6}(-\d+)?$/.test(setNumber)) {
      return NextResponse.json(
        { success: false, error: 'Invalid set number format' },
        { status: 400 }
      );
    }
    const res = await fetch(`${API_BASE}/api/items/${setNumber}/watchlist`, {
      method: 'PATCH',
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to toggle watchlist' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to toggle watchlist';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
