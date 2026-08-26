import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { usePlant, useRemovePlant, useRenamePlant } from "@/api/hooks/plants";
import { readable } from "@/api/problems";
import { Field } from "@/components/Field";
import { LinkButton } from "@/components/LinkButton";
import { Notice } from "@/components/Notice";
import { Photo } from "@/components/Photo";
import { Severity } from "@/components/Severity";
import { Button } from "@/components/ui/button";
import { Chat } from "@/screens/chat/Chat";
import { Roadmap } from "@/screens/plants/Roadmap";

/** One plant: what it is, what has been found, what to do, and what was said about it. */
export function PlantDetail() {
  const { plantId = "" } = useParams();
  const { data, isPending, error } = usePlant(plantId);

  if (isPending) return <p role="status">Loading…</p>;
  if (error)
    return (
      <Notice tone="failure" title="This plant could not be loaded">
        {readable(error)}
      </Notice>
    );
  if (!data) return null;

  const { plant, diagnoses, roadmap_steps } = data;
  const latest = diagnoses[0];

  return (
    <div className="grid gap-8">
      <header className="flex flex-wrap items-start gap-4">
        <Photo
          photoKey={plant.photo_ref}
          className="h-24 w-24 rounded-md object-cover"
        />
        <div className="grid gap-1">
          <h1 className="text-2xl font-semibold">{plant.name}</h1>
          {plant.species ? (
            <p className="text-muted-foreground italic">{plant.species}</p>
          ) : null}
          <Severity severity={latest?.candidates?.[0]?.severity} />
        </div>
        <div className="ml-auto flex gap-2">
          <LinkButton to={`/plants/${plant.id}/diagnose`} variant="outline">
            Check again
          </LinkButton>
        </div>
      </header>

      {latest ? (
        <section aria-labelledby="finding">
          <h2 id="finding" className="mb-3 text-lg font-medium">
            What Plantopia thinks
          </h2>
          <p className="mb-3">{latest.reasoning}</p>
          <LinkButton
            to={`/diagnoses/${latest.id}`}
            variant="outline"
            size="sm"
          >
            See the full differential
          </LinkButton>
        </section>
      ) : (
        <Notice title="Nothing has been diagnosed yet">
          Start a check and Plantopia will tell you what it finds.
        </Notice>
      )}

      <Roadmap plantId={plant.id} steps={roadmap_steps} />

      <Chat plantId={plant.id} />

      <PlantSettings plantId={plant.id} name={plant.name} />
    </div>
  );
}

function PlantSettings({ plantId, name }: { plantId: string; name: string }) {
  const navigate = useNavigate();
  const rename = useRenamePlant(plantId);
  const remove = useRemovePlant();
  const [draft, setDraft] = useState(name);
  const [confirming, setConfirming] = useState(false);

  return (
    <section aria-labelledby="settings" className="border-t pt-6">
      <h2 id="settings" className="mb-3 text-lg font-medium">
        This plant
      </h2>

      <form
        className="mb-6 flex items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault();
          rename.mutate(draft);
        }}
      >
        <Field
          label="Name"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          required
        />
        <Button type="submit" variant="outline" disabled={rename.isPending}>
          Rename
        </Button>
      </form>

      {/* Removal takes two deliberate actions. A plant carries its whole history — every
          diagnosis, every photograph, every conversation — and one stray click should not
          be able to take all of it. */}
      {confirming ? (
        <div className="grid gap-3">
          <Notice tone="failure" title="Remove this plant?">
            Its photographs, diagnoses and conversation go with it. This cannot
            be undone.
          </Notice>
          <div className="flex gap-2">
            <Button
              variant="destructive"
              onClick={() =>
                remove.mutate(plantId, { onSuccess: () => navigate("/") })
              }
              disabled={remove.isPending}
            >
              Yes, remove it
            </Button>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
          </div>
        </div>
      ) : (
        <Button variant="outline" onClick={() => setConfirming(true)}>
          Remove this plant
        </Button>
      )}
    </section>
  );
}
