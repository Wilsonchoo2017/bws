import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function PUT(
  request: NextRequest,
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

    const body = await request.json();
    const res = await fetch(`${API_BASE}/api/items/${setNumber}/buy-rating`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to update buy rating' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to update buy rating';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
