import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  useAnswerRun,
  useCancelRun,
  useDiagnosis,
  useRun,
  useRuns,
  useStartRun,
} from "@/api/hooks/runs";
import { hasFinished, useRunStream } from "@/api/hooks/useRunStream";
import { allowance, useAccount } from "@/api/hooks/account";
import { usePlant } from "@/api/hooks/plants";
import { keys } from "@/app/queries";
import { LinkButton } from "@/components/LinkButton";
import { Notice } from "@/components/Notice";
import { Button } from "@/components/ui/button";
import { Differential } from "@/screens/wizard/Differential";
import { Questions } from "@/screens/wizard/Questions";
import { Reasoning } from "@/screens/wizard/Reasoning";
import { Upload } from "@/screens/wizard/Upload";

/**
 * Starting a diagnosis and watching it happen.
 *
 * The run's identifier lives in the address bar. That is what makes a reload survivable and
 * a link to a run shareable with oneself — and it is why this screen reads a status from the
 * server rather than remembering one, because after a reload it has nothing to remember.
 *
 * **Arriving with no run id in the address bar does not mean there isn't one.** Every link
 * that opens this screen fresh — "Diagnose a plant" in the header, the same on the plants
 * grid — points at a bare route, because none of them know whether a diagnosis is already
 * in flight. Landing here used to always mean the upload form, which is right the first
 * time and wrong every time after: navigate away mid-diagnosis and back through one of
 * those links, and the run kept running with nobody watching, landing you back at the
 * start of a new one instead of the progress of the old. So this checks for one still going
 * before ever showing the form, scoped to this plant when the route names one — re-checking
 * Kitchen basil should not hijack into an unrelated run on a different plant.
 */
export function Wizard() {
  const { plantId } = useParams();
  const [params, setParams] = useSearchParams();
  const runId = params.get("run");

  const start = useStartRun();
  const { data: run } = useRun(runId);
  const plant = usePlant(plantId);
  const { data: account } = useAccount();
  const runs = useRuns({ enabled: runId === null });

  const left = allowance(account);

  // The most recent run still going, if any — the one worth resuming into rather than
  // starting over. `runs` is newest first, so the first match is the most recent one.
  //
  // **Not computed from data still being revalidated.** `useRuns` forces `staleTime: 0`
  // specifically so a remount always rechecks rather than trusting a cache that can be
  // thirty seconds behind — but the cached (stale) answer is what a query returns
  // immediately while that recheck is still in flight, on this very first render. Acting
  // on it then means setting the run into the address bar from data already known to be
  // suspect, and nothing afterwards would take it back out once the fresh answer
  // disagreed: a run that had actually finished stayed resumed for the rest of this
  // component's life, moments after the cache that caused it was corrected. So this
  // waits for `isFetching` to clear — true for exactly as long as that recheck takes,
  // cached data or not — rather than for `data` to merely exist.
  const active =
    runId || runs.isFetching
      ? undefined
      : runs.data?.find(
          (candidate) =>
            !hasFinished(candidate.status) &&
            (!plantId || candidate.plant_id === plantId),
        );

  // Into the address bar, the same as a freshly started run: this screen reads a run from
  // the URL and nowhere else, so finding one still going is only half the fix without
  // also putting it where the rest of this component looks.
  useEffect(() => {
    if (active) setParams({ run: active.id }, { replace: true });
  }, [active, setParams]);

  // Diagnosing a named plant means the form is shaped by what that plant already is: it
  // stops asking for a species and a location that are on record. Rendering before the
  // record arrives would show those fields for an instant and then take them away, which
  // reads as the page changing its mind.
  if (!runId && plantId && plant.isPending) {
    return <p role="status">Loading this plant…</p>;
  }

  // Waiting to know whether one is already going, so the upload form does not flash before
  // being replaced by the progress of a run that was already in flight — and so a stale
  // cache is never the thing this decision got made from, on a remount that revalidates it.
  if (!runId && runs.isFetching) {
    return <p role="status">Checking for a diagnosis already in progress…</p>;
  }

  if (active) {
    return <Watching runId={active.id} finished={hasFinished(active.status)} />;
  }

  return runId ? (
    <Watching runId={runId} finished={hasFinished(run?.status)} />
  ) : (
    <>
      <h1 className="mb-6 text-2xl font-semibold">Diagnose a plant</h1>

      {/* Said before, not after. Being told "you have used your twenty diagnoses" by a failed
          diagnosis is being told too late — and the number comes from the same computation
          the server refuses with, so the two cannot disagree. */}
      {left?.exhausted ? (
        <Notice tone="failure" title="No diagnoses left this month">
          You have used all {left.limit}. You can start another after{" "}
          {left.resetsAt.toLocaleDateString()}.
        </Notice>
      ) : left && left.remaining <= 3 ? (
        <Notice
          title={`${left.remaining} diagnos${left.remaining === 1 ? "is" : "es"} left this month`}
        >
          Your allowance resets on {left.resetsAt.toLocaleDateString()}.
        </Notice>
      ) : null}
      <Upload
        blocked={Boolean(left?.exhausted)}
        busy={start.isPending}
        failure={start.error}
        fixedPlant={
          plantId && plant.data
            ? {
                id: plantId,
                name: plant.data.plant.name,
                // Already on record from the diagnosis that created this plant. Asking
                // again is asking somebody to retype what the application told them.
                species: plant.data.plant.species,
                locationKind: plant.data.plant.location_kind,
              }
            : undefined
        }
        onStart={(fields) =>
          start.mutate(
            { ...fields, plantId },
            {
              // Into the address bar, not into state. A reload a minute later must find the
              // run rather than an empty form.
              onSuccess: (created) =>
                setParams({ run: created.id }, { replace: true }),
            },
          )
        }
      />
    </>
  );
}

