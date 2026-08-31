import { useState } from "react";

import { readable } from "@/api/problems";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { StartRun } from "@/api/hooks/runs";

/**
 * Choosing what to look at.
 *
 * **Nothing starts until somebody says so.** A run costs real money and takes a minute and
 * a half, and beginning one as a side effect of choosing a file is a bill nobody agreed to.
 *
 * **Nobody is asked where the plant is here.** The photograph usually knows, and asking
 * somebody to type what the file already says is asking them to do the machine's work.
 * Where it does not know, the run asks at the pause it was going to make anyway — one
 * interruption rather than two, and by then it is one field among several.
 */
export function Upload({
  onStart,
  busy,
  blocked = false,
  failure,
  fixedPlant,
}: {
  onStart: (start: Omit<StartRun, "plantId">) => void;
  busy: boolean;
  /** The allowance is used up, so the server would refuse this. */
  blocked?: boolean;
  failure: unknown;
  fixedPlant?: { id: string; name: string };
}) {
  const [photographs, setPhotographs] = useState<File[]>([]);
  const [locationKind, setLocationKind] = useState<"indoor" | "outdoor">(
    "indoor",
  );
  const [statedSpecies, setStatedSpecies] = useState("");
  const [notes, setNotes] = useState("");

  return (
    <form
      className="grid max-w-xl gap-6"
      // The application shows its own messages, in its own words, in a place a screen
      // reader announces. Native validation bubbles are none of those things, and they
      // disagree with what the server says the moment the two rules differ.
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        onStart({
          photographs,
          // The plant this re-checks, where there is one. A fresh diagnosis names its
          // plant from what the identification found — nobody is asked to name a plant
          // they came here to have identified.
          plantName: fixedPlant?.name,
          statedSpecies,
          locationKind,
          notes,
        });
      }}
    >
      {failure ? (
        <Notice tone="failure" title="That could not be started">
          {readable(failure)}
        </Notice>
      ) : null}

      <div className="grid gap-2">
        <Label htmlFor="photographs">Photographs</Label>
        <input
          id="photographs"
          type="file"
          accept="image/*"
          multiple
          required
          onChange={(event) =>
            setPhotographs(Array.from(event.target.files ?? []))
          }
          className="text-sm"
        />
        <p className="text-muted-foreground text-sm">
          A clear shot of the whole plant and a close-up of the problem work
          best.
        </p>
        {/* Shown back, so somebody can see what they picked before paying for it. */}
        {photographs.length ? (
          <ul className="text-muted-foreground text-sm">
            {photographs.map((file) => (
              <li key={file.name}>{file.name}</li>
            ))}
          </ul>
        ) : null}
      </div>

      <Field
        label="Do you know what it is?"
        value={statedSpecies}
        onChange={(event) => setStatedSpecies(event.target.value)}
        hint={
          // Optional, and said so plainly. Most people asking what is wrong with a plant do
          // not know what it is — that is frequently why they are asking — and a field that
          // looked required would stop the people this exists for.
          "Optional. A common or botanical name. Plantopia works it out from the " +
          "photographs either way, and will say if it disagrees."
        }
      />

      <fieldset className="grid gap-2">
        <legend className="text-sm font-medium">Where does it live?</legend>
        <div className="flex gap-4">
          {(["indoor", "outdoor"] as const).map((where) => (
            <label key={where} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="location"
                value={where}
                checked={locationKind === where}
                onChange={() => setLocationKind(where)}
              />
              {where === "indoor" ? "Indoors" : "Outdoors"}
            </label>
          ))}
        </div>
      </fieldset>

      <Field
        label="Anything else worth knowing?"
        value={notes}
        onChange={(event) => setNotes(event.target.value)}
        hint="Optional."
      />

      <div>
        <Button
          type="submit"
          disabled={busy || blocked || photographs.length === 0}
        >
          {busy ? "Starting…" : "Start the check"}
        </Button>
      </div>
    </form>
  );
}
