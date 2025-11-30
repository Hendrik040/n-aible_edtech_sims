import { apiClient } from "./api"

export async function refreshAssignedSimulations(): Promise<void> {
  try {
    await apiClient.apiRequest("/professor/cohorts/refresh-assignments", { method: "POST" })
  } catch {
    // Non-fatal; page will still load
  }
}


