import { type NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function POST(request: NextRequest) {
  try {
    let body: string | undefined;
    const contentType = request.headers.get('content-type');
    if (contentType?.includes('application/json')) {
      body = JSON.stringify(await request.json());
    }

    const res = await fetch(`${API_BASE}/api/enrichment/scrape-missing-minifigs`, {
      method: 'POST',
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body,
    });
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to scrape missing minifigs' },
        { status: res.status }
      );
    }

    return NextResponse.json({ success: true, data });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to scrape missing minifigs';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
