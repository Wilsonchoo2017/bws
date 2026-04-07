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

    const { searchParams } = new URL(request.url);
    const queryParts: string[] = [];

    const price = searchParams.get('price');
    if (price) queryParts.push(`price=${encodeURIComponent(price)}`);

    const discount = searchParams.get('discount');
    if (discount) queryParts.push(`discount=${encodeURIComponent(discount)}`);

    const queryStr = queryParts.length > 0 ? `?${queryParts.join('&')}` : '';

    const res = await fetch(
      `${API_BASE}/api/ml/buy-signal/${setNumber}${queryStr}`
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to fetch buy signal' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch buy signal';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
