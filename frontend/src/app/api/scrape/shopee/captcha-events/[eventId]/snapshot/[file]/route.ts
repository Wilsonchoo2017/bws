import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

type RouteContext = {
  params: Promise<{ eventId: string; file: string }>;
};

const ALLOWED = new Set(['meta.json', 'page.html', 'screenshot.png']);

export async function GET(_request: NextRequest, context: RouteContext) {
  const { eventId, file } = await context.params;
  if (!ALLOWED.has(file)) {
    return NextResponse.json(
      { success: false, error: 'Invalid snapshot file' },
      { status: 400 }
    );
  }
  try {
    const res = await fetch(
      `${API_BASE}/api/scrape/shopee/captcha-events/${encodeURIComponent(eventId)}/snapshot/${encodeURIComponent(file)}`
    );
    if (!res.ok) {
      const text = await res.text();
      return NextResponse.json(
        { success: false, error: text || 'Snapshot fetch failed' },
        { status: res.status }
      );
    }
    const contentType =
      res.headers.get('content-type') ?? 'application/octet-stream';
    const body = await res.arrayBuffer();
    return new NextResponse(body, {
      status: 200,
      headers: { 'content-type': contentType },
    });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch snapshot';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