function Watching({ runId, finished }: { runId: string; finished: boolean }) {
  const navigate = useNavigate();
  const watched = useRunStream(runId);
  const { data: run } = useRun(runId);
  const answer = useAnswerRun(runId);
  const cancel = useCancelRun(runId);
  const queries = useQueryClient();
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  // The stream is the live view; the run is the record. After a reload the stream replays
  // everything, but a run that ended while nobody was watching is known from the run alone.
  const ending = watched.ending;
  const over = ending !== null || finished;

  /**
   * Waiting for the person, which is not the same as not working.
   *
   * `watched.paused` is the stream's own answer to this, current across a reconnect —
   * unlike `questions !== null`, which this used to be, and which never clears once
   * true. That reads as still-waiting for the entire resumed pass on a connection that
   * has been open the whole time, which is exactly wrong when `diagnose` and `plan` both
   * run after the interrupt and either can take a minute — the sidebar went quiet
   * precisely when it had the most to wait for.
   *
   * `!answer.isSuccess` covers the gap `paused` cannot: the moment right after
   * submitting, before the resumed pass has published anything at all to prove it on the
   * stream. Both are needed, because navigating away and back resumes into a *new*
   * connection with a *new* mutation that never ran — its own `isSuccess` is false
   * whether or not the answers were actually sent, so relying on it alone reintroduces
   * the same bug for a run reopened this way while `paused` alone would reintroduce it
   * for the first few seconds after answering.
   */
  const awaitingAnswers = watched.paused && !answer.isSuccess;
  const diagnosisId = ending?.diagnosisId ?? run?.diagnosis_id ?? null;
  const { data: detail } = useDiagnosis(diagnosisId);

  useEffect(() => {
    if (answer.isSuccess) setConfirmingCancel(false);
  }, [answer.isSuccess]);

  // A run creates a plant, and the grid was fetched before it existed. Without this,
  // finishing a first diagnosis and clicking home shows "Nothing here yet" — the query is
  // cached, nothing here writes through it, and it stays that way until it goes stale on its
  // own. The plant is real the whole time, which is what makes it look like data loss.
  const finishedPlantId = ending?.kind === "completed" ? ending.plantId : null;
  useEffect(() => {
    if (!finishedPlantId) return;
    void queries.invalidateQueries({ queryKey: keys.plants });
    void queries.invalidateQueries({ queryKey: keys.plant(finishedPlantId) });
  }, [finishedPlantId, queries]);

  return (
    <div className="grid gap-8">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-2xl font-semibold">Diagnosing your plant</h1>
        {!over ? (
          <div className="grid gap-2 text-right">
            {confirmingCancel ? (
              <>
                <p className="text-muted-foreground max-w-xs text-sm">
                  {/* Said plainly. "Cancel" reads as "undo", and this is not one — the step
                      already running finishes, and it has already been paid for. */}
                  Stopping ends the diagnosis. What it has already done is not
                  undone, and the work so far still counts towards your monthly
                  allowance.
                </p>
                <div className="flex justify-end gap-2">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => cancel.mutate()}
                    disabled={cancel.isPending}
                  >
                    Stop it
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setConfirmingCancel(false)}
                  >
                    Keep going
                  </Button>
                </div>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmingCancel(true)}
              >
                Stop this diagnosis
              </Button>
            )}
          </div>
        ) : null}
      </div>

      {/*
        The activity sits beside the run, not above it, and comes first in the DOM so that
        it leads when the columns collapse — on a phone, during a ninety-second run, the
        progress is the screen.
      */}
      <div className="grid gap-8 lg:grid-cols-[18rem_1fr] lg:items-start">
        <Reasoning
          steps={watched.steps}
          working={!over && !awaitingAnswers}
          connected={watched.connected}
        />

        <div className="grid gap-8">
          {watched.questions && !over ? (
            <Questions
              questions={watched.questions}
              identification={watched.identification}
              staleAfterDays={watched.staleAfterDays}
              busy={answer.isPending}
              locked={answer.isSuccess}
              failure={answer.error}
              onAnswer={(answers, species) =>
                answer.mutate({ answers, species })
              }
            />
          ) : null}

          {ending?.kind === "cancelled" || run?.status === "cancelled" ? (
            <Notice title="Stopped">
              This diagnosis was stopped. You can start another whenever you
              like.
            </Notice>
          ) : null}

          {ending?.kind === "failed" || run?.status === "failed" ? (
            <Notice tone="failure" title="This diagnosis could not be finished">
              {ending?.detail ??
                run?.error ??
                "Something went wrong. Please try again."}
            </Notice>
          ) : null}

          {ending?.rejected ? (
            <Notice title="Nothing to diagnose">
              {/* Not a failure. Nothing broke — the photograph could not be used, and saying so
              plainly is better than an error somebody reads as a bug. */}
              {ending.reason}
            </Notice>
          ) : null}

          {/* Above the result rather than after it. A finished diagnosis is a differential,
              a plan and a set of candidates; putting the way onward at the end of all that
              hides it behind a scroll from the moment it becomes useful. */}
          {over ? (
            <div className="flex gap-2">
              {(ending?.plantId ?? run?.plant_id) ? (
                <LinkButton to={`/plants/${ending?.plantId ?? run?.plant_id}`}>
                  Open this plant
                </LinkButton>
              ) : null}
              <Button
                variant="outline"
                onClick={() => navigate("/diagnose", { replace: true })}
              >
                Diagnose another
              </Button>
            </div>
          ) : null}

          {detail ? <Differential detail={detail} /> : null}
        </div>
      </div>
    </div>
  );
}
