import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/api/client";
import { keys } from "@/app/queries";
import type { Account, Evaluation, ProfileFact } from "@/api/types";

export function useAccount() {
  return useQuery({
    queryKey: keys.account,
    queryFn: () => request<Account>("/me"),
  });
}

export function useFacts() {
  return useQuery({
    queryKey: keys.facts,
    queryFn: () => request<ProfileFact[]>("/profile/facts"),
  });
}

export function useForgetFact() {
  const queries = useQueryClient();
  return useMutation({
    // The fact itself is the identity. There is no separate id, which is a little unusual
    // and is why this takes text rather than a key.
    mutationFn: (fact: string) =>
      request("/profile/facts/forget", { method: "POST", body: { fact } }),
    onSuccess: () => queries.invalidateQueries({ queryKey: keys.facts }),
  });
}

export function useEvaluation() {
  return useQuery({
    queryKey: keys.evaluation,
    queryFn: () => request<Evaluation>("/evaluation/latest"),
    // A harness result changes when somebody runs the harness by hand, which is not often.
    staleTime: 5 * 60_000,
  });
}

/** How much of the allowance is left, and whether a run would be refused. */
export function allowance(account: Account | undefined) {
  if (!account) return null;
  const remaining = Math.max(0, account.runs_allowed - account.runs_used);
  return {
    remaining,
    used: account.runs_used,
    limit: account.runs_allowed,
    exhausted: remaining === 0,
    resetsAt: new Date(account.allowance_resets_at),
  };
}
