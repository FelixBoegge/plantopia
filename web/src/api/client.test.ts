/**
 * The fetch wrapper, and the renewal that is the subtlest thing in this application.
 *
 * The API is mocked at the network boundary, so what runs here is the code that will run in
 * a browser — including the header it sets, the cookie it asks for, and the retry it makes.
 */

import { HttpResponse, http } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { request } from "@/api/client";
import { ApiError, PROBLEM, readable } from "@/api/problems";
import { forget, currentToken, onSessionLost, setToken } from "@/api/session";
import { server } from "@/test/server";

const EXPIRED = {
  type: PROBLEM.sessionExpired,
  title: "Session expired",
  status: 401,
  detail: "The access token has expired. Refresh it and try again.",
};

const UNAUTHENTICATED = {
  type: PROBLEM.unauthenticated,
  title: "Not signed in",
  status: 401,
  detail: "This endpoint needs a signed-in account.",
};

afterEach(() => {
  forget();
  onSessionLost(() => {});
});

describe("sending a request", () => {
  it("sends the token as a header", async () => {
    setToken("a-token");
    let seen: string | null = null;
    server.use(
      http.get("/api/v1/plants", ({ request: incoming }) => {
        seen = incoming.headers.get("Authorization");
        return HttpResponse.json([]);
      }),
    );

    await request("/plants");

    expect(seen).toBe("Bearer a-token");
  });

  it("never puts the token in the URL", async () => {
    setToken("a-token");
    let url = "";
    server.use(
      http.get("/api/v1/plants", ({ request: incoming }) => {
        url = incoming.url;
        return HttpResponse.json([]);
      }),
    );

    await request("/plants");

    expect(url).not.toContain("a-token");
  });

  it("does not write the token to browser storage", async () => {
    // The refresh token is an httpOnly cookie so that a script cannot read it. Putting the
    // access token in storage would give most of that back.
    setToken("a-token");

    expect(window.localStorage.getItem("token")).toBeNull();
    expect(Object.keys(window.localStorage)).toHaveLength(0);
    expect(Object.keys(window.sessionStorage)).toHaveLength(0);
  });

  it("sends credentials so the refresh cookie travels", async () => {
    let credentials: RequestCredentials | undefined;
    server.use(
      http.post("/api/v1/auth/login", ({ request: incoming }) => {
        credentials = incoming.credentials;
        return HttpResponse.json({ access_token: "x" });
      }),
    );

    await request("/auth/login", { method: "POST", body: { email: "a@b.com" } });

    expect(credentials).toBe("include");
  });

  it("returns nothing for an empty response rather than failing to parse it", async () => {
    server.use(http.delete("/api/v1/plants/1", () => new HttpResponse(null, { status: 204 })));

    await expect(request("/plants/1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("lets FormData set its own content type", async () => {
    // Setting one here would produce a boundary the body does not use, and the server would
    // read an empty upload.
    let contentType: string | null = null;
    const form = new FormData();
    form.append("plant_name", "Basil");
    server.use(
      http.post("/api/v1/runs", ({ request: incoming }) => {
        contentType = incoming.headers.get("Content-Type");
        return HttpResponse.json({ id: "1" });
      }),
    );

    await request("/runs", { method: "POST", body: form });

    expect(contentType).toContain("multipart/form-data");
    expect(contentType).toContain("boundary=");
  });
});

describe("when a refusal arrives", () => {
  it("raises it as a problem the application can branch on", async () => {
    server.use(
      http.get("/api/v1/plants/1", () =>
        HttpResponse.json(
          { type: PROBLEM.notFound, title: "Not found", status: 404 },
          { status: 404 },
        ),
      ),
    );

    await expect(request("/plants/1")).rejects.toSatisfy(
      (error: ApiError) => error.is(PROBLEM.notFound) && error.status === 404,
    );
  });

  it("turns a response that is not a problem into one", async () => {
    // A proxy answering a 502 with HTML. It must not surface as a JSON parse error.
    server.use(
      http.get("/api/v1/plants", () => new HttpResponse("<html>502</html>", { status: 502 })),
    );

    await expect(request("/plants")).rejects.toSatisfy(
      (error: ApiError) => error.is(PROBLEM.internal) && error.status === 502,
    );
  });

  it("shows an internal failure as a sentence rather than its detail", () => {
    const internal = new ApiError({
      type: PROBLEM.internal,
      title: "Internal error",
      status: 500,
      detail: "psycopg: relation does not exist",
    });

    expect(readable(internal)).not.toContain("psycopg");
  });

  it("shows a refusal written for a person as it was written", () => {
    const quota = new ApiError({
      type: PROBLEM.quotaExceeded,
      title: "Monthly allowance reached",
      status: 429,
      detail: "This account has used its runs for the current period.",
    });

    expect(readable(quota)).toBe("This account has used its runs for the current period.");
  });
});

describe("when the token has expired", () => {
  it("renews and retries once, invisibly", async () => {
    setToken("stale");
    let attempts = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => HttpResponse.json({ access_token: "fresh" })),
      http.get("/api/v1/plants", ({ request: incoming }) => {
        attempts += 1;
        if (incoming.headers.get("Authorization") === "Bearer fresh") {
          return HttpResponse.json([{ id: "1" }]);
        }
        return HttpResponse.json(EXPIRED, { status: 401 });
      }),
    );

    await expect(request("/plants")).resolves.toEqual([{ id: "1" }]);
    expect(attempts).toBe(2);
    expect(currentToken()).toBe("fresh");
  });

  it("does not renew a second time for the same request", async () => {
    // Otherwise a server that keeps answering "expired" is an infinite loop.
    setToken("stale");
    let refreshes = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshes += 1;
        return HttpResponse.json({ access_token: "also-stale" });
      }),
      http.get("/api/v1/plants", () => HttpResponse.json(EXPIRED, { status: 401 })),
    );

    await expect(request("/plants")).rejects.toBeInstanceOf(ApiError);
    expect(refreshes).toBe(1);
  });

  it("makes exactly one refresh for several requests failing together", async () => {
    // The one that matters. Each refresh rotates the token, so a second concurrent one
    // presents a token the first has already spent — which the server correctly reads as a
    // stolen token replayed, and ends the session for everybody. A page firing four queries
    // on mount would sign the person out.
    setToken("stale");
    let refreshes = 0;
    server.use(
      http.post("/api/v1/auth/refresh", async () => {
        refreshes += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return HttpResponse.json({ access_token: "fresh" });
      }),
      http.get("/api/v1/plants", ({ request: incoming }) =>
        incoming.headers.get("Authorization") === "Bearer fresh"
          ? HttpResponse.json([])
          : HttpResponse.json(EXPIRED, { status: 401 }),
      ),
    );

    await Promise.all([
      request("/plants"),
      request("/plants"),
      request("/plants"),
      request("/plants"),
    ]);

    expect(refreshes).toBe(1);
  });

  it("starts a fresh renewal for a later expiry", async () => {
    // The shared promise is cleared once it settles. Reusing a resolved one would mean a
    // token that expires an hour later is never renewed.
    setToken("stale");
    let refreshes = 0;
    let issued = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshes += 1;
        issued += 1;
        return HttpResponse.json({ access_token: `fresh-${issued}` });
      }),
      http.get("/api/v1/plants", ({ request: incoming }) =>
        incoming.headers.get("Authorization") === `Bearer fresh-${issued}`
          ? HttpResponse.json([])
          : HttpResponse.json(EXPIRED, { status: 401 }),
      ),
    );

    await request("/plants");
    setToken("stale-again");
    await request("/plants");

    expect(refreshes).toBe(2);
  });
});

