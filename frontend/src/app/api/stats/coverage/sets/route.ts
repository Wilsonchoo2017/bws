import { NextRequest, NextResponse } from 'next/server';

import { API_BASE } from '@/lib/api-proxy';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const qs = searchParams.toString();
    const url = `${API_BASE}/api/stats/coverage/sets${qs ? `?${qs}` : ''}`;
    const res = await fetch(url);
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail ?? 'Failed to fetch set coverage' },
        { status: res.status },
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Network error';
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
