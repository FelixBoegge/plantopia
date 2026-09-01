import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import {
  useAnswerRun,
  useCancelRun,
  useDiagnosis,
  useRun,
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
 */
export function Wizard() {
  const { plantId } = useParams();
  const [params, setParams] = useSearchParams();
  const runId = params.get("run");

  const start = useStartRun();
  const { data: run } = useRun(runId);
  const plant = usePlant(plantId);
  const { data: account } = useAccount();

  const left = allowance(account);

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
            ? { id: plantId, name: plant.data.plant.name }
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

      <Reasoning
        steps={watched.steps}
        working={!over && watched.questions === null}
        connected={watched.connected}
      />

      {watched.questions && !over ? (
        <Questions
          questions={watched.questions}
          identification={watched.identification}
          staleAfterDays={watched.staleAfterDays}
          busy={answer.isPending}
          failure={answer.error}
          onAnswer={(answers, species) => answer.mutate({ answers, species })}
        />
      ) : null}

      {ending?.kind === "cancelled" || run?.status === "cancelled" ? (
        <Notice title="Stopped">
          This diagnosis was stopped. You can start another whenever you like.
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

      {detail ? <Differential detail={detail} /> : null}

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
    </div>
  );
}