describe("when the session has ended", () => {
  it("does not attempt a renewal", async () => {
    let refreshes = 0;
    server.use(
      http.post("/api/v1/auth/refresh", () => {
        refreshes += 1;
        return HttpResponse.json({ access_token: "fresh" });
      }),
      http.get("/api/v1/plants", () => HttpResponse.json(UNAUTHENTICATED, { status: 401 })),
    );

    await expect(request("/plants")).rejects.toBeInstanceOf(ApiError);
    expect(refreshes).toBe(0);
  });

  it("reports a failed renewal so the application can send somebody to sign in", async () => {
    setToken("stale");
    const lost = vi.fn();
    onSessionLost(lost);
    server.use(
      http.post("/api/v1/auth/refresh", () => HttpResponse.json(UNAUTHENTICATED, { status: 401 })),
      http.get("/api/v1/plants", () => HttpResponse.json(EXPIRED, { status: 401 })),
    );

    await expect(request("/plants")).rejects.toBeInstanceOf(ApiError);
    expect(lost).toHaveBeenCalledOnce();
    expect(currentToken()).toBeNull();
  });

  it("forgets the token when a renewal fails", async () => {
    setToken("stale");
    server.use(
      http.post("/api/v1/auth/refresh", () => HttpResponse.json(UNAUTHENTICATED, { status: 401 })),
      http.get("/api/v1/plants", () => HttpResponse.json(EXPIRED, { status: 401 })),
    );

    await expect(request("/plants")).rejects.toBeInstanceOf(ApiError);

    expect(currentToken()).toBeNull();
  });
});
