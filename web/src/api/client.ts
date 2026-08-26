/**
 * Every request the application makes.
 *
 * One place, so that the token, the renewal and the problem-details handling exist once.
 * A component calling `fetch` directly would be a component with its own opinion about all
 * three.
 */

import { ApiError, PROBLEM, toProblem } from "@/api/problems";
import { currentToken, renew } from "@/api/session";

const BASE = "/api/v1";

export interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Set internally to stop a renewed request renewing again. */
  retrying?: boolean;
}

/**
 * Make a request, renewing the session once if the token has expired.
 *
 * The two refusals are deliberately handled differently, because the API distinguishes them
 * for exactly this reason: an expired token means renew and carry on, and an unauthenticated
 * one means the session is over. A client that treated them alike would either sign people
 * out every fifteen minutes or retry a sign-in that cannot succeed.
 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await send(path, options);

  if (response.ok) return parse<T>(response);

  const problem = await toProblem(response);

  if (problem.type === PROBLEM.sessionExpired && !options.retrying) {
    const renewed = await renew();
    if (renewed === null) throw new ApiError(problem);
    return request<T>(path, { ...options, retrying: true });
  }

  throw new ApiError(problem);
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const { body, retrying: _retrying, headers, ...rest } = options;
  const token = currentToken();

  const isFormData = body instanceof FormData;
  return fetch(`${BASE}${path}`, {
    ...rest,
    // The refresh cookie is scoped to the auth routes, so this costs nothing elsewhere and
    // is required there.
    credentials: "include",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      // FormData sets its own content type, including the multipart boundary. Setting one
      // here would produce a boundary the body does not use.
      ...(body !== undefined && !isFormData ? { "Content-Type": "application/json" } : {}),
      ...headers,
    },
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });
}

async function parse<T>(response: Response): Promise<T> {
  // 204, and any other empty body. `json()` on nothing throws, and several endpoints here
  // deliberately answer with nothing.
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return (await response.json()) as T;
}
