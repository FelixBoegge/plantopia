import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/api/client";
import { keys } from "@/app/queries";
import type { DiagnosisDetail, Run, SpeciesCandidate } from "@/api/types";

/** One run, for what it finally produced and for resuming after a reload. */
export function useRun(runId: string | null) {
  return useQuery({
    queryKey: keys.run(runId ?? "none"),
    queryFn: () => request<Run>(`/runs/${runId}`),
    enabled: runId !== null,
  });
}

export function useDiagnosis(diagnosisId: string | null) {
  return useQuery({
    queryKey: keys.diagnosis(diagnosisId ?? "none"),
    queryFn: () => request<DiagnosisDetail>(`/diagnoses/${diagnosisId}`),
    enabled: diagnosisId !== null,
  });
}

export interface StartRun {
  photographs: File[];
  /** What the owner calls it. Absent for a fresh diagnosis; the run names it. */
  plantName?: string;
  locationKind: "indoor" | "outdoor";
  /** What the owner says the plant is, if they know. Never required. */
  statedSpecies?: string;
  locationText?: string;
  notes?: string;
  plantId?: string;
}

export function useStartRun() {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (start: StartRun) => {
      const form = new FormData();
      if (start.plantName) form.append("plant_name", start.plantName);
      form.append("location_kind", start.locationKind);
      if (start.statedSpecies) form.append("stated_species", start.statedSpecies);
      if (start.locationText) form.append("location_text", start.locationText);
      if (start.notes) form.append("user_notes", start.notes);
      if (start.plantId) form.append("plant_id", start.plantId);
      for (const photograph of start.photographs)
        form.append("photographs", photograph);
      return request<Run>("/runs", { method: "POST", body: form });
    },
    // The allowance shown elsewhere has just changed, and so has the list of runs.
    onSuccess: () => {
      void queries.invalidateQueries({ queryKey: keys.account });
      void queries.invalidateQueries({ queryKey: keys.runs });
    },
  });
}

/** What a paused run is resumed with: its answers, and the species chosen if it asked. */
export interface Resume {
  answers: Record<string, string>;
  species?: SpeciesCandidate | null;
}

export function useAnswerRun(runId: string) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: ({ answers, species }: Resume) =>
      request<Run>(`/runs/${runId}/answers`, {
        method: "POST",
        // The candidate is sent back whole rather than as an index into the list it came
        // from. An index would mean the client and the run must agree on an ordering only
        // one of them controls.
        body: { answers, species: species ?? null },
      }),
    onSuccess: () => queries.invalidateQueries({ queryKey: keys.run(runId) }),
  });
}

export function useCancelRun(runId: string) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: () => request(`/runs/${runId}`, { method: "DELETE" }),
    onSuccess: () => queries.invalidateQueries({ queryKey: keys.run(runId) }),
  });
}
