# SAM Remote Connectivity & Secure Relay Validation Report

**Document ID:** `VAL-PHASE8-RELAY-001`  
**Date:** 2026-11-10  
**Transport:** Outbound Secure WebSocket (WSS / TLS 1.3) via Self-Hosted or Managed Relay  
**Verification Scope:** NAT Traversal, Zero Port Forwarding, E2E Message Signing & Reconnection  
**Status:** `PASS` (Desktop Client & Android Relay Protocol Verified)

---

## 1. Remote Connectivity Architecture & Problem Statement

### The Problem
When the user is away from home or the mobile device is operating on cellular data (5G / LTE), direct LAN HTTP connections are blocked by Carrier-Grade NAT (CGNAT) and home firewalls. Exposing the Desktop SAM HTTP port directly to the public internet via port forwarding creates severe security risks (DoS, port scanning, unauthenticated exposure).

### The Solution: Outbound-Only Secure Relay
SAM resolves this by implementing an **outbound-only bidirectional relay model**:

```
+-----------------------------------------------------------------------------------+
|                                  PUBLIC INTERNET                                  |
|                                                                                   |
|                           +-----------------------------+                         |
|                           |       SAM SECURE RELAY      |                         |
|                           | (wss://relay.example.com)   |                         |
|                           |                             |                         |
|                           |  Blind Message Router:      |                         |
|                           |  Inspects sender/target ID, |                         |
|                           |  forwards encrypted payload |                         |
|                           +-----------------------------+                         |
|                                     ^                 ^                           |
|       Outbound TLS 1.3 / WSS        |                 |  Outbound TLS 1.3 / WSS   |
|       (Zero open inbound ports)     |                 |  (Cellular / Foreign WiFi)|
+-------------------------------------+-----------------+---------------------------+
                                      |                 |
                   +------------------+                 +------------------+
                   |                                                       |
        +--------------------+                                   +--------------------+
        |    Desktop SAM     |                                   |    Android SAM     |
        | (Home / Office LAN)|                                   | (Cellular / Remote)|
        |                    |                                   |                    |
        | Signs with DeskKey |                                   | Signs with MobKey  |
        +--------------------+                                   +--------------------+
```

### Key Security Guarantees:
1. **Zero Open Ports on Desktop:** No router firewall rules, no UPnP, no exposed public IP endpoints.
2. **Untrusted Relay Model:** The relay server acts purely as a message switchboard. Every relay frame is signed with the originating device's private Ed25519 key (`canonical_bytes`). The receiving device independently verifies the signature against the paired device's stored public key. An adversarial relay operator cannot forge or alter commands without failing verification.
3. **Outbound Keepalive:** Desktop and mobile maintain persistent WebSocket connections with 30-second ping/pong frames, keeping NAT state tables open across firewalls.

---

## 2. Relay Message Protocol (Version 1.0)

Every relay frame is structured as a typed `RelayMessage`:

```json
{
  "protocol_version": "1.0",
  "message_id": "msg_9f81a7b3c2d4",
  "sender_device_id": "sam-desktop-mac-01",
  "target_device_id": "sam-android-iqoo-01",
  "message_type": "task_event",
  "timestamp": 1731238491,
  "payload": {
    "task_id": "task_20261110_4192",
    "action": "app_launch",
    "required_capability": "app_launch",
    "action_payload": { "app": "WhatsApp" }
  },
  "signature": "MC4CAQ...[Base64 Ed25519 Signature]..."
}
```

### Signature Verification Algorithm:
```python
canonical_bytes = f"{version}:{sender_id}:{target_id}:{msg_type}:{timestamp}:{sorted_json(payload)}".encode("utf-8")
is_valid = crypto.verify_signature(target_public_key, canonical_bytes, signature_bytes)
```

---

## 3. Resilience, Failover & NAT Traversal Analysis

### Connection State Machine:
```
           +------------------+
           |   DISCONNECTED   |
           +------------------+
                     |
            (Initiate Connect)
                     v
           +------------------+       Auth Failed
           |   CONNECTING     | -----------------------> [ FATAL ERROR ]
           +------------------+                         (Requires Re-pair)
                     |
            (Ed25519 Handshake)
                     v
           +------------------+       Ping Timeout
           |    CONNECTED     | -----------------------> [ BACKOFF RETRY ]
           +------------------+                         (1s, 2s, 4s... 30s)
```

1. **Cellular-to-Wi-Fi Handoff:** Android `ACCESS_NETWORK_STATE` receiver detects interface switches and triggers instant re-handshake without restarting active task leases.
2. **Relay Outage Fallback:** If the relay is unreachable, SAM falls back to local LAN discovery if available, or queues tasks locally until remote connectivity resumes.

---

## 4. Verification Test Matrix

| Test Suite / Case | Target Module | Result | Details |
| :--- | :--- | :--- | :--- |
| `test_tiered_execution_and_coordinator_offline.py::test_remote_relay_message_signing_and_verification` | `connect/bridges/remote_relay.py` | **PASS** | Validates Ed25519 frame signing |
| `test_tiered_execution_and_coordinator_offline.py::test_remote_relay_tampered_payload_rejected` | `connect/bridges/remote_relay.py` | **PASS** | Rejects modified JSON payload |
| `tests/test_iqoo_phase2_offline.py` | Relay Client & Offline State | **PASS** | Reconnection backoff logic |
