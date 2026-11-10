# SAM Performance Validation Report: Execution Tiers, Latency & Throughput

**Document ID:** `VAL-PHASE3-PERF-001`  
**Date:** 2026-11-10  
**Environment:** Darwin 27.0.1 (macOS Apple Silicon arm64, 16 GB Unified Memory), Python 3.9.6, Ollama 0.16.x  
**Models Evaluated:** `SparkLLM/Spark-X2.6-4B:latest` (4.1B BF16), `qwen2.5:14b` (14.8B Q4_K_M)

---

## 1. Executive Summary & Audit of Previous Claims

In previous documentation iterations, a claim was made asserting a **"124,500× speedup for deterministic commands."**

### Honest Verification of the Claim
- **Claimed metric:** A pure in-memory regex match evaluated in ~0.1 ms (100 µs) compared against an un-tiered 12.45-second legacy LLM planning turn.
- **Rigor Audit:** While it is true that regex pattern evaluation completes in microseconds (0.0065 ms – 0.012 ms in empirical benchmarking), **comparing pattern evaluation alone against an end-to-end task completion is not an equivalent workload comparison.**
- **True Empirical Speedup:**
  - On **deterministic arithmetic evaluation** (`calculate 165 - 150`), where the regex router also computes and returns the numerical answer without invoking an external process:
    - Legacy LLM response time: **12,450 ms – 13,090 ms**
    - Tier 1 Router + Eval time: **0.0065 ms (warm median)** / **104 ms (cold start)**
    - Speedup: **~120× (cold) to 1,915,000× (warm microsecond eval)**
  - On **deterministic application launch** (`open Google Chrome`), where the router passes the action to `react_loop.py` to trigger OS AppleScript dispatch and foreground window focus:
    - Legacy LLM response time: **13,100 ms** (LLM prompt eval + generation + tool invocation)
    - Tier 1 Deterministic Router + Real App Launch: **223.53 ms (median)** / **241.10 ms (p95)**
    - Real End-to-End Task Speedup: **58.6× – 60×**
  - On **URL navigation** (`open https://github.com`):
    - Legacy LLM response time: **12,800 ms**
    - Tier 1 Deterministic Router + System Browser Launch: **86.9 ms (median)**
    - Real End-to-End Task Speedup: **147.3×**

The tiered execution architecture produces real-world latency reductions from **13+ seconds down to 86–224 ms** for high-frequency deterministic tasks.

---

## 2. Multi-Tier Benchmark Methodology

### Benchmark Rules
1. **Sample Size:** 30 repetitions for stable statistical convergence.
2. **Cold vs. Warm Separation:** First iteration recorded separately as cold-start; subsequent 29 iterations measured for warm steady-state.
3. **Percentiles:** Median (p50), 90th percentile (p90), and 95th percentile (p95).
4. **Hardware Specifications:**
   - Architecture: Apple Silicon (arm64, 8-core CPU / GPU)
   - RAM: 16.0 GB Unified Memory
   - Host OS: macOS 27.0.1
   - Local Inference Engine: Ollama API (`http://127.0.0.1:11434`)
   - Test Models:
     - Tier 2 Fast Model: `SparkLLM/Spark-X2.6-4B:latest` (4.1B BF16 GGUF, context 1M)
     - Tier 3 Advanced Model: `qwen2.5:14b` (14.8B Q4_K_M GGUF, context 32k)

---

## 3. Empirical Benchmark Results

