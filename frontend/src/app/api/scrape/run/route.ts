import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { scraperId, url } = body;

    const res = await fetch(`${API_BASE}/api/scrape/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scraper_id: scraperId, url }),
    });

    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to start scrape' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to connect to API';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
