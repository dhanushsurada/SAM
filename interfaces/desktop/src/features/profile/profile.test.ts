import { test } from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_FOUNDER_PROFILE, GUEST_PROFILE } from "./types.ts";

test("founder profile defaults to Dhanush Surada as sovereign operator", () => {
  assert.equal(DEFAULT_FOUNDER_PROFILE.name, "Dhanush Surada");
  assert.equal(DEFAULT_FOUNDER_PROFILE.handle, "@dhanush");
  assert.equal(DEFAULT_FOUNDER_PROFILE.role, "Sovereign Operator");
  assert.equal(DEFAULT_FOUNDER_PROFILE.isSignedIn, true);
  assert.equal(DEFAULT_FOUNDER_PROFILE.authMethod, "founder");
  assert.equal(DEFAULT_FOUNDER_PROFILE.incognitoMode, false);
  assert.ok(DEFAULT_FOUNDER_PROFILE.nodeId.includes("sam-node"));
  assert.ok(DEFAULT_FOUNDER_PROFILE.deviceKeyFingerprint.startsWith("ed25519:"));
});

test("guest profile is ephemeral and signed out by default", () => {
  assert.equal(GUEST_PROFILE.name, "Guest Operator");
  assert.equal(GUEST_PROFILE.handle, "@guest");
  assert.equal(GUEST_PROFILE.isSignedIn, false);
  assert.equal(GUEST_PROFILE.authMethod, "guest");
  assert.equal(GUEST_PROFILE.incognitoMode, true);
});
