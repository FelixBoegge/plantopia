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

/**
 * One plant, with its observations, diagnoses and current plan.
 *
 * Disabled without an identifier rather than asked for with an empty one. The wizard is
 * reachable both with a plant and without, and a missing id would otherwise fetch
 * `/plants/` — a wasted request that 404s, on every visit to the general form.
 */
export function usePlant(plantId: string | null | undefined) {
  return useQuery({
    queryKey: keys.plant(plantId ?? "none"),
    queryFn: () => request<PlantDetail>(`/plants/${plantId}`),
    enabled: Boolean(plantId),
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

export function useRemovePlant(plantId: string) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: () => request(`/plants/${plantId}`, { method: "DELETE" }),
    // **Exact, and not awaited.** `keys.plants` is a prefix of `keys.plant(id)`, so a
    // prefix invalidation also refetches the plant just deleted -- which 404s, and a 404
    // is permanent, so it renders "This plant could not be loaded" instead of retrying.
    // Returning the promise made it worse: an onSuccess that returns one is awaited, so
    // the error rendered before the caller's navigate ran. `removeQueries` on the detail
    // key is not the fix either -- the observer is still mounted, so it would refetch.
    onSuccess: () => {
      void queries.invalidateQueries({ queryKey: keys.plants, exact: true });
    },
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
