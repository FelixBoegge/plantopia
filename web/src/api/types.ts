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
  created_at: string;
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

export interface Diagnosis {
  id: string;
  plant_id: string;
  observation_id: string;
  is_healthy: boolean;
  reasoning: string;
  candidates: Candidate[];
  created_at: string;
  cost_usd: number | null;
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
export interface Question {
  key: string;
  text: string;
  kind: "text" | "choice" | "boolean";
  options: string[];
}
