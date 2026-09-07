/**
 * A harness result, read into what a page can render.
 *
 * **The API hands this through untouched.** `services/evaluations.py` parses the JSON the
 * harness wrote and returns the object; no schema describes it, and `test_client_types`
 * cannot check it because there is nothing on the API side to check against. So the shape
 * here is the harness's, and this module is the one place that knows it.
 *
 * Every reader returns `null` — or an empty list — for a section it cannot find, rather
 * than throwing. The page omits what is missing. A harness that grows a field is a page
 * that ignores it; a harness that drops or renames one is a page missing a panel. Neither
 * is a blank screen, and that graceful edge is the whole reason for reading it here rather
 * than trusting the file's shape at the point of render.
 *
 * The alternative is worth naming: a typed `EvaluationOut` on the API would make the
 * contract checkable, and the harness would then have to keep it. That is the better answer
 * once anything other than this page reads a result. It is not worth a schema today, and
 * this module is small enough to be replaced by one.
 */

export interface CategoryScore {
  name: string;
  top1: number;
  top3: number;
  scored: number;
}

export interface Accuracy {
  top1: number;
  top3: number;
  /** How many cases the top-1 rate stands for. A rate over 28 is not a rate over 3. */
  top1Cases: number;
  scored: number;
  failed: number;
  /** Weakest first: what somebody opens this page to find. */
  byCategory: CategoryScore[];
}

export interface Metric {
  key: string;
  label: string;
  value: number;
  /** How many cases it actually scored, and of how many. `M22` is why this travels. */
  scored: number | null;
  total: number | null;
  /** What it measures, for a reader who cannot act on a bare percentage. */
  meaning: string;
  /** Anything that makes this one not quite comparable with the others. */
  caveat: string | null;
}

export interface StabilityMeasure {
  key: string;
  label: string;
  value: number;
  /** Two of the three read better when lower, which no colour conveys on its own. */
  higherIsBetter: boolean;
  meaning: string;
}

export interface Stability {
  measures: StabilityMeasure[];
  cases: number | null;
  runsPerCase: number | null;
}

export interface Provenance {
  reasoningModel: string | null;
  visionModel: string | null;
  embeddingModel: string | null;
  temperature: number | null;
  corpusDocuments: number | null;
  goldenSetSize: number | null;
  profile: string | null;
  totalTokens: number | null;
  costUsd: number | null;
}

export interface CaseRow {
  id: string;
  category: string | null;
  groundTruth: string;
  candidates: string[];
  top1Hit: boolean;
  top3Hit: boolean;
  questionsAsked: number;
  error: string | null;
}

export interface Report {
  accuracy: Accuracy | null;
  metrics: Metric[];
  stability: Stability | null;
  provenance: Provenance | null;
  cases: CaseRow[];
  nearMisses: number | null;
  retriedCases: string[];
}

/** What each Ragas metric measures, in words somebody can act on. */
const MEANINGS: Record<
  string,
  { label: string; meaning: string; caveat: string | null }
> = {
  faithfulness: {
    label: "Faithfulness",
    meaning:
      "How much of what the diagnosis claimed is supported by the passages it actually read. This is the hallucination check: a low score means it asserted things the corpus does not say.",
    caveat: null,
  },
  answer_relevancy: {
    label: "Answer relevancy",
    meaning:
      "Whether the diagnosis answered the question that was asked, rather than something adjacent to it.",
    caveat: null,
  },
  context_precision: {
    label: "Context precision",
    meaning:
      "What fraction of the retrieved material was relevant — a question about ranking rather than about the answer.",
    caveat:
      "Scored over the similarity-ranked passages only, where the other three see everything the model read. The look-alikes sections and the documents `hypothesise` named were fetched by identifier on purpose, with no ranking to judge, so counting them as retrieval misses would mark down a mechanism working as designed (M22).",
  },
  context_recall: {
    label: "Context recall",
    meaning:
      "Whether the passages needed to reach the right answer were retrieved at all. Read it next to precision: recall asks if the material was there, precision asks how well it was ranked.",
    caveat: null,
  },
};

/** In the order they are worth reading, not the order the file lists them. */
const METRIC_ORDER = [
  "faithfulness",
  "answer_relevancy",
  "context_precision",
  "context_recall",
];

