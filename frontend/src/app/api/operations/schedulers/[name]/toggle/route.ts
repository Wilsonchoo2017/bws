import { NextRequest, NextResponse } from 'next/server';
import { API_BASE } from '@/lib/api-proxy';

interface Context {
  readonly params: Promise<{ readonly name: string }>;
}

export async function POST(request: NextRequest, context: Context) {
  try {
    const { name } = await context.params;
    const qs = new URL(request.url).searchParams.toString();
    const suffix = qs ? `?${qs}` : '';
    const res = await fetch(
      `${API_BASE}/api/operations/schedulers/${encodeURIComponent(name)}/toggle${suffix}`,
      { method: 'POST' }
    );
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        {
          success: false,
          error: data.detail ?? 'Failed to toggle scheduler',
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
