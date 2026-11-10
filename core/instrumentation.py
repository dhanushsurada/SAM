"""
Performance Instrumentation and Telemetry for SAM

Captures end-to-end performance metrics:
- Input processing latency
- Time to first token (TTFT)
- Model inference duration
- Tool routing time
- Tool execution time
- Device communication latency
- Memory retrieval time
- Total task completion time
- Retry count and failure rate
"""

import time
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger("SAM.Instrumentation")


@dataclass
class TurnMetrics:
    task_id: str
    user_input: str
    tier: str = "unknown"
    target_device: str = "desktop"
    
    # Latencies in milliseconds
    input_processing_ms: float = 0.0
    memory_retrieval_ms: float = 0.0
    time_to_first_token_ms: float = 0.0
    model_inference_ms: float = 0.0
    tool_routing_ms: float = 0.0
    tool_execution_ms: float = 0.0
    device_comm_ms: float = 0.0
    total_latency_ms: float = 0.0
    
    # Execution counts
    model_call_count: int = 0
    tool_call_count: int = 0
    retry_count: int = 0
    success: bool = True
    error: Optional[str] = None
    
    # Breakdown of tool timings: [{"action": str, "elapsed_ms": float, "success": bool}]
    tool_breakdown: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PerformanceProfiler:
    """Singleton/thread-safe profiler for tracking SAM task lifecycle."""
    
    def __init__(self, log_path: Optional[Path] = None):
        self.log_path = log_path
        self._history: List[TurnMetrics] = []

    def start_turn(self, task_id: str, user_input: str) -> 'TurnContext':
        return TurnContext(self, task_id=task_id, user_input=user_input)

    def record(self, metrics: TurnMetrics):
        self._history.append(metrics)
        logger.info(
            f"[PERF] Task {metrics.task_id} ({metrics.tier}): Total {metrics.total_latency_ms:.1f}ms | "
            f"TTFT: {metrics.time_to_first_token_ms:.1f}ms | LLM: {metrics.model_inference_ms:.1f}ms | "
            f"Tools: {metrics.tool_execution_ms:.1f}ms | Calls: {metrics.model_call_count} | Retries: {metrics.retry_count}"
        )
        if self.log_path:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.log_path, "a") as f:
                    f.write(json.dumps(metrics.to_dict()) + "\n")
            except Exception as e:
                logger.debug(f"Failed to write perf log: {e}")

    def get_summary(self) -> Dict[str, Any]:
        if not self._history:
            return {"total_tasks": 0}
        total = len(self._history)
        successful = sum(1 for m in self._history if m.success)
        avg_total_ms = sum(m.total_latency_ms for m in self._history) / total
        avg_ttft_ms = sum(m.time_to_first_token_ms for m in self._history) / total
        avg_llm_ms = sum(m.model_inference_ms for m in self._history) / total
        total_retries = sum(m.retry_count for m in self._history)
        
        tier_counts = {}
        for m in self._history:
            tier_counts[m.tier] = tier_counts.get(m.tier, 0) + 1

        return {
            "total_tasks": total,
            "success_rate": successful / total,
            "avg_total_latency_ms": round(avg_total_ms, 2),
            "avg_time_to_first_token_ms": round(avg_ttft_ms, 2),
            "avg_model_inference_ms": round(avg_llm_ms, 2),
            "total_retries": total_retries,
            "tier_distribution": tier_counts
        }


class TurnContext:
    """Context manager and stopwatch for an active user turn."""

    def __init__(self, profiler: PerformanceProfiler, task_id: str, user_input: str):
        self.profiler = profiler
        self.metrics = TurnMetrics(task_id=task_id, user_input=user_input)
        self._start_time = time.time()
        self._checkpoints: Dict[str, float] = {}

    def mark(self, name: str):
        self._checkpoints[name] = time.time()

    def elapsed_since(self, name: str) -> float:
        if name not in self._checkpoints:
            return 0.0
        return (time.time() - self._checkpoints[name]) * 1000.0

    def record_memory_retrieval(self, elapsed_ms: float):
        self.metrics.memory_retrieval_ms += elapsed_ms

    def record_tool_routing(self, elapsed_ms: float):
        self.metrics.tool_routing_ms += elapsed_ms

    def record_first_token(self):
        if self.metrics.time_to_first_token_ms == 0.0:
            self.metrics.time_to_first_token_ms = (time.time() - self._start_time) * 1000.0

    def record_model_inference(self, elapsed_ms: float):
        self.metrics.model_inference_ms += elapsed_ms
        self.metrics.model_call_count += 1

    def record_tool_call(self, action: str, elapsed_ms: float, success: bool, retry: bool = False):
        self.metrics.tool_execution_ms += elapsed_ms
        self.metrics.tool_call_count += 1
        if retry:
            self.metrics.retry_count += 1
        self.metrics.tool_breakdown.append({
            "action": action,
            "elapsed_ms": round(elapsed_ms, 2),
            "success": success,
            "retry": retry
        })

    def record_device_comm(self, elapsed_ms: float):
        self.metrics.device_comm_ms += elapsed_ms

    def finish(self, success: bool = True, error: Optional[str] = None) -> TurnMetrics:
        self.metrics.total_latency_ms = (time.time() - self._start_time) * 1000.0
        self.metrics.success = success
        self.metrics.error = error
        if self.metrics.time_to_first_token_ms == 0.0 and self.metrics.total_latency_ms > 0:
            self.metrics.time_to_first_token_ms = self.metrics.total_latency_ms
        self.profiler.record(self.metrics)
        return self.metrics


# Global default profiler instance
default_profiler = PerformanceProfiler()
