import { Handlers } from "$fresh/server.ts";
import { eq } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import { products } from "../../../db/schema.ts";

interface UpdateProductRequest {
  name?: string;
  brand?: string;
  legoSetNumber?: string;
  currency?: string;
  price?: number;
  priceMin?: number;
  priceMax?: number;
  priceBeforeDiscount?: number;
  image?: string;
  watchStatus?: "active" | "paused" | "stopped" | "archived";
}

export const handler: Handlers = {
  async PATCH(req, ctx) {
    try {
      const productId = ctx.params.id;

      if (!productId) {
        return new Response(
          JSON.stringify({ error: "Product ID is required" }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      // Parse request body
      const body: UpdateProductRequest = await req.json();

      // Validate legoSetNumber length if provided
      if (body.legoSetNumber && body.legoSetNumber.length > 10) {
        return new Response(
          JSON.stringify({
            error: "LEGO Set Number must be 10 characters or less",
          }),
          { status: 400, headers: { "Content-Type": "application/json" } },
        );
      }

      // Build update object with only provided fields
      const updateData: Partial<typeof products.$inferInsert> = {
        updatedAt: new Date(),
      };

      if (body.name !== undefined) updateData.name = body.name || null;
      if (body.brand !== undefined) updateData.brand = body.brand || null;
      if (body.legoSetNumber !== undefined) {
        updateData.legoSetNumber = body.legoSetNumber || null;
      }
      if (body.currency !== undefined) {
        updateData.currency = body.currency || null;
      }
      if (body.price !== undefined) updateData.price = body.price || null;
      if (body.priceMin !== undefined) {
        updateData.priceMin = body.priceMin || null;
      }
      if (body.priceMax !== undefined) {
        updateData.priceMax = body.priceMax || null;
      }
      if (body.priceBeforeDiscount !== undefined) {
        updateData.priceBeforeDiscount = body.priceBeforeDiscount || null;
      }
      if (body.image !== undefined) updateData.image = body.image || null;
      if (body.watchStatus !== undefined) {
        updateData.watchStatus = body.watchStatus;
      }

      // Update the product - using productId (not serial id)
      const updatedProducts = await db
        .update(products)
        .set(updateData)
        .where(eq(products.productId, productId))
        .returning();

      if (updatedProducts.length === 0) {
        return new Response(
          JSON.stringify({ error: "Product not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      return new Response(
        JSON.stringify({ success: true, product: updatedProducts[0] }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    } catch (error) {
      console.error("Error updating product:", error);
      return new Response(
        JSON.stringify({
          error: "Failed to update product",
          details: error.message,
        }),
        { status: 500, headers: { "Content-Type": "application/json" } },
      );
    }
  },
};
