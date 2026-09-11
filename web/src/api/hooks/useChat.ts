import { useCallback, useState } from "react";
import { flushSync } from "react-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "@/api/client";
import { readEvents } from "@/api/events";
import { currentToken } from "@/api/session";
import { keys } from "@/app/queries";
import type { Message } from "@/api/types";

export interface Progress {
  /** Sources consulted so far, in the words the server used. */
  sources: string[];
  /** The reply as it arrives, when the provider streams it. */
  text: string;
}

const NOTHING: Progress = { sources: [], text: "" };

/** The transcript for one plant. */
export function useTranscript(plantId: string) {
  return useQuery({
    queryKey: keys.messages(plantId),
    queryFn: () => request<Message[]>(`/plants/${plantId}/messages`),
  });
}

/**
 * Send a message and watch the agent answer.
 *
 * The streaming endpoint rather than the plain one, because a message that consults the
 * corpus and then the web is several seconds of silence otherwise — and silence reads as a
 * failure.
 *
 * The transcript is refetched at the end rather than assembled from the events. The server
 * writes it either way, and reconstructing it here would be a second implementation of what
 * a conversation is, kept in step by hand.
 */
export function useSendMessage(plantId: string) {
  const queries = useQueryClient();
  const [progress, setProgress] = useState<Progress>(NOTHING);
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);

  const send = useCallback(
    async (content: string) => {
      setProgress(NOTHING);
      setFailure(null);
      setSending(true);

      try {
        const response = await fetch(
          `/api/v1/plants/${plantId}/messages/stream`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${currentToken() ?? ""}`,
            },
            body: JSON.stringify({ content }),
          },
        );

        if (!response.ok || !response.body) {
          setFailure("The reply could not be produced. Please try again.");
          return;
        }

        for await (const event of readEvents(response.body)) {
          if (event.event === "tool") {
            const source = (event.data as { source?: string }).source;
            if (source) {
              // Flushed rather than left to React's own batching: this loop can receive
              // the tool event and the stream's closing frame within the same tick, and
              // batching would let the announcement below be overwritten before a screen
              // reader — or anybody — ever saw it announced.
              flushSync(() =>
                setProgress((seen) => ({
                  ...seen,
                  sources: [...seen.sources, source],
                })),
              );
            }
          } else if (event.event === "delta") {
            const text = (event.data as { text?: string }).text ?? "";
            setProgress((seen) => ({ ...seen, text: seen.text + text }));
          } else if (event.event === "failed") {
            setFailure("The reply could not be produced. Please try again.");
          }
        }
      } catch {
        // The reply is recorded whether or not this connection survived — the server runs
        // it to completion on its own thread. So a dropped stream costs the view, and
        // refetching the transcript below is what recovers it.
        setFailure(
          "The connection was lost. Your reply may still be in the conversation.",
        );
      } finally {
        setSending(false);
        setProgress(NOTHING);
        void queries.invalidateQueries({ queryKey: keys.messages(plantId) });
      }
    },
    [plantId, queries],
  );

  return { send, progress, sending, failure };
}
