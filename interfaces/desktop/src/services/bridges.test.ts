import { test } from "node:test";
import assert from "node:assert/strict";
import { bridgesService } from "./bridges.ts";

test("bridgesService exposes complete omnichannel and fabric methods", () => {
  assert.equal(typeof bridgesService.getStatus, "function");
  assert.equal(typeof bridgesService.startBridge, "function");
  assert.equal(typeof bridgesService.stopBridge, "function");
  assert.equal(typeof bridgesService.pairChannel, "function");
  assert.equal(typeof bridgesService.broadcast, "function");
  assert.equal(typeof bridgesService.getTopology, "function");
  assert.equal(typeof bridgesService.getClipboard, "function");
  assert.equal(typeof bridgesService.setClipboard, "function");
  assert.equal(typeof bridgesService.getIOSShortcutConfig, "function");
});

test("bridgesService getIOSShortcutConfig builds correct query parameters", async () => {
  const originalFetch = globalThis.fetch;
  try {
    let capturedUrl = "";
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      capturedUrl = input.toString();
      return {
        ok: true,
        json: async () => ({
          name: "Ask SAM",
          endpoint: "http://192.168.1.100:8420/api/ios/shortcut",
          instructions: [],
        }),
      } as any;
    }) as any;

    const res = await bridgesService.getIOSShortcutConfig("http://192.168.1.100:8420");
    assert.equal(res.name, "Ask SAM");
    assert.ok(capturedUrl.includes("base_url=http%3A%2F%2F192.168.1.100%3A8420"));
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("bridgesService setClipboard sends JSON payload with source device ID", async () => {
  const originalFetch = globalThis.fetch;
  try {
    let capturedBody = "";
    globalThis.fetch = (async (_input: RequestInfo | URL, init?: RequestInit) => {
      capturedBody = init?.body as string;
      return {
        ok: true,
        json: async () => ({ synced: true, length: 14 }),
      } as any;
    }) as any;

    const res = await bridgesService.setClipboard("test clipboard", "desktop");
    assert.equal(res.synced, true);
    assert.ok(capturedBody.includes('"content":"test clipboard"'));
    assert.ok(capturedBody.includes('"source_device_id":"desktop"'));
  } finally {
    globalThis.fetch = originalFetch;
  }
});
