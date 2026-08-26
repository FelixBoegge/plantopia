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

// jsdom implements neither of these. Photographs are fetched with the session and handed to
// `<img>` as a blob URL — there is no other way to send an Authorization header for an
// image — so without them every test touching a photograph fails for a reason that has
// nothing to do with the code.
//
// Counted rather than stubbed blind: a test can assert that what it created was also
// released, which is how a leak of every photograph somebody scrolls past would be caught.
let objectUrls = 0;
if (!URL.createObjectURL) {
  URL.createObjectURL = () => `blob:test/${(objectUrls += 1)}`;
  URL.revokeObjectURL = () => {};
}
