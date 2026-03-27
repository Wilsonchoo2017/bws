import { NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8000';

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/items/shopee`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch shopee items';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
