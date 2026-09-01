# Implementation tasks

Ordered so the free mechanism is proven before the one that costs a model call, and so the
property that must not change — the stored transcript — is pinned before either lands.

## 1. What must not change

- [x] 1.1 Pin that the stored transcript is written before and after the agent runs and never rewritten; verify a test asserts the recorded messages are identical after a turn that would be condensed.
- [x] 1.2 Pin that an export carries the full conversation regardless of condensation; verify a test asserts every message reaches the archive.
- [x] 1.3 Pin that what a reply consulted stays recorded against it; verify a test asserts the tool calls on an older message survive.

## 2. Dropping stale tool output

- [x] 2.1 Add the threshold to `Settings` with the reasoning for its default, and name it in `.env.example`; verify the settings test covers it.
- [x] 2.2 Wire `ContextEditingMiddleware` with `ClearToolUsesEdit` into the chat agent; verify a test asserts a short conversation is passed through untouched.
- [x] 2.3 Drop older tool output past the threshold, keeping the most recent results; verify a test asserts an old result is absent from what reaches the model and a recent one is present.
- [x] 2.4 Confirm the model can tell something was cleared rather than that nothing happened; verify a test asserts the placeholder is present.
- [x] 2.5 Confirm what reaches the model stops growing; verify a test asserts the size at twenty turns is bounded rather than proportional.

## 3. Condensing the conversation

- [x] 3.1 Add the higher threshold to `Settings` with its reasoning, and name it in `.env.example`; verify the settings test covers it.
- [x] 3.2 Wire `SummarizationMiddleware` on the cheap model tier; verify a test asserts the reasoning tier is not used for it.
- [x] 3.3 Fire it only after tool clearing was insufficient; verify a test asserts a conversation brought under the limit by clearing alone is not summarised.
- [x] 3.4 Keep the most recent exchanges verbatim; verify a test asserts the last turns are word for word.
- [x] 3.5 Confirm a follow-up still reflects what was established earlier; verify a test asserts the summary reaches the model.

## 4. Proving it, and closing

- [x] 4.1 Measure what reaches the model across a long scripted conversation, before and after; verify the numbers and record them.
- [x] 4.2 Add a browser flow holding a conversation long enough to be condensed; verify the transcript still reads in full and a follow-up is answered.
- [x] 4.3 Update the README: what is sent to the model, what is kept, and that the transcript is untouched; verify every command runs as written on a clean clone.
- [x] 4.4 Correct the README's standing claim that chat context grows without bound; verify nothing else in that section contradicts it.
- [x] 4.5 Record what this leaves undone — `M17`, the placeholder wording, the summariser not knowing the plant; verify identifiers and dates against the file's conventions.
- [x] 4.6 Run `openspec validate add-chat-context-limits --strict`, the Python suite, the frontend suite, Playwright and ruff; verify all five are clean.
