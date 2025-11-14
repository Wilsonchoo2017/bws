import { FreshContext } from "$fresh/server.ts";
import { and, desc, eq, gte, lt, lte, or, sql } from "drizzle-orm";
import { db } from "../../db/client.ts";
import { vouchers } from "../../db/schema.ts";

export const handler = async (
  req: Request,
  _ctx: FreshContext,
): Promise<Response> => {
  try {
    // GET - List all vouchers with filtering and pagination
    if (req.method === "GET") {
      const url = new URL(req.url);
      const page = parseInt(url.searchParams.get("page") || "1");
      const limit = parseInt(url.searchParams.get("limit") || "20");
      const status = url.searchParams.get("status"); // active, soon, expired, all
      const platform = url.searchParams.get("platform");
      const search = url.searchParams.get("search");
      const tagId = url.searchParams.get("tagId");

      const offset = (page - 1) * limit;
      const now = new Date();
      const sevenDaysFromNow = new Date(now.getTime() + 7 * 24 * 60 * 60 * 1000);

      // Build WHERE conditions
      const conditions = [];

      // Status filter
      if (status === "active") {
        // Active: isActive=true AND (startDate is null OR startDate <= now) AND (endDate is null OR endDate > now)
        conditions.push(
          and(
            eq(vouchers.isActive, true),
            or(
              sql`${vouchers.startDate} IS NULL`,
              lte(vouchers.startDate, now),
            ),
            or(
              sql`${vouchers.endDate} IS NULL`,
              gte(vouchers.endDate, now),
            ),
          ),
        );
      } else if (status === "soon") {
        // Soon: startDate > now AND startDate <= 7 days from now
        conditions.push(
          and(
            gte(vouchers.startDate, now),
            lte(vouchers.startDate, sevenDaysFromNow),
          ),
        );
      } else if (status === "expired") {
        // Expired: endDate < now OR isActive=false
        conditions.push(
          or(
            eq(vouchers.isActive, false),
            and(
              sql`${vouchers.endDate} IS NOT NULL`,
              lt(vouchers.endDate, now),
            ),
          ),
        );
      }

      // Platform filter
      if (platform && platform !== "all") {
        conditions.push(eq(vouchers.platform, platform));
      }

      // Search by name
      if (search) {
        conditions.push(sql`${vouchers.name} ILIKE ${"%" + search + "%"}`);
      }

      // Filter by tag
      if (tagId) {
        conditions.push(sql`${tagId} = ANY(${vouchers.requiredTagIds})`);
      }

      // Combine all conditions
      const whereClause = conditions.length > 0
        ? and(...conditions)
        : undefined;

      // Get total count
      const countResult = await db
        .select({ count: sql<number>`count(*)` })
        .from(vouchers)
        .where(whereClause);

      const totalCount = Number(countResult[0]?.count || 0);

      // Get paginated vouchers
      const vouchersList = await db
        .select()
        .from(vouchers)
        .where(whereClause)
        .orderBy(desc(vouchers.createdAt))
        .limit(limit)
        .offset(offset);

      // Add computed fields
      const vouchersWithStatus = vouchersList.map((voucher) => {
        const isExpired = voucher.endDate && new Date(voucher.endDate) < now;
        const isSoon = voucher.startDate &&
          new Date(voucher.startDate) > now &&
          new Date(voucher.startDate) <= sevenDaysFromNow;
        const isActive = voucher.isActive &&
          (!voucher.startDate || new Date(voucher.startDate) <= now) &&
          (!voucher.endDate || new Date(voucher.endDate) > now);

        return {
          ...voucher,
          status: isExpired || !voucher.isActive
            ? "expired"
            : isSoon
            ? "soon"
            : isActive
            ? "active"
            : "inactive",
        };
      });

      const totalPages = Math.ceil(totalCount / limit);

      return new Response(
        JSON.stringify({
          items: vouchersWithStatus,
          pagination: {
            page,
            limit,
            totalCount,
            totalPages,
            hasNextPage: page < totalPages,
            hasPrevPage: page > 1,
          },
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    // POST - Create new voucher
    if (req.method === "POST") {
      const body = await req.json();

      // Validate required fields
      if (!body.name || typeof body.name !== "string") {
        return new Response(
          JSON.stringify({ error: "Missing or invalid 'name' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      if (!body.voucherType || !["platform", "shop", "item_tag"].includes(body.voucherType)) {
        return new Response(
          JSON.stringify({ error: "Missing or invalid 'voucherType' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      if (!body.discountType || !["percentage", "fixed"].includes(body.discountType)) {
        return new Response(
          JSON.stringify({ error: "Missing or invalid 'discountType' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      if (body.discountValue === undefined || typeof body.discountValue !== "number") {
        return new Response(
          JSON.stringify({ error: "Missing or invalid 'discountValue' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      const [newVoucher] = await db
        .insert(vouchers)
        .values({
          name: body.name.trim(),
          description: body.description?.trim() || null,
          voucherType: body.voucherType,
          discountType: body.discountType,
          discountValue: body.discountValue,
          platform: body.platform || null,
          shopId: body.shopId || null,
          shopName: body.shopName?.trim() || null,
          minPurchase: body.minPurchase || null,
          maxDiscount: body.maxDiscount || null,
          requiredTagIds: body.requiredTagIds || null,
          tieredDiscounts: body.tieredDiscounts || null,
          isActive: body.isActive !== undefined ? body.isActive : true,
          startDate: body.startDate ? new Date(body.startDate) : null,
          endDate: body.endDate ? new Date(body.endDate) : null,
        })
        .returning();

      return new Response(JSON.stringify(newVoucher), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    }

    // PUT - Update existing voucher
    if (req.method === "PUT") {
      const body = await req.json();

      if (!body.id) {
        return new Response(
          JSON.stringify({ error: "Missing 'id' field" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      const updates: Record<string, unknown> = {
        updatedAt: new Date(),
      };

      if (body.name !== undefined) updates.name = body.name.trim();
      if (body.description !== undefined) {
        updates.description = body.description?.trim() || null;
      }
      if (body.voucherType !== undefined) updates.voucherType = body.voucherType;
      if (body.discountType !== undefined) updates.discountType = body.discountType;
      if (body.discountValue !== undefined) updates.discountValue = body.discountValue;
      if (body.platform !== undefined) updates.platform = body.platform;
      if (body.shopId !== undefined) updates.shopId = body.shopId;
      if (body.shopName !== undefined) updates.shopName = body.shopName?.trim() || null;
      if (body.minPurchase !== undefined) updates.minPurchase = body.minPurchase;
      if (body.maxDiscount !== undefined) updates.maxDiscount = body.maxDiscount;
      if (body.requiredTagIds !== undefined) updates.requiredTagIds = body.requiredTagIds;
      if (body.tieredDiscounts !== undefined) updates.tieredDiscounts = body.tieredDiscounts;
      if (body.isActive !== undefined) updates.isActive = body.isActive;
      if (body.startDate !== undefined) {
        updates.startDate = body.startDate ? new Date(body.startDate) : null;
      }
      if (body.endDate !== undefined) {
        updates.endDate = body.endDate ? new Date(body.endDate) : null;
      }

      const [updatedVoucher] = await db
        .update(vouchers)
        .set(updates)
        .where(eq(vouchers.id, body.id))
        .returning();

      if (!updatedVoucher) {
        return new Response(
          JSON.stringify({ error: "Voucher not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(JSON.stringify(updatedVoucher), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    // DELETE - Delete voucher
    if (req.method === "DELETE") {
      const url = new URL(req.url);
      const id = url.searchParams.get("id");

      if (!id) {
        return new Response(
          JSON.stringify({ error: "Missing 'id' query parameter" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      const [deletedVoucher] = await db
        .delete(vouchers)
        .where(eq(vouchers.id, id))
        .returning();

      if (!deletedVoucher) {
        return new Response(
          JSON.stringify({ error: "Voucher not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(
        JSON.stringify({ success: true, deletedVoucher }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      );
    }

    return new Response(
      JSON.stringify({ error: "Method not allowed" }),
      { status: 405, headers: { "Content-Type": "application/json" } },
    );
  } catch (error) {
    console.error("Error in vouchers API:", error);
    return new Response(
      JSON.stringify({
        error: "Internal server error",
        details: error instanceof Error ? error.message : String(error),
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    );
  }
};
