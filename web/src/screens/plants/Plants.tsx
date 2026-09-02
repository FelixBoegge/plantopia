import { Link } from "react-router-dom";

import { usePlants } from "@/api/hooks/plants";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { Photo } from "@/components/Photo";
import { Severity } from "@/components/Severity";
import { LinkButton } from "@/components/LinkButton";
import { Card, CardContent } from "@/components/ui/card";

/**
 * Everything this person is looking after.
 *
 * Three states, all of which happen: plants, no plants yet, and a load that failed. The
 * third is the one usually left out, and a screen that shows an empty grid because a
 * request failed is a screen that says somebody's plants are gone.
 */
export function Plants() {
  const { data: plants, isPending, error } = usePlants();

  return (
    <>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Your plants</h1>
        <LinkButton to="/diagnose">Diagnose a plant</LinkButton>
      </div>

      {isPending ? <p role="status">Loading your plants…</p> : null}

      {error ? (
        <Notice tone="failure" title="Your plants could not be loaded">
          {readable(error)}
        </Notice>
      ) : null}

      {plants?.length === 0 ? (
        <Card>
          <CardContent className="grid gap-4 py-10 text-center">
            <p className="text-lg">Nothing here yet.</p>
            <p className="text-muted-foreground">
              Photograph a plant you are worried about and Plantopia will work
              out what is wrong with it.
            </p>
            <div>
              <LinkButton to="/diagnose">Diagnose your first plant</LinkButton>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {plants?.length ? (
        // Three at most. Four and five were for a page with no maximum width; inside a
        // centred column they would leave each card too narrow for the photograph and the
        // name to sit beside each other.
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plants.map(({ plant, latest_diagnosis, pending_step_count }) => (
            // A floor, not a fixed height. Grid rows stretch their items, so every card in
            // a row still matches the tallest — but a long name can now take a second line
            // and make the whole row taller, rather than being cut off to preserve a
            // height nobody asked for.
            <li key={plant.id} className="min-h-40">
              <Card className="hover:border-primary/60 h-full overflow-hidden py-0 transition-colors">
                {/*
                  The photograph beside the text rather than above it. These are nearly all
                  portraits, and a wide strip across the top of a card crops a tall picture
                  to a band of leaf — the plant somebody is trying to recognise ends up the
                  part that was cut. A tall column at a fixed width crops the sides of a
                  portrait instead, which is where the least is happening.
                */}
                <Link to={`/plants/${plant.id}`} className="flex h-full">
                  <Photo
                    photoKey={plant.photo_ref}
                    className="h-full w-32 shrink-0 object-cover"
                  />
                  <CardContent className="grid min-w-0 flex-1 content-center gap-2 py-4">
                    <span className="text-lg leading-tight font-semibold">
                      {plant.name}
                    </span>
                    {plant.species ? (
                      <span className="text-muted-foreground truncate text-sm italic">
                        {plant.species}
                      </span>
                    ) : null}
                    {/* Stacked, and each one holds its line. Side by side they competed
                        for a narrow column and wrapped mid-phrase, which reads as two
                        facts where there is one. */}
                    <div className="flex flex-col items-start gap-1 overflow-hidden">
                      <Severity
                        severity={latest_diagnosis?.candidates?.[0]?.severity}
                        className="text-sm"
                      />
                      {pending_step_count > 0 ? (
                        <span className="text-muted-foreground text-sm whitespace-nowrap">
                          {pending_step_count} step
                          {pending_step_count === 1 ? "" : "s"} to do
                        </span>
                      ) : null}
                    </div>
                  </CardContent>
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}
