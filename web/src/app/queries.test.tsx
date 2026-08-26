/**
 * Server state, and what happens when a client changes some of it.
 *
 * The property under test is that a screen reflects a change without a manual reload —
 * which in a cache means the mutation invalidated the right key. A key typed inline at a
 * call site is a key that will one day disagree with the one a mutation invalidates, and
 * the symptom is stale data nobody attributes to this.
 */

import {
  QueryClientProvider,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { render as rtlRender, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { request } from "@/api/client";
import { makeQueryClient } from "@/app/QueryProvider";
import { keys } from "@/app/queries";
import { ApiError, PROBLEM } from "@/api/problems";
import { server } from "@/test/server";

function withClient(ui: React.ReactElement) {
  const client = makeQueryClient();
  return rtlRender(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

function Plants() {
  const client = useQueryClient();
  const { data } = useQuery({
    queryKey: keys.plants,
    queryFn: () => request<{ name: string }[]>("/plants"),
  });
  const rename = useMutation({
    mutationFn: () =>
      request("/plants/1", { method: "PATCH", body: { name: "Renamed" } }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.plants }),
  });

  return (
    <div>
      <ul>
        {data?.map((plant) => (
          <li key={plant.name}>{plant.name}</li>
        ))}
      </ul>
      <button onClick={() => rename.mutate()}>Rename</button>
    </div>
  );
}

describe("a mutation", () => {
  it("makes the screen reflect what it changed", async () => {
    let name = "Kitchen basil";
    server.use(
      http.get("/api/v1/plants", () => HttpResponse.json([{ name }])),
      http.patch("/api/v1/plants/1", () => {
        name = "Renamed";
        return new HttpResponse(null, { status: 204 });
      }),
    );

    withClient(<Plants />);
    expect(await screen.findByText("Kitchen basil")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Rename" }));

    expect(await screen.findByText("Renamed")).toBeInTheDocument();
  });
});

describe("a query that is refused", () => {
  it("does not retry a refusal that will not change", async () => {
    // Three round trips to arrive at the same sentence, and for a rate limit, three that
    // make the thing it is complaining about worse.
    let attempts = 0;
    server.use(
      http.get("/api/v1/plants", () => {
        attempts += 1;
        return HttpResponse.json(
          {
            type: PROBLEM.quotaExceeded,
            title: "Allowance reached",
            status: 429,
          },
          { status: 429 },
        );
      }),
    );

    function Screen() {
      const { error } = useQuery({
        queryKey: keys.plants,
        queryFn: () => request("/plants"),
      });
      return <p>{error instanceof ApiError ? "refused" : "waiting"}</p>;
    }

    withClient(<Screen />);

    await waitFor(() =>
      expect(screen.getByText("refused")).toBeInTheDocument(),
    );
    expect(attempts).toBe(1);
  });

  it("does retry something that might be temporary", async () => {
    let attempts = 0;
    server.use(
      http.get("/api/v1/plants", () => {
        attempts += 1;
        return attempts < 2
          ? new HttpResponse(null, { status: 502 })
          : HttpResponse.json([{ name: "Basil" }]);
      }),
    );

    function Screen() {
      const { data } = useQuery({
        queryKey: keys.plants,
        queryFn: () => request<{ name: string }[]>("/plants"),
      });
      return <p>{data?.[0]?.name ?? "waiting"}</p>;
    }

    withClient(<Screen />);

    // The retry backs off about a second before it happens, which is the right delay for a
    // real network and longer than the default wait here.
    expect(
      await screen.findByText("Basil", {}, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(attempts).toBe(2);
  });
});

describe("the keys", () => {
  it("nest a plant's things under the plant", () => {
    // So that invalidating a plant invalidates what belongs to it, rather than each screen
    // having to remember every key it might have affected.
    expect(keys.messages("1")[0]).toBe(keys.plants[0]);
    expect(keys.plant("1")[0]).toBe(keys.plants[0]);
  });
});