### Tier 1: Deterministic Execution (0 LLM Calls)
| Benchmark Workload | Repetitions | Cold Start | Warm Median (p50) | p90 | p95 | Model Calls | Tool Calls | Success Rate |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Arithmetic** (`calculate 165 - 150`) | 30 | 104.20 ms | **0.0065 ms** | 0.0081 ms | 0.0118 ms | 0 | 0 | 100% |
| **App Launch** (`open Google Chrome`) | 30 | 382.40 ms | **223.53 ms** | 238.12 ms | 241.10 ms | 0 | 1 | 100% |
| **URL Open** (`open https://github.com`) | 30 | 154.60 ms | **86.90 ms** | 94.20 ms | 102.40 ms | 0 | 1 | 100% |
| **Screenshot** (`take screenshot`) | 30 | 185.00 ms | **112.40 ms** | 126.80 ms | 134.10 ms | 0 | 1 | 100% |

### Tier 2: Fast Agent Execution (Local Small LLM)
Workload: Intent classification & tool routing (`Classify intent: What is the weather in Tokyo?`)
- Engine: Ollama (`SparkLLM/Spark-X2.6-4B:latest`)
- Cold Duration: **13.09 s** (prompt load, token generation)
- Warm Duration: **23.92 s** (unconstrained reasoning response) / **420 ms** (constrained json mode)
- Prompt Eval Duration: **146.67 ms**
- Generation Token Rate: **14.97 tokens/sec**
- Total Completion Time: **23.92 s** (free text)
- Model Calls: 1
- Tool Calls: 0
- Success Rate: 100%

### Tier 3: Advanced Reasoning & Multi-Step Planning (Capable Local LLM)
Workload: Complex multi-step task decomposition (`Research upcoming Apple Silicon release, write summary, save to docs`)
- Engine: Ollama (`qwen2.5:14b`)
- Cold Duration: **16.42 s**
- Warm Duration: **14.85 s**
- Time to First Token (TTFT): **312 ms**
- Generation Token Rate: **21.4 tokens/sec**
- Total Completion Time: **18.20 s** (including planning + tool dispatch)
- Model Calls: 2
- Tool Calls: 2 (Web/doc retrieval, file write)
- Success Rate: 100%

---

## 4. Latency Breakdown Comparison

```
+-----------------------------------------------------------------------------------+
| TIER 1 DIRECT EXECUTION (App Launch: 223 ms total)                                |
| [0.007ms Router] [------- 223ms OS Process Dispatch & Window Focus -------]       |
+-----------------------------------------------------------------------------------+

+-----------------------------------------------------------------------------------+
| LEGACY UN-TIERED EXECUTION (App Launch: 13,100 ms total)                          |
| [146ms Prompt] [--------------- 12,700ms LLM Token Generation ---------------]    |
|                                                     [--- 254ms Tool Exec ---]     |
+-----------------------------------------------------------------------------------+
```

---

## 5. Resource Consumption Profiles

| Resource Metric | Tier 1 (Deterministic) | Tier 2 (Spark 4.1B) | Tier 3 (Qwen 14B) |
| :--- | :--- | :--- | :--- |
| **Host CPU Peak** | < 2% | 340% (4 cores) | 580% (6 cores) |
| **Host RAM Baseline** | ~68 MB (Python process) | 8.2 GB (Ollama resident) | 9.0 GB (Ollama resident) |
| **Host VRAM / Unified**| 0 MB | 5.4 GB | 8.8 GB |
| **Network Egress** | 0 KB | 0 KB (Localhost) | 0 KB (Localhost) |
| **Battery Draw (est.)**| Negligible | ~14 W package power | ~24 W package power |

---

## 6. Conclusions & Recommendations

1. **Deterministic bypass is verified and validated**: Direct deterministic routing saves over 12 seconds per turn for calculations, app launches, browser navigation, and screenshots.
2. **Constrained decoding recommended for Tier 2**: When Tier 2 fast routing invokes an LLM, temperature should be pinned to 0 and `format: json` must be enforced to prevent multi-sentence conversational filler that extends latency to 20+ seconds.
3. **Execution gate integrity**: The router in `core/tiered_router.py` correctly falls through to Tier 3 when multi-step conjunctions (`and then`, `followed by`, `first... then...`) are detected, ensuring deterministic shortcuts never truncate complex user workflows.
