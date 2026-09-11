import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/api/client";
import { keys } from "@/app/queries";
import type { Step } from "@/api/hooks/useRunStream";
import type { DiagnosisDetail, Run, SpeciesCandidate } from "@/api/types";

/** One run, for what it finally produced and for resuming after a reload. */
export function useRun(runId: string | null) {
  return useQuery({
    queryKey: keys.run(runId ?? "none"),
    queryFn: () => request<Run>(`/runs/${runId}`),
    enabled: runId !== null,
  });
}

/**
 * This owner's runs, most recent first — for finding one still going.
 *
 * Every link that opens the wizard fresh ("Diagnose a plant" in the header, the same on
 * the plants grid) points at a bare route with no run id, because none of them know
 * whether one is already in flight. This is how the wizard finds out for itself, rather
 * than every one of those links having to.
 *
 * **`staleTime: 0`, against the app's own 30-second default.** That default is a
 * reasonable trade for most of what this app reads — a plant's name is not going to
 * change in the next thirty seconds — but the entire question this query answers is
 * "is anything active *right now*", and a thirty-second-old answer to that is wrong by
 * definition, not merely stale: a run that finished twenty seconds ago still reads as
 * active for the rest of that window, and clicking back in through it resumes a
 * diagnosis that has already ended instead of opening a fresh one.
 */
export function useRuns({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: keys.runs,
    queryFn: () => request<Run[]>("/runs"),
    enabled,
    staleTime: 0,
  });
}

export function useDiagnosis(diagnosisId: string | null) {
  return useQuery({
    queryKey: keys.diagnosis(diagnosisId ?? "none"),
    queryFn: () => request<DiagnosisDetail>(`/diagnoses/${diagnosisId}`),
    enabled: diagnosisId !== null,
  });
}

/**
 * What the run that produced a diagnosis did.
 *
 * Its own request rather than part of the diagnosis: this is a panel somebody opens, and
 * folding it into `DiagnosisDetail` would make every screen showing a result carry it.
 */
export function useActivity(diagnosisId: string | null) {
  return useQuery({
    queryKey: keys.diagnosisActivity(diagnosisId ?? "none"),
    queryFn: () =>
      request<ActivityStep[]>(`/diagnoses/${diagnosisId}/activity`),
    enabled: diagnosisId !== null,
    select: asSteps,
  });
}

/** What the endpoint sends. `step` where the client says `id`, as the event payload does. */
interface ActivityStep extends Omit<Step, "id"> {
  step: string;
  occurred_at: string;
}

/**
 * The recorded steps, as the live stream would have shown them.
 *
 * Two jobs, both about the record agreeing with what somebody watched. It renames `step` to
 * `id`, which is what the stream calls it. And it collapses consecutive repeats the way the
 * stream does: several nodes deliberately share one sentence — `guard_input` and
 * `quality_check` are both "Checking the photographs" — so without this the same run reads
 * as one length while it happens and a longer one afterwards.
 */
function asSteps(recorded: ActivityStep[]): Step[] {
  const shown: Step[] = [];
  for (const { step, occurred_at: _at, ...rest } of recorded) {
    if (shown.at(-1)?.id === step) continue;
    shown.push({ ...rest, id: step });
  }
  return shown;
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
      if (start.statedSpecies)
        form.append("stated_species", start.statedSpecies);
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
