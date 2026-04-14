import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function GET(request: NextRequest) {
  try {
    const url = new URL(request.url);
    const qs = url.searchParams.toString();
    const suffix = qs ? `?${qs}` : '';
    const res = await fetch(
      `${API_BASE}/api/scrape/shopee/captcha-events${suffix}`
    );
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        {
          success: false,
          error: data.detail ?? 'Failed to load captcha events',
        },
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
