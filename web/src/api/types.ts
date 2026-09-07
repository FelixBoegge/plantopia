/**
 * The shapes this application reads from the API.
 *
 * Hand-written rather than generated. There are a dozen of them, they are read by whoever
 * is writing the screen that uses them, and a generator would be a build step, a dependency
 * and a diff to review for the saving of an afternoon.
 *
 * They are a claim about the server, and the claim is checked where it matters: the tests
 * mock the API at the network boundary with these shapes, and the end-to-end runs hit the
 * real one.
 */

export type RunStatus =
  | "queued"
  | "running"
  | "awaiting_answers"
  | "completed"
  | "failed"
  | "cancelled";

export interface Run {
  id: string;
  plant_id: string | null;
  kind: string;
  status: RunStatus;
  created_at: string;
  finished_at: string | null;
  diagnosis_id: string | null;
  error: string | null;
}

export interface Accepted {
  detail: string;
  /**
   * Whether this deployment can put a message in somebody's inbox at all.
   *
   * Absent from an older server, and read as `true` when it is: claiming an email was sent
   * is the safer of the two wrong answers, since the other one tells somebody to go read a
   * log that may not contain anything.
   */
  email_configured?: boolean;
}

export interface Session {
  access_token: string;
  token_type: string;
  expires_in_seconds: number;
}

export interface Account {
  id: string;
  email: string;
  created_at: string;
  tier: string;
  role: "member" | "admin";
  consent_version: string;
  consent_at: string;
  runs_used: number;
  runs_allowed: number;
  /**
   * Whether this account may read the evaluation results.
   *
   * The server's answer, not a rule to re-derive from `role`. `AppHeader` used to compare
   * the role to "admin" itself and kept hiding the link after a deployment opened the page
   * to members.
   */
  may_read_evaluations: boolean;
  allowance_resets_at: string;
}

export interface Plant {
  id: string;
  name: string;
  species: string | null;
  species_confidence: number | null;
  location_kind: "indoor" | "outdoor";
  location_text: string | null;
  photo_ref: string | null;
  created_at: string;
}

export interface PlantSummary {
  plant: Plant;
  latest_diagnosis: Diagnosis | null;
  pending_step_count: number;
}

export interface Observation {
  id: string;
  plant_id: string;
  kind: "initial" | "recheck";
  photo_refs: string[];
  user_notes: string | null;
  /** When the photographs were uploaded. */
  created_at: string;
  /**
   * When the photographs were *taken*, where the camera recorded it.
   *
   * Different from `created_at` for anybody who did not upload immediately, and this is
   * what the timeline dates an observation by — a history ordered by upload puts events in
   * an order the plant never experienced. `null` where no photograph declared one.
   */
  captured_at: string | null;
  /**
   * Where the photographs were taken, to about eleven kilometres.
   *
   * Deliberately not rendered anywhere: a coarse pair of coordinates is not something to
   * show somebody who already told you where their plant is. Present so that the three
   * fields a photograph carries stay together.
   */
  latitude: number | null;
  longitude: number | null;
  /** The weather recorded against this observation, or `null` where none was. */
  weather: WeatherSummary | null;
}

export interface PlantDetail {
  plant: Plant;
  observations: Observation[];
  diagnoses: Diagnosis[];
  roadmap_steps: RoadmapStep[];
  feedback_due: boolean;
}

export interface Candidate {
  disorder_id: string;
  name: string;
  /** How likely this candidate is, 0 to 1. Rendered as a proportion, never as a verdict. */
  probability: number;
  severity: string;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  /** The quick check that would separate this from the others. */
  distinguishing_test: string;
}

/** One day of weather where the plant is. */
export interface WeatherDay {
  /** The date, in ISO form. The whole point: a plant responds to *when*. */
  on: string;
  min_temp_c: number;
  max_temp_c: number;
  precip_mm: number;
}

/**
 * The weather a diagnosis was reasoned against.
 *
 * `days` is the window before the photograph was taken; `forecast` is the week ahead from
 * the day the run happened. Two anchors because there are two questions — what the plant
 * stood in, and what the plan has to survive.
 *
 * Both are empty on a summary stored before the series was kept, which still carries the
 * aggregates below.
 */
export interface WeatherSummary {
  min_temp_c: number;
  max_temp_c: number;
  total_precip_mm: number;
  frost_days: number;
  heat_days: number;
  days_covered: number;
  days: WeatherDay[];
  forecast: WeatherDay[];
}

