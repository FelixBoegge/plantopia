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
            <li key={plant.id}>
              <Card className="hover:border-primary/60 h-full overflow-hidden pt-0 transition-colors">
                <Link to={`/plants/${plant.id}`} className="block">
                  <Photo
                    photoKey={plant.photo_ref}
                    className="h-40 w-full object-cover"
                  />
                  <CardContent className="grid gap-2 pt-4">
                    <span className="font-medium">{plant.name}</span>
                    {plant.species ? (
                      <span className="text-muted-foreground text-sm italic">
                        {plant.species}
                      </span>
                    ) : null}
                    <div className="flex items-center gap-2">
                      <Severity
                        severity={latest_diagnosis?.candidates?.[0]?.severity}
                      />
                      {pending_step_count > 0 ? (
                        <span className="text-muted-foreground text-xs">
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
