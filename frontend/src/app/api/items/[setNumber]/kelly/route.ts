import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ setNumber: string }> }
) {
  try {
    const { setNumber } = await params;

    if (!/^[\w-]+$/.test(setNumber)) {
      return NextResponse.json(
        { success: false, error: 'Invalid set number' },
        { status: 400 }
      );
    }

    const res = await fetch(
      `${API_BASE}/api/items/${setNumber}/kelly`
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to fetch capital allocation' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch capital allocation';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
