import { useState } from "react";
import { Image as ImageIcon, ImagePlus } from "lucide-react";

import { ACCEPTED_TYPES, MAX_IMAGE_MB, MAX_IMAGES } from "@/api/limits";
import { readable } from "@/api/problems";
import { Field } from "@/components/Field";
import { Notice } from "@/components/Notice";
import { Button, buttonVariants } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
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
  /**
   * The plant being diagnosed again, where there is one.
   *
   * `species` and `locationKind` come off its record. Both were established by the
   * diagnosis that created it, so a re-diagnosis that asked for them again would be asking
   * somebody to retype what the application already told them — and to get it wrong, since
   * whatever they type overrides what is on record.
   */
  fixedPlant?: {
    id: string;
    name: string;
    species?: string | null;
    locationKind?: "indoor" | "outdoor";
  };
}) {
  const [photographs, setPhotographs] = useState<File[]>([]);
  const knownSpecies = fixedPlant?.species ?? null;
  const knownLocation = fixedPlant?.locationKind;
  const [locationKind, setLocationKind] = useState<"indoor" | "outdoor">(
    knownLocation ?? "indoor",
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
          // What is on record wins over an empty box that was never shown.
          statedSpecies: knownSpecies ?? statedSpecies,
          locationKind: knownLocation ?? locationKind,
          notes,
        });
      }}
    >
      {failure ? (
        <Notice tone="failure" title="That could not be started">
          {readable(failure)}
        </Notice>
      ) : null}

      <div className="grid gap-3">
        {/*
          The input is the control; the label is what it looks like.

          A browser's own file button is a small grey rectangle wearing a word the browser
          chose, and it did not read as the first thing to do on a screen whose whole
          purpose is to take a photograph. Hiding it and dressing the label as a button
          changes the appearance and nothing else: it is still one native input, so the
          picker, the keyboard, and `setInputFiles` all still work. `sr-only` rather than
          `display: none`, because a hidden input is not focusable and this one must be —
          the ring is drawn on the label through `peer-focus-visible`, since the thing
          taking focus is invisible.
        */}
        <input
          id="photographs"
          type="file"
          accept={ACCEPTED_TYPES}
          multiple
          required
          onChange={(event) =>
            setPhotographs(Array.from(event.target.files ?? []))
          }
          className="peer sr-only"
        />
        <Label
          htmlFor="photographs"
          className={cn(
            buttonVariants({ variant: "outline", size: "lg" }),
            "peer-focus-visible:border-ring peer-focus-visible:ring-ring/50 w-fit peer-focus-visible:ring-3",
          )}
        >
          <ImagePlus />
          Upload images
        </Label>

        <p className="text-muted-foreground text-sm">
          A clear shot of the whole plant and a close-up of the problem work
          best.
        </p>
        {/* Said before a file is chosen, not after the server refuses one. Somebody who
            picked four photographs and waited for them to upload has done work this
            sentence could have saved. */}
        <p className="text-muted-foreground text-sm">
          Up to {MAX_IMAGES} images, PNG or JPEG, {MAX_IMAGE_MB} MB each.
        </p>

        {/* Shown back, so somebody can see what they picked before paying for it. */}
        {photographs.length ? (
          <>
            <p role="status" className="text-sm font-medium">
              {photographs.length} image{photographs.length === 1 ? "" : "s"}{" "}
              ready
            </p>
            <ul className="grid gap-2 sm:grid-cols-2">
              {photographs.map((file, index) => (
                // Two files can carry the same name — one from each of two folders — so the
                // name alone is not a key.
                <li
                  key={`${file.name}-${file.size}-${index}`}
                  className="bg-card flex items-center gap-3 rounded-lg border p-3 text-sm"
                >
                  <ImageIcon className="text-muted-foreground size-4 shrink-0" />
                  <span className="truncate font-medium">{file.name}</span>
                  <span className="text-muted-foreground ml-auto text-xs whitespace-nowrap">
                    {Math.max(1, Math.round(file.size / 1024))} kB
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>

      {knownSpecies ? (
        <p className="text-muted-foreground text-sm">
          Diagnosing{" "}
          <span className="text-foreground font-medium">
            {fixedPlant?.name}
          </span>
          , a known{" "}
          <span className="text-foreground italic">{knownSpecies}</span>
          {knownLocation
            ? knownLocation === "indoor"
              ? " kept indoors."
              : " kept outdoors."
            : "."}{" "}
          Plantopia will look again and say if it disagrees.
        </p>
      ) : (
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
      )}

      {knownLocation ? null : (
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
      )}

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
          {busy ? "Starting…" : "Start the diagnosis"}
        </Button>
      </div>
    </form>
  );
}
