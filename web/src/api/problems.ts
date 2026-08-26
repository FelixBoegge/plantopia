/**
 * What a refusal means.
 *
 * The API answers every failure in one shape — RFC 9457 problem details — with a stable
 * `type` a client branches on. This turns that into something the application can decide
 * with, rather than a status code and a sentence.
 *
 * The types are copied from the server rather than imported, because there is nothing to
 * import from across a language boundary. A test asserts the two lists agree.
 */

export const PROBLEM = {
  notFound: "https://plantopia.example/problems/not-found",
  invalidRequest: "https://plantopia.example/problems/invalid-request",
  internal: "https://plantopia.example/problems/internal-error",
  invalidLink: "https://plantopia.example/problems/invalid-link",
  unauthenticated: "https://plantopia.example/problems/unauthenticated",
  sessionExpired: "https://plantopia.example/problems/session-expired",
  quotaExceeded: "https://plantopia.example/problems/quota-exceeded",
  dailyCap: "https://plantopia.example/problems/daily-cap-reached",
  rateLimited: "https://plantopia.example/problems/rate-limited",
  conflict: "https://plantopia.example/problems/conflict",
  tooBusy: "https://plantopia.example/problems/too-busy",
} as const;

export type ProblemType = (typeof PROBLEM)[keyof typeof PROBLEM];

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  /** Present on a validation failure: which fields were rejected, and why. */
  errors?: { location: string; message: string }[];
  /** Present on a quota refusal. */
  limit?: number;
  used?: number;
  resets_at?: string;
  /** Present on a rate-limit refusal. */
  retry_after_seconds?: number;
}

export class ApiError extends Error {
  readonly problem: Problem;
  readonly status: number;

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.problem = problem;
    this.status = problem.status;
  }

  is(type: ProblemType): boolean {
    return this.problem.type === type;
  }
}

/**
 * A sentence to show somebody.
 *
 * Never the raw `detail` for an internal failure: that one is written for a log. Everything
 * else the API sends is written for a person, which is the whole point of the shape.
 */
export function readable(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.is(PROBLEM.internal)) return "Something went wrong at our end. Please try again.";
    return error.problem.detail ?? error.problem.title;
  }
  return "Something went wrong. Please try again.";
}

/**
 * Turn a failed response into a problem.
 *
 * A response that is not JSON, or is JSON that is not a problem, still has to become one —
 * a proxy returning HTML on a 502 is the case this exists for, and it must not surface as
 * "unexpected token < in JSON".
 */
export async function toProblem(response: Response): Promise<Problem> {
  try {
    const body = (await response.json()) as Partial<Problem>;
    if (typeof body?.type === "string" && typeof body?.status === "number") {
      return body as Problem;
    }
  } catch {
    // Fall through to the constructed problem below.
  }
  return {
    type: PROBLEM.internal,
    title: "Unexpected response",
    status: response.status,
  };
}
