import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { download, request } from "@/api/client";
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

/**
 * Fetch the export and hand it to the browser to save.
 *
 * The bytes come through the authenticated client and are handed over as an object URL: a
 * plain link cannot carry the bearer token, which lives in memory rather than in a cookie.
 * The URL is revoked immediately — the download has already been queued by then, and
 * leaving it alive holds the whole archive in memory for as long as the tab is open.
 */
export function useExport() {
  return useMutation({
    mutationFn: async () => {
      const { blob, filename } = await download("/me/export");
      const url = URL.createObjectURL(blob);
      try {
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        link.click();
      } finally {
        URL.revokeObjectURL(url);
      }
      return filename;
    },
  });
}

/**
 * Delete the account. There is no undo and no confirmation dialog beyond the form itself.
 *
 * Takes no identifier: the endpoint acts on whoever the request is authenticated as, which
 * is the only account it can act on.
 */
export function useDeleteAccount() {
  return useMutation({
    mutationFn: (confirmation: { password: string; confirmation: string }) =>
      request("/me", { method: "DELETE", body: confirmation }),
  });
}

/**
 * Replace the password of the account already signed in.
 *
 * Not the reset flow. That one exists for somebody who cannot sign in and proves who they
 * are through their email; this proves it with the password being replaced, and touches no
 * email at all.
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: (passwords: {
      current_password: string;
      new_password: string;
    }) => request("/auth/password", { method: "POST", body: passwords }),
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
