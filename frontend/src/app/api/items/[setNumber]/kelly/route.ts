import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.BWS_API_URL || 'http://localhost:8005';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ setNumber: string }> }
) {
  try {
    const { setNumber } = await params;

    if (!/^[\w-]+$/.test(setNumber)) {
      return NextResponse.json(
        { success: false, error: 'Invalid set number' },
        { status: 400 }
      );
    }

    const { searchParams } = new URL(request.url);
    let queryStr = '';
    const budgetRaw = searchParams.get('budget');
    if (budgetRaw) {
      const budgetNum = parseInt(budgetRaw, 10);
      if (isNaN(budgetNum) || budgetNum < 0 || budgetNum > 100_000_000) {
        return NextResponse.json(
          { success: false, error: 'Invalid budget parameter' },
          { status: 400 }
        );
      }
      queryStr = `?budget=${budgetNum}`;
    }

    const res = await fetch(
      `${API_BASE}/api/items/${setNumber}/kelly${queryStr}`
    );
    const data = await res.json();

    if (!res.ok) {
      return NextResponse.json(
        { success: false, error: data.detail || 'Failed to fetch Kelly sizing' },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch Kelly sizing';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
