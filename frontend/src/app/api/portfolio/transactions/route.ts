import { type NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const params = new URLSearchParams();
    const setNumber = searchParams.get('set_number');
    const limit = searchParams.get('limit');
    const offset = searchParams.get('offset');
    if (setNumber) params.set('set_number', setNumber);
    if (limit) params.set('limit', limit);
    if (offset) params.set('offset', offset);

    const url = `${API_BASE}/api/portfolio/transactions?${params.toString()}`;
    const res = await fetch(url);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch transactions';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/api/portfolio/transactions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to create transaction' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to create transaction';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
