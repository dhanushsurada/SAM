import * as client from "@/api/client";
import type {
  TaskCreateRequest,
  TaskRecord,
  HealthStatus,
  DemoResetResult,
  ExecutionEvent,
} from "@/api/types";

/**
 * The interface, not just the real implementation, is what matters here —
 * this is the seam a demo implementation would sit behind for any domain
 * that doesn't have a real backend yet (see PHASE5_PLAN.md §B/§F). iQOO
 * only needs the real side because iQOO is the one domain that's actually
 * live today.
 */
export interface IqooService {
  createTask(req: TaskCreateRequest): Promise<TaskRecord>;
  getTask(taskId: string): Promise<TaskRecord>;
  cancelTask(taskId: string): Promise<TaskRecord>;
  retryTask(taskId: string): Promise<TaskRecord>;
  getHealth(): Promise<HealthStatus>;
  demoReset(): Promise<DemoResetResult>;
  subscribeToTaskEvents(taskId: string, onEvent: (e: ExecutionEvent) => void, onError?: (e: Event) => void): () => void;
}

export const iqooService: IqooService = {
  createTask: client.createTask,
  getTask: client.getTask,
  cancelTask: client.cancelTask,
  retryTask: client.retryTask,
  getHealth: client.getHealth,
  demoReset: client.demoReset,
  subscribeToTaskEvents: client.subscribeToTaskEvents,
};
