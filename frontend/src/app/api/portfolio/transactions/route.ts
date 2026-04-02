import { type NextRequest, NextResponse } from 'next/server';
import { API_BASE, proxyPost } from '@/lib/api-proxy';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const params = new URLSearchParams();
    const setNumber = searchParams.get('set_number');
    const limit = searchParams.get('limit');
    const offset = searchParams.get('offset');
    if (setNumber) params.set('set_number', setNumber);
    if (limit) params.set('limit', limit);
    if (offset) params.set('offset', offset);

    const url = `${API_BASE}/api/portfolio/transactions?${params.toString()}`;
    const res = await fetch(url);
    const data = await res.json();
    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch transactions';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}

export const POST = proxyPost('/api/portfolio/transactions', {
  errorMessage: 'Failed to create transaction',
  forwardBody: true,
});
