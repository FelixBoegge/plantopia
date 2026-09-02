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
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {plants.map(({ plant, latest_diagnosis, pending_step_count }) => (
            // A fixed height on every card rather than letting content decide. A grid row
            // is only as tall as its tallest card, so one plant with a long name used to
            // leave its neighbours short and their photographs letterboxed.
            <li key={plant.id} className="h-40">
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
                    className="h-full w-28 shrink-0 object-cover"
                  />
                  <CardContent className="grid min-w-0 flex-1 content-start gap-2 py-4">
                    <span className="truncate font-medium">{plant.name}</span>
                    {plant.species ? (
                      <span className="text-muted-foreground truncate text-sm italic">
                        {plant.species}
                      </span>
                    ) : null}
                    {/* One line, and it stays one line. The badge and the step count used
                        to wrap mid-phrase in a narrow column, which reads as two facts
                        rather than one. */}
                    <div className="flex items-center gap-2 overflow-hidden">
                      <Severity
                        severity={latest_diagnosis?.candidates?.[0]?.severity}
                      />
                      {pending_step_count > 0 ? (
                        <span className="text-muted-foreground text-xs whitespace-nowrap">
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
