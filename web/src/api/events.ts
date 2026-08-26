/**
 * Reading a server-sent event stream with `fetch`.
 *
 * `EventSource` cannot set an `Authorization` header, and every workaround puts the access
 * token in the query string — where it lands in the server's access log, the browser's
 * history, and the `Referer` of whatever the page loads next, for a credential deliberately
 * never written to storage. So the body is read and parsed here instead: about sixty lines,
 * and `Last-Event-ID` on a reconnect is then a request header like any other.
 */

export interface StreamEvent {
  id: string | null;
  event: string;
  data: unknown;
}

/**
 * Yield each event from a response body as it arrives.
 *
 * Frames are separated by a blank line and may straddle a chunk boundary, so a buffer is
 * carried between reads. Splitting on the boundary alone would drop half of any event
 * unlucky enough to arrive in two pieces — rare, and impossible to reproduce afterwards.
 *
 * **Line endings are normalised first**, by `normalise` below. Skipping that is not a
 * cosmetic matter: it yields nothing at all, for every event, silently. See its comment.
 */
export async function* readEvents(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<StreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      // Normalised on arrival rather than at each split, so every comparison downstream
      // sees one form.
      buffer += normalise(decoder.decode(value, { stream: true }));

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const parsed = parseFrame(frame);
        if (parsed) yield parsed;
        boundary = buffer.indexOf("\n\n");
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let id: string | null = null;
  let event = "message";
  const data: string[] = [];

  for (const line of frame.split("\n")) {
    // A comment. This is what a keep-alive looks like, and it is not an event.
    if (line.startsWith(":")) continue;

    const separator = line.indexOf(":");
    const field = separator === -1 ? line : line.slice(0, separator);
    const value =
      separator === -1 ? "" : line.slice(separator + 1).replace(/^ /, "");

    if (field === "id") id = value;
    else if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }

  if (data.length === 0) return null;

  const joined = data.join("\n");
  try {
    return { id, event, data: JSON.parse(joined) };
  } catch {
    return { id, event, data: joined };
  }
}

/**
 * One form of line ending.
 *
 * The specification permits CRLF, LF or a bare CR, and this project's server sends CRLF.
 * A parser that split on two line feeds finds no boundary at all in CRLF CRLF and yields
 * nothing — silently, and for every event.
 */
function normalise(chunk: string): string {
  return chunk.replace(/\r\n?/g, "\n");
}
