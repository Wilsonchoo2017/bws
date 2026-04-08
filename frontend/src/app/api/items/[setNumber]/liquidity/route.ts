import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

type RouteContext = { params: Promise<Record<string, string>> };

export async function GET(request: NextRequest, context: RouteContext) {
  try {
    const { setNumber } = await context.params;
    const search = request.nextUrl.searchParams.toString();
    const qs = search ? `?${search}` : '';
    const res = await fetch(`${API_BASE}/api/items/${setNumber}/liquidity${qs}`);
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: (data.detail as string) || 'Failed to fetch liquidity data' },
        { status: res.status },
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to fetch liquidity data';
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
