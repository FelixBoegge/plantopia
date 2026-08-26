import { setupServer } from "msw/node";

// No default handlers. `onUnhandledRequest: "error"` above means a test that reaches an
// endpoint it did not declare fails loudly, rather than passing against a stub nobody
// remembers writing.
export const server = setupServer();
