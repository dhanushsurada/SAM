import * as client from "@/api/client";
import type { BrainStatus } from "@/api/types";

/**
 * The seam between the UI and the Brain endpoints, same shape as
 * services/iqoo.ts. Both calls are real (interfaces/api/server.py,
 * GET /api/models and POST /api/models/select) — there is no demo
 * implementation behind this interface.
 */
export interface BrainService {
  getBrainStatus(): Promise<BrainStatus>;
  selectModel(model: string): Promise<BrainStatus>;
}

export const brainService: BrainService = {
  getBrainStatus: client.getBrainStatus,
  selectModel: client.selectModel,
};
