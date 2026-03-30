import { NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET() {
  try {
    const res = await fetch(`${API_BASE}/api/portfolio/holdings`);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch holdings';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
