import { NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function POST() {
  try {
    const res = await fetch(`${API_BASE}/api/images/download`, {
      method: 'POST',
    });
    const data = await res.json();
    return NextResponse.json({ success: true, data });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to connect to API';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
