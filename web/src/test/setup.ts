import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./server";

// The API is mocked at the network boundary rather than by replacing the client. What is
// under test is then the code that will run in a browser, including its fetch wrapper and
// its error handling — replacing the client would test everything except the part most
// likely to be wrong.
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
