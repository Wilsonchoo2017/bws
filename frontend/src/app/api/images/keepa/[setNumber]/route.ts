import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ setNumber: string }> }
) {
  try {
    const { setNumber } = await params;
    const res = await fetch(`${API_BASE}/api/images/keepa/${setNumber}`);

    if (!res.ok) {
      return NextResponse.json(
        { error: 'Keepa chart not found' },
        { status: 404 }
      );
    }

    const buffer = await res.arrayBuffer();
    return new NextResponse(buffer, {
      headers: {
        'Content-Type': 'image/png',
        'Cache-Control': 'public, max-age=3600',
      },
    });
  } catch {
    return NextResponse.json(
      { error: 'Failed to fetch Keepa chart' },
      { status: 500 }
    );
  }
}
