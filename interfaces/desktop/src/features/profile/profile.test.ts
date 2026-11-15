import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_FOUNDER_PROFILE,
  GUEST_PROFILE,
  FOUNDER_CONNECTED_PLATFORMS,
  FOUNDER_PERSONA_ANALYSIS,
} from "./types.ts";

test("founder profile defaults to Dhanush Surada as sovereign operator", () => {
  assert.equal(DEFAULT_FOUNDER_PROFILE.name, "Dhanush Surada");
  assert.equal(DEFAULT_FOUNDER_PROFILE.handle, "@dhanush");
  assert.equal(DEFAULT_FOUNDER_PROFILE.role, "Sovereign Operator");
  assert.equal(DEFAULT_FOUNDER_PROFILE.isSignedIn, true);
  assert.equal(DEFAULT_FOUNDER_PROFILE.authMethod, "founder");
  assert.equal(DEFAULT_FOUNDER_PROFILE.incognitoMode, false);
  assert.equal(DEFAULT_FOUNDER_PROFILE.isEmailVerified, true);
  assert.equal(DEFAULT_FOUNDER_PROFILE.isPhoneVerified, true);
  assert.equal(DEFAULT_FOUNDER_PROFILE.email, "dhanush@sam.local");
  assert.equal(DEFAULT_FOUNDER_PROFILE.phone, "+91 98765 43210");
  assert.ok(DEFAULT_FOUNDER_PROFILE.nodeId.includes("sam-node"));
  assert.ok(DEFAULT_FOUNDER_PROFILE.deviceKeyFingerprint.startsWith("ed25519:"));
});

test("guest profile is ephemeral and signed out by default", () => {
  assert.equal(GUEST_PROFILE.name, "Guest Operator");
  assert.equal(GUEST_PROFILE.handle, "@guest");
  assert.equal(GUEST_PROFILE.isSignedIn, false);
  assert.equal(GUEST_PROFILE.authMethod, "guest");
  assert.equal(GUEST_PROFILE.incognitoMode, true);
  assert.equal(GUEST_PROFILE.isEmailVerified, false);
  assert.equal(GUEST_PROFILE.isPhoneVerified, false);
  assert.equal(GUEST_PROFILE.connectedPlatforms.length, 0);
  assert.equal(GUEST_PROFILE.personaAnalysis, undefined);
});

test("founder has connected ecosystem platforms configured", () => {
  const platformIds = FOUNDER_CONNECTED_PLATFORMS.map((p) => p.id);
  assert.ok(platformIds.includes("telegram"), "telegram is connected");
  assert.ok(platformIds.includes("instagram"), "instagram is connected");
  assert.ok(platformIds.includes("whatsapp"), "whatsapp is connected");
  assert.ok(platformIds.includes("traceop"), "traceop profiler is connected");
  assert.ok(platformIds.includes("github"), "github is connected");
  assert.ok(platformIds.includes("twitter"), "twitter is connected");
  assert.ok(platformIds.includes("linkedin"), "linkedin is connected");

  const telegram = FOUNDER_CONNECTED_PLATFORMS.find((p) => p.id === "telegram");
  assert.equal(telegram?.connected, true);
  assert.equal(telegram?.syncMessages, true);
  assert.equal(telegram?.syncContext, true);

  const instagram = FOUNDER_CONNECTED_PLATFORMS.find((p) => p.id === "instagram");
  assert.equal(instagram?.connected, true);
  assert.equal(instagram?.syncContext, true);
});

test("TraceOp persona analysis contains structured intelligence metrics", () => {
  assert.ok(FOUNDER_PERSONA_ANALYSIS.overallScore >= 90);
  assert.ok(FOUNDER_PERSONA_ANALYSIS.executiveSummary.length > 20);
  assert.ok(FOUNDER_PERSONA_ANALYSIS.communicationStyle.length > 10);
  assert.ok(FOUNDER_PERSONA_ANALYSIS.keyInterests.length >= 4);
  assert.ok(FOUNDER_PERSONA_ANALYSIS.cognitivePreferences.length >= 3);
  assert.ok(FOUNDER_PERSONA_ANALYSIS.crossPlatformFootprint.length >= 3);
});
