/**
 * The accessibility matcher, declared for the compiler.
 *
 * `expect.extend` adds it at runtime; the package ships its declaration against the `Vi`
 * global namespace, which Vitest 3 no longer merges into `expect`. Without this the build
 * fails while the tests pass — the sort of split that only surfaces in CI.
 */

import "vitest";
import type { AxeMatchers } from "vitest-axe/matchers";

declare module "vitest" {
  interface Assertion extends AxeMatchers {}
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
