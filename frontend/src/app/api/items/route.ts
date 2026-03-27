import { query } from '@/lib/db';
import type { ItemWithAnalysis } from '@/features/items/types';
import { NextResponse } from 'next/server';

export async function GET() {
  try {
    const items = await query<ItemWithAnalysis>(`
      SELECT
        bi.item_id,
        bi.item_type,
        bi.title,
        bi.year_released,
        bi.image_url,
        bi.watch_status,
        bi.last_scraped_at,
        bi.created_at,
        pa.overall_score,
        pa.confidence,
        pa.action,
        pa.urgency
      FROM bricklink_items bi
      LEFT JOIN product_analysis pa ON bi.item_id = pa.item_id
      ORDER BY bi.created_at DESC
    `);

    return NextResponse.json({ success: true, data: items });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'Failed to fetch items';
    return NextResponse.json(
      { success: false, error: message },
      { status: 500 }
    );
  }
}
