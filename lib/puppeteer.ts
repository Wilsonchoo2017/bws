/**
 * Puppeteer wrapper for Deno compatibility
 *
 * This file fixes the "Warning: Not implemented: ClientRequest.options.createConnection"
 * warning by replacing Puppeteer's NodeWebSocketTransport with Deno's native WebSocket.
 *
 * Issue: https://github.com/puppeteer/puppeteer/issues/11839
 * Workaround: Monkey-patch NodeWebSocketTransport to use native Deno WebSocket
 */

import { NodeWebSocketTransport } from "npm:puppeteer-core@23.11.1/lib/esm/puppeteer/node/NodeWebSocketTransport.js";
import puppeteer from "npm:puppeteer@23.11.1";

// Monkey-patch NodeWebSocketTransport to use Deno's native WebSocket
// This eliminates the warning and prevents async ops leaks
NodeWebSocketTransport.create = function create(url: string) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url, []);
    ws.addEventListener("open", () => {
      return resolve(new NodeWebSocketTransport(ws as any));
    });
    ws.addEventListener("error", reject);
  });
};

export default puppeteer;
export * from "npm:puppeteer@23.11.1";
