import { type NextRequest, NextResponse } from 'next/server';
import { API_BASE, proxyGet } from '@/lib/api-proxy';

export const GET = proxyGet('/api/items');

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const res = await fetch(`${API_BASE}/api/items`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ set_number: body.set_number }),
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to add item' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to add item';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
