import { Handlers } from "$fresh/server.ts";
import { eq } from "drizzle-orm";
import { db } from "../../../db/client.ts";
import {
  brickrankerRetirementItems,
  products,
  worldbricksSets,
} from "../../../db/schema.ts";

interface UpdateProductRequest {
  name?: string;
  legoSetNumber?: string;
  price?: number;
  priceBeforeDiscount?: number;
  watchStatus?: "active" | "paused" | "stopped" | "archived";
  yearReleased?: number | null;
  yearRetired?: number | null;
  expectedRetirementDate?: string | null;
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
      if (body.legoSetNumber !== undefined) {
        updateData.legoSetNumber = body.legoSetNumber || null;
      }
      if (body.price !== undefined) updateData.price = body.price || null;
      if (body.priceBeforeDiscount !== undefined) {
        updateData.priceBeforeDiscount = body.priceBeforeDiscount || null;
      }
      if (body.watchStatus !== undefined) {
        updateData.watchStatus = body.watchStatus;
      }

      // Get current product to check for LEGO set number
      const currentProduct = await db.query.products.findFirst({
        where: eq(products.productId, productId),
      });

      if (!currentProduct) {
        return new Response(
          JSON.stringify({ error: "Product not found" }),
          { status: 404, headers: { "Content-Type": "application/json" } },
        );
      }

      // Update the product - using productId (not serial id)
      const updatedProducts = await db
        .update(products)
        .set(updateData)
        .where(eq(products.productId, productId))
        .returning();

      // Update retirement information if LEGO set number exists
      const legoSetNumber = body.legoSetNumber || currentProduct.legoSetNumber;

      if (legoSetNumber) {
        // Update WorldBricks data if yearReleased or yearRetired provided
        if (
          body.yearReleased !== undefined || body.yearRetired !== undefined
        ) {
          const worldbricksUpdateData: Partial<
            typeof worldbricksSets.$inferInsert
          > = {
            updatedAt: new Date(),
          };

          if (body.yearReleased !== undefined) {
            worldbricksUpdateData.yearReleased = body.yearReleased;
          }
          if (body.yearRetired !== undefined) {
            worldbricksUpdateData.yearRetired = body.yearRetired;
          }

          // Try to update existing WorldBricks record
          await db
            .update(worldbricksSets)
            .set(worldbricksUpdateData)
            .where(eq(worldbricksSets.setNumber, legoSetNumber));
        }

        // Update BrickRanker data if expectedRetirementDate provided
        if (
          body.expectedRetirementDate !== undefined ||
          body.yearReleased !== undefined
        ) {
          const brickrankerUpdateData: Partial<
            typeof brickrankerRetirementItems.$inferInsert
          > = {
            updatedAt: new Date(),
          };

          if (body.yearReleased !== undefined) {
            brickrankerUpdateData.yearReleased = body.yearReleased;
          }
          if (body.expectedRetirementDate !== undefined) {
            brickrankerUpdateData.expectedRetirementDate =
              body.expectedRetirementDate;
          }

          // Try to update existing BrickRanker record
          await db
            .update(brickrankerRetirementItems)
            .set(brickrankerUpdateData)
            .where(eq(brickrankerRetirementItems.setNumber, legoSetNumber));
        }
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
