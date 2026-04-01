import { apiClient } from "./api"

export async function refreshAssignedSimulations(): Promise<void> {
  try {
    await apiClient.apiRequest("/professor/cohorts/refresh-assignments", { method: "POST" })
  } catch (error) {
    // Non-fatal; page will still load
    console.error("Failed to refresh assignments:", error)
  }
}
