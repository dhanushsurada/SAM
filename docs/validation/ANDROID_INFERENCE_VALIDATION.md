# SAM Android On-Device AI Inference Validation Report

**Document ID:** `VAL-PHASE5-MOBILE-AI-001`  
**Date:** 2026-11-10  
**Target Runtimes:** Google LiteRT (formerly TFLite) / llama.cpp Android / MediaPipe LLM Inference  
**Physical Benchmark Status:** `BLOCKED` on host (Requires physical device with Snapdragon/Dimensity/Tensor NPU).

---

## 1. On-Device Inference Architecture

SAM implements an adaptive dual-engine AI architecture:
1. **Desktop Host (High Capacity):** Hosts 4B–14B+ models via Ollama (`SparkLLM/Spark-X2.6-4B`, `qwen2.5:14b`) with unified memory and GPU/Metal acceleration.
2. **Mobile Device (Low Latency / Offline):** Employs `SamMobileInferenceEngine.kt` to run compact 1B–3B parameter models locally on the mobile SoC.

### Dynamic Hardware Tiering Matrix
The Android engine inspects `ActivityManager.MemoryInfo` at runtime to select the appropriate model profile:

```
                  +------------------------------------------+
                  |  SamMobileInferenceEngine.hardwareTier  |
                  +------------------------------------------+
                                       |
           +---------------------------+---------------------------+
           |                                                       |
     Total RAM < 6 GB                                       Total RAM >= 6 GB
           |                                                       |
  [ MobileHardwareTier.LOW ]                             [ MobileHardwareTier.MEDIUM / HIGH ]
  Target: 1B - 2B Models                                 Target: 3B - 4B Models
  - SmolLM2 1.7B (Q4_K_M)                                - Qwen 2.5 3B (Q4_K_M)
  - Gemma 2 2B (LiteRT)                                  - Phi-3.5 Mini 3.8B (LiteRT)
  - RAM Budget: <= 1.5 GB                                - RAM Budget: <= 3.2 GB
```

---

## 2. Targeted Mobile Models & Theoretical Envelopes

| Model Identifier | Parameters | Quantization | Format | Memory Footprint | Expected Speed (Snapdragon 8 Gen 3) | Target Use Case |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **SmolLM2-1.7B-Instruct** | 1.71 B | Q4_K_M | GGUF | ~1.15 GB | 32–45 tokens/sec | Fast intent classification & tool args |
| **Gemma-2-2B-IT** | 2.61 B | 4-bit AWQ | LiteRT / TFLite | ~1.65 GB | 24–36 tokens/sec | Conversational mobile responses |
| **Qwen2.5-3B-Instruct** | 3.09 B | Q4_K_M | GGUF | ~2.10 GB | 18–28 tokens/sec | Offline multi-step Android planning |
| **Desktop Offload Fallback** | 14.8 B | Q4_K_M | Ollama API | 0 GB (Phone RAM) | Network bounded (< 150 ms RTT) | Complex cross-device workflows |

---

## 3. Battery, Thermal & Offload Routing Logic

Mobile inference creates substantial thermal and battery impact if unmanaged. SAM employs capability-aware routing heuristics:

```
                              User Task Arrives
                                      |
                           Is Desktop Reachable?
                               /             \
                             YES              NO
                             /                 \
                 Check Phone State           Run Mobile Local Model
               [Battery, Temperature]                  |
                 /                \             (Best-effort offline)
         Battery < 20%       Battery >= 20%
        or Temp > 40°C      and Temp <= 40°C
               |                    |
        Offload to Desktop    Evaluate Task Complexity
        (Preserve Battery)          |
                             Tier 1/2: Run on Mobile
                             Tier 3:   Offload to Desktop
```

### Policy Rules:
1. **Battery Preservation Gate:** If phone battery is below 20% and not charging, all LLM inference offloads to Desktop over LAN/Relay; phone only executes deterministic UI commands.
2. **Thermal Throttle Gate:** If thermal throttling exceeds `THERMAL_STATUS_SEVERE`, local inference is paused.
3. **Bandwidth Optimization:** When connected over local 5GHz Wi-Fi, offloading to desktop achieves 14B model quality at lower total energy cost than running a 3B model locally.

---

## 4. Physical Benchmark Execution Instructions

To benchmark inference performance on a physical device (e.g. iQOO 12 with Snapdragon 8 Gen 3):

```bash
# 1. Push model weights to device
adb push ./models/smollm2-1.7b-instruct-q4_k_m.gguf /sdcard/Android/data/com.samcore.android/files/models/

# 2. Run inference benchmark test harness
adb shell am start-activity -n com.samcore.android/.ui.diagnostics.BenchmarkActivity \
  --es model "smollm2-1.7b-instruct-q4_k_m.gguf" \
  --ei iterations 30 \
  --es prompt "Summarize the unread notifications and draft a quick reply."

# 3. Pull diagnostic CSV
adb pull /sdcard/Android/data/com.samcore.android/files/benchmark_results.csv ./
```

---

## 5. Verification Status Summary

| Component | Code Reference | Static Verification | Physical Benchmark |
| :--- | :--- | :--- | :--- |
| **RAM Profiler** | `SamMobileInferenceEngine.kt:52` | **PASS** (ActivityManager query) | `BLOCKED` (Host missing ADB) |
| **Model Loader** | `SamMobileInferenceEngine.kt:87` | **PASS** (GGUF/LiteRT format check) | `BLOCKED` (Host missing device) |
| **Streaming Flow** | `SamMobileInferenceEngine.kt:121` | **PASS** (Coroutines flow/delay) | `BLOCKED` (Host missing device) |
| **Desktop Offload Router** | `connect/services/coordinator.py:68` | **PASS** (Tested in pytest suite) | **PASS** (Host verified) |
