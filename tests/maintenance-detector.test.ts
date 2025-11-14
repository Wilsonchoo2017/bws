import { assertEquals, assertThrows } from "https://deno.land/std@0.208.0/assert/mod.ts";
import { BricklinkMaintenanceDetector } from "../services/bricklink/BricklinkMaintenanceDetector.ts";
import { MaintenanceError } from "../types/errors/MaintenanceError.ts";
import { MAINTENANCE_CONFIG } from "../config/scraper.config.ts";

Deno.test("BricklinkMaintenanceDetector - detects maintenance page", () => {
  const html = `
    <html>
      <body>
        <font size="+3">System Unavailable</font>
        <p>Daily maintenance is running. The site will be available in 1 minute.</p>
      </body>
    </html>
  `;

  const isMaintenancePage = BricklinkMaintenanceDetector.isMaintenancePage(html);
  assertEquals(isMaintenancePage, true);
});

Deno.test("BricklinkMaintenanceDetector - does not detect regular page", () => {
  const html = `
    <html>
      <body>
        <h1>Welcome to Bricklink</h1>
        <p>Browse our catalog</p>
      </body>
    </html>
  `;

  const isMaintenancePage = BricklinkMaintenanceDetector.isMaintenancePage(html);
  assertEquals(isMaintenancePage, false);
});

Deno.test("BricklinkMaintenanceDetector - parses maintenance duration (1 minute)", () => {
  const html = `Daily maintenance is running. The site will be available in 1 minute.`;

  const durationMs = BricklinkMaintenanceDetector.parseMaintenanceDuration(html);

  // 1 minute = 60000ms
  // With safety: 60000 * 1.5 + 60000 = 150000ms
  const expected = 60000 * MAINTENANCE_CONFIG.SAFETY_MULTIPLIER +
                   MAINTENANCE_CONFIG.SAFETY_BUFFER_MS;

  assertEquals(durationMs, expected);
});

Deno.test("BricklinkMaintenanceDetector - parses maintenance duration (5 minutes)", () => {
  const html = `Daily maintenance is running. The site will be available in 5 minutes.`;

  const durationMs = BricklinkMaintenanceDetector.parseMaintenanceDuration(html);

  // 5 minutes = 300000ms
  // With safety: 300000 * 1.5 + 60000 = 510000ms
  const expected = 300000 * MAINTENANCE_CONFIG.SAFETY_MULTIPLIER +
                   MAINTENANCE_CONFIG.SAFETY_BUFFER_MS;

  assertEquals(durationMs, expected);
});

Deno.test("BricklinkMaintenanceDetector - uses default delay when cannot parse", () => {
  const html = `Daily maintenance is running.`;

  const durationMs = BricklinkMaintenanceDetector.parseMaintenanceDuration(html);

  assertEquals(durationMs, MAINTENANCE_CONFIG.DEFAULT_DELAY_MS);
});

Deno.test("BricklinkMaintenanceDetector - throws MaintenanceError when maintenance detected", () => {
  const html = `
    <html>
      <body>
        <font size="+3">System Unavailable</font>
        <p>Daily maintenance is running. The site will be available in 2 minutes.</p>
      </body>
    </html>
  `;

  assertThrows(
    () => {
      BricklinkMaintenanceDetector.checkAndThrow(html);
    },
    MaintenanceError,
    "Bricklink is currently under maintenance",
  );
});

Deno.test("BricklinkMaintenanceDetector - does not throw for regular page", () => {
  const html = `
    <html>
      <body>
        <h1>Welcome to Bricklink</h1>
      </body>
    </html>
  `;

  // Should not throw
  BricklinkMaintenanceDetector.checkAndThrow(html);
});

Deno.test("MaintenanceError - has correct properties", () => {
  const error = new MaintenanceError("Test maintenance", 120000);

  assertEquals(error.name, "MaintenanceError");
  assertEquals(error.message, "Test maintenance");
  assertEquals(error.estimatedDurationMs, 120000);
  assertEquals(error.isMaintenanceError, true);

  // Check estimated end time is roughly correct (within 1 second)
  const expectedEndTime = new Date(Date.now() + 120000);
  const actualEndTime = error.getEstimatedEndTime();
  const diff = Math.abs(actualEndTime.getTime() - expectedEndTime.getTime());
  assertEquals(diff < 1000, true, "End time should be within 1 second");
});

Deno.test("MaintenanceError - type guard works correctly", () => {
  const maintenanceError = new MaintenanceError("Test", 60000);
  const regularError = new Error("Regular error");

  assertEquals(MaintenanceError.isMaintenanceError(maintenanceError), true);
  assertEquals(MaintenanceError.isMaintenanceError(regularError), false);
  assertEquals(MaintenanceError.isMaintenanceError(null), false);
  assertEquals(MaintenanceError.isMaintenanceError(undefined), false);
  assertEquals(MaintenanceError.isMaintenanceError("string"), false);
});
