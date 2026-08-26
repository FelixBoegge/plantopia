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

export interface PlantSummary {
  id: string;
  name: string;
  species: string | null;
  photo_ref: string | null;
  created_at: string;
  latest_severity: string | null;
  outstanding_steps: number;
}

export interface Candidate {
  disorder_id: string;
  name: string;
  confidence: number;
  evidence_for: string[];
  evidence_against: string[];
  confirming_test: string | null;
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
  title: string;
  detail: string | null;
  tier: string;
  due_date: string | null;
  status: StepStatus;
  completed_at: string | null;
}

export interface DiagnosisDetail {
  diagnosis: Diagnosis;
  roadmap_steps: RoadmapStep[];
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls: string[] | null;
  created_at: string;
}

export interface ProfileFact {
  id: string;
  fact: string;
  source: string;
  confidence: number;
  created_at: string;
}

export interface Evaluation {
  generated_at: string | null;
  results: Record<string, unknown> | null;
}

/** The question a paused run asks. */
export interface Question {
  key: string;
  prompt: string;
  options?: string[];
}