export interface Diagnosis {
  id: string;
  plant_id: string;
  observation_id: string;
  is_healthy: boolean;
  reasoning: string;
  candidates: Candidate[];
  /** Which method produced the species this was reasoned from; null means unknown. */
  species_method: "typed" | "vision" | "plantnet" | "agreed" | null;
  /**
   * How this compared with the diagnosis before it.
   *
   * `null` on a first diagnosis, which has nothing to compare against, and on any re-check
   * made before this was recorded.
   */
  progress_verdict: "improving" | "static" | "worsening" | "new_problem" | null;
  /** Whether a person picked that species, as opposed to it being the leading candidate. */
  species_confirmed: boolean;
  /**
   * The weather this was reasoned against, or `null` where none was recorded.
   *
   * `null` covers an indoor plant, a lookup that failed, and every diagnosis made before
   * the series was kept — deliberately not an empty window, which would say the weather was
   * looked up and found to be nothing at all.
   */
  weather: WeatherSummary | null;
  created_at: string;

  /**
   * What this diagnosis spent. `null` where nothing was measured — a failed run records no
   * cost, and neither does any diagnosis made before it was kept. Render nothing rather
   * than "$0.0000", which would claim the run was measured and free.
   */
  cost_usd: number | null;
  token_usage: TokenUsage | null;

  /** Every passage the diagnosis was given, in the order retrieval returned them. */
  sources: Source[];
}

export type StepStatus = "pending" | "done" | "skipped";

export interface RoadmapStep {
  id: string;
  diagnosis_id: string;
  ordinal: number;
  action: string;
  rationale: string;
  success_signal: string;
  /** Integer management tier: 1 is the gentlest thing that might work. */
  tier: number;
  due_date: string;
  status: StepStatus;
  completed_at: string | null;
}

export interface Source {
  name: string;
  section: string;
  origin: "knowledge_base" | "web";
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface DiagnosisDetail {
  diagnosis: Diagnosis;
  roadmap_steps: RoadmapStep[];
}

export interface Message {
  id: string;
  plant_id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  /** What the agent consulted to produce this reply, if anything, and what came back. */
  tool_calls:
    { name: string; args: Record<string, unknown>; result: string }[] | null;
  created_at: string;
}

export interface ProfileFact {
  /** The fact itself is the identity — there is no separate id, and forgetting takes text. */
  fact: string;
  source: "inferred" | "stated";
  confidence: number;
  first_seen: string;
  last_confirmed: string;
}

export interface Evaluation {
  generated_at: string | null;
  results: Record<string, unknown> | null;
}

/**
 * The question a paused run asks.
 *
 * These arrive in a stream event rather than in a response body, so they are the one shape
 * here that the OpenAPI document does not describe and `tests/api/test_client_types.py`
 * therefore cannot check. That is not a small caveat: this interface said `prompt` where the
 * graph says `text`, and carried no `kind` at all, so every question rendered as an
 * unlabelled text box — including the ones with four fixed options. It looked correct in
 * every component test, because the fixtures were written from this interface rather than
 * from the graph.
 *
 * `tests/api/test_question_shape_agrees.py` now compares this against `agent/schemas.py`
 * directly.
 */
/**
 * One answer to "what is this plant?", offered at the pause when the methods disagree.
 *
 * Like `Question`, this arrives in a stream event rather than a response body, so the
 * OpenAPI document does not describe it and `tests/api/test_client_types.py` cannot check
 * it. `tests/api/test_identification_shape_agrees.py` compares it against
 * `agent/schemas.py` directly, for the reason recorded there: the last shape in this
 * position said `prompt` where the graph said `text`, and every component test agreed with
 * the bug because the fixtures had been written from this file.
 *
 * `method` is which of them produced it. It is the whole reason the choice is worth
 * showing — a list of names with no provenance asks somebody to pick on nothing.
 */
export interface SpeciesCandidate {
  common_name: string;
  scientific_name: string | null;
  confidence: number;
  method: "typed" | "vision" | "plantnet" | "agreed";
}

export interface Question {
  key: string;
  text: string;
  kind: "text" | "choice" | "boolean" | "date";
  options: string[];
  /**
   * An answer the run already believes — a place read from the photograph, say.
   *
   * Rendered *as the answer*, not as a suggestion beside an empty field: it is what will be
   * used unless somebody says otherwise, and a suggestion asks the common case to do work
   * while a filled field asks only the uncommon one.
   */
  prefill: string | null;
  /**
   * Where a prefilled answer came from, in a phrase to show under the field — and any
   * credit the source's terms require, because the credit belongs with the datum rather
   * than with the page.
   */
  prefill_note: string | null;
  /** Whether the run refuses to continue while this is empty. Almost nothing is. */
  required: boolean;
}
