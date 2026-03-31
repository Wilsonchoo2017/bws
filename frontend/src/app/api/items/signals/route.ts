import { NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/items/signals`);
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to fetch signals' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch signals';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
