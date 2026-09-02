import { useState } from "react";

import { useSendMessage, useTranscript } from "@/api/hooks/useChat";
import { readable } from "@/api/problems";
import type { Message } from "@/api/types";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { sourceName } from "@/screens/chat/sources";

/**
 * Talking about one plant.
 *
 * **Every reply says what it consulted, on the reply itself.** A grounded answer and one the
 * agent produced from its own knowledge look identical otherwise, and only one of them is
 * worth trusting about a plant somebody is worried about.
 */
export function Chat({ plantId }: { plantId: string }) {
  const { data: messages, error } = useTranscript(plantId);
  const { send, progress, sending, failure } = useSendMessage(plantId);
  const [draft, setDraft] = useState("");

  const visible = (messages ?? []).filter((message) => message.role !== "tool");

  return (
    // A surface of its own, so the column reads as a panel beside the page rather than as
    // more of the page that happens to be over there. `sidebar` is a palette token defined
    // for exactly this, so it follows the theme instead of being a hardcoded grey.
    //
    // Sticky on wide screens: the conversation is a companion to whatever somebody is
    // reading, and one that scrolls away the moment they look at the history below is not.
    <section
      aria-labelledby="conversation"
      className="bg-sidebar grid gap-4 rounded-lg border p-4 xl:sticky xl:top-6"
    >
      <h2 id="conversation" className="text-lg font-medium">
        Ask about this plant
      </h2>

      {error ? <Notice tone="failure">{readable(error)}</Notice> : null}

      <ol className="grid gap-4">
        {visible.map((message) => (
          <li key={message.id}>
            <Reply message={message} />
          </li>
        ))}
      </ol>

      {/* Announced rather than merely appearing: somebody who cannot see the screen has no
          other way to know the agent is working. */}
      <div aria-live="polite" className="grid gap-2">
        {sending ? (
          <p className="text-muted-foreground text-sm">
            {progress.sources.length
              ? `Consulting ${progress.sources[progress.sources.length - 1]}…`
              : "Thinking…"}
          </p>
        ) : null}
        {progress.text ? <p className="text-sm">{progress.text}</p> : null}
      </div>

      {failure ? <Notice tone="failure">{failure}</Notice> : null}

      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!draft.trim()) return;
          const question = draft;
          setDraft("");
          void send(question);
        }}
      >
        <Input
          aria-label="Your question"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Why are the lower leaves yellow?"
          disabled={sending}
        />
        <Button type="submit" disabled={sending || !draft.trim()}>
          Ask
        </Button>
      </form>
    </section>
  );
}

function Reply({ message }: { message: Message }) {
  const mine = message.role === "user";
  const sources = [
    ...new Set((message.tool_calls ?? []).map((call) => sourceName(call.name))),
  ];

  return (
    // Two colours from the palette rather than two alignments. Both are palette tokens, so
    // the pair moves with the theme instead of being a second set to keep in step: what
    // somebody asked takes the accent, what Plantopia answered takes the plain surface with
    // a border. The alignment stays too, because colour alone is not a distinction for
    // anybody who cannot separate these two hues.
    <div className={`flex ${mine ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-3 py-2 ${
          mine
            ? "bg-accent text-accent-foreground rounded-br-sm"
            : "bg-card text-card-foreground rounded-bl-sm border"
        }`}
      >
        <p className="whitespace-pre-wrap">{message.content}</p>
        {!mine ? (
          <p className="text-muted-foreground mt-1 text-xs">
            {sources.length
              ? `Consulted ${sources.join(", ")}`
              : "Answered from the model's own knowledge, without a lookup"}
          </p>
        ) : null}
      </div>
    </div>
  );
}