const STABILITY: Record<string, Omit<StabilityMeasure, "value">> = {
  top1_agreement: {
    key: "top1_agreement",
    label: "Top-1 agreement",
    higherIsBetter: true,
    meaning: "How often repeated runs of one case led with the same disorder.",
  },
  candidate_churn: {
    key: "candidate_churn",
    label: "Candidate churn",
    higherIsBetter: false,
    meaning:
      "How much the rest of the differential moved between runs of the same case. The tail is measurably less stable than the head.",
  },
  question_drift: {
    key: "question_drift",
    label: "Question drift",
    higherIsBetter: false,
    meaning:
      "How much the clarifying questions varied between runs of the same case. They are model-generated, so some drift is expected.",
  },
};

function object(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function str(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function readAccuracy(results: Record<string, unknown>): Accuracy | null {
  const source = object(results.accuracy);
  const top1 = num(source?.top1);
  const top3 = num(source?.top3);
  const scored = num(source?.scored);
  if (source === null || top1 === null || top3 === null || scored === null)
    return null;

  const categories = object(source.by_category) ?? {};
  const byCategory = Object.entries(categories)
    .map(([name, value]) => {
      const entry = object(value);
      return {
        name,
        top1: num(entry?.top1) ?? 0,
        top3: num(entry?.top3) ?? 0,
        scored: num(entry?.scored) ?? 0,
      };
    })
    // Weakest first, and by case count where two categories score alike — a tie broken
    // towards the one with more evidence behind it.
    .sort((a, b) => a.top1 - b.top1 || b.scored - a.scored);

  return {
    top1,
    top3,
    top1Cases: Math.round(top1 * scored),
    scored,
    failed: num(source.failed) ?? 0,
    byCategory,
  };
}

function readMetrics(results: Record<string, unknown>): Metric[] {
  const source = object(results.ragas);
  if (source === null) return [];
  const counts = object(results.ragas_counts) ?? {};

  return METRIC_ORDER.flatMap((key) => {
    const value = num(source[key]);
    if (value === null) return [];
    const described = MEANINGS[key];
    const count = object(counts[key]);
    return [
      {
        key,
        label: described?.label ?? key.replace(/_/g, " "),
        value,
        scored: num(count?.scored),
        total: num(count?.total),
        meaning: described?.meaning ?? "",
        caveat: described?.caveat ?? null,
      },
    ];
  });
}

function readStability(results: Record<string, unknown>): Stability | null {
  const source = object(results.stability);
  if (source === null) return null;

  // `Object.entries` rather than keys-then-index: under `noUncheckedIndexedAccess` the
  // lookup is `T | undefined`, and entries carries the value already typed.
  const measures = Object.entries(STABILITY).flatMap(([key, described]) => {
    const value = num(source[key]);
    return value === null ? [] : [{ ...described, value }];
  });
  if (!measures.length) return null;

  return {
    measures,
    cases: num(source.cases),
    runsPerCase: num(source.runs_per_case),
  };
}

function readProvenance(results: Record<string, unknown>): Provenance | null {
  const source = object(results.provenance);
  if (source === null) return null;
  const usage = object(source.total_token_usage);

  return {
    reasoningModel: str(source.reasoning_model),
    visionModel: str(source.vision_model),
    embeddingModel: str(source.embedding_model),
    temperature: num(source.temperature),
    corpusDocuments: num(source.corpus_documents),
    goldenSetSize: num(source.golden_set_size),
    profile: str(source.profile),
    totalTokens: num(usage?.total_tokens),
    costUsd: num(source.total_cost_usd),
  };
}

function readCases(results: Record<string, unknown>): CaseRow[] {
  if (!Array.isArray(results.cases)) return [];

  return results.cases.flatMap((entry) => {
    const source = object(entry);
    const id = str(source?.case_id);
    const groundTruth = str(source?.ground_truth);
    if (source === null || id === null || groundTruth === null) return [];

    const candidates = strings(source.candidates);
    return [
      {
        id,
        category: str(source.category),
        groundTruth,
        candidates,
        // Recomputed here rather than read: the harness records what came back, and
        // whether that counts as a hit is the same comparison `eval/metrics.py` makes.
        // A case that failed has no candidates and is a miss at both ranks.
        top1Hit: candidates[0] === groundTruth,
        top3Hit: candidates.slice(0, 3).includes(groundTruth),
        questionsAsked: strings(source.questions_asked).length,
        error: str(source.error),
      },
    ];
  });
}

export function readReport(results: Record<string, unknown>): Report {
  return {
    accuracy: readAccuracy(results),
    metrics: readMetrics(results),
    stability: readStability(results),
    provenance: readProvenance(results),
    cases: readCases(results),
    nearMisses: num(results.near_misses),
    retriedCases: strings(results.retried_cases),
  };
}
