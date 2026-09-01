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
export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
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
      ...(body !== undefined && !isFormData
        ? { "Content-Type": "application/json" }
        : {}),
      ...headers,
    },
    body:
      body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });
}

async function parse<T>(response: Response): Promise<T> {
  // 204, and any other empty body. `json()` on nothing throws, and several endpoints here
  // deliberately answer with nothing.
  if (
    response.status === 204 ||
    response.headers.get("content-length") === "0"
  ) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface Download {
  blob: Blob;
  /** What the server asked the file to be called. */
  filename: string;
}

/**
 * Fetch a binary body — an export archive — rather than JSON.
 *
 * A sibling of `request` rather than a mode of it: every other call in the application
 * wants JSON, and widening `request`'s return type to "or a Blob" would push a check into
 * every caller to buy one.
 *
 * The renewal branch is repeated deliberately. Sharing it would mean `request` returning
 * an unparsed `Response` and each caller doing its own parsing, which is the arrangement
 * this module exists to avoid.
 *
 * A plain `<a href>` cannot do this: the access token lives in memory, not a cookie, so an
 * anchor would arrive unauthenticated. The bytes come back here and are handed to the
 * browser as an object URL — the same mechanism `usePhoto` already uses for images.
 */
export async function download(
  path: string,
  options: RequestOptions = {},
): Promise<Download> {
  const response = await send(path, options);

  if (!response.ok) {
    const problem = await toProblem(response);
    if (problem.type === PROBLEM.sessionExpired && !options.retrying) {
      const renewed = await renew();
      if (renewed === null) throw new ApiError(problem);
      return download(path, { ...options, retrying: true });
    }
    throw new ApiError(problem);
  }

  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get("content-disposition")),
  };
}

/**
 * The name in a `Content-Disposition` header, or a fallback.
 *
 * Deliberately small: this reads the quoted `filename="…"` form the export sends and does
 * not attempt RFC 5987's encoded variant. A header this application does not produce is not
 * a header worth parsing, and guessing wrong would name somebody's data after a mistake.
 */
export function filenameFrom(
  disposition: string | null,
  fallback = "download",
): string {
  const quoted = disposition?.match(/filename="([^"]+)"/);
  return quoted?.[1] ?? fallback;
}
