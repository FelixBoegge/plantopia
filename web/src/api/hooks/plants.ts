import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/api/client";
import { keys } from "@/app/queries";
import type { PlantDetail, PlantSummary, StepStatus } from "@/api/types";

/** Every plant this person owns, newest first. */
export function usePlants() {
  return useQuery({
    queryKey: keys.plants,
    queryFn: () => request<PlantSummary[]>("/plants"),
  });
}

/** One plant, with its observations, diagnoses and current plan. */
export function usePlant(plantId: string) {
  return useQuery({
    queryKey: keys.plant(plantId),
    queryFn: () => request<PlantDetail>(`/plants/${plantId}`),
  });
}

export function useRenamePlant(plantId: string) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      request(`/plants/${plantId}`, { method: "PATCH", body: { name } }),
    // Both, because a rename shows on the plant and in the grid, and a screen that reflected
    // only one of them would be right in one place and stale in the other.
    onSuccess: () => {
      void queries.invalidateQueries({ queryKey: keys.plant(plantId) });
      void queries.invalidateQueries({ queryKey: keys.plants });
    },
  });
}

export function useRemovePlant() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (plantId: string) =>
      request(`/plants/${plantId}`, { method: "DELETE" }),
    onSuccess: () => queries.invalidateQueries({ queryKey: keys.plants }),
  });
}

export function useMarkStep(plantId: string) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ stepId, status }: { stepId: string; status: StepStatus }) =>
      request(`/roadmap-steps/${stepId}`, {
        method: "PATCH",
        body: { status },
      }),
    onSuccess: () =>
      queries.invalidateQueries({ queryKey: keys.plant(plantId) }),
  });
}
