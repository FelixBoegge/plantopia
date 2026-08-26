/**
 * Parsing a server-sent event stream.
 *
 * Written against fabricated chunks rather than a server, because the case worth proving is
 * the one a server almost never produces on demand: a frame split across two reads.
 */

import { describe, expect, it } from "vitest";

import { readEvents } from "@/api/events";

/** What the server sends between lines. Built rather than typed, so it survives a formatter. */
const CRLF = String.fromCharCode(13) + String.fromCharCode(10);

function streamOf(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>) {
  const events = [];
  for await (const event of readEvents(stream)) events.push(event);
  return events;
}

describe("reading a stream", () => {
  it("reads one event", async () => {
    const events = await collect(
      streamOf('id: 1\nevent: step\ndata: {"step":"checking"}\n\n'),
    );

    expect(events).toEqual([
      { id: "1", event: "step", data: { step: "checking" } },
    ]);
  });

  it("reads several in order", async () => {
    const events = await collect(
      streamOf(
        'id: 1\nevent: step\ndata: {"n":1}\n\nid: 2\nevent: step\ndata: {"n":2}\n\n',
      ),
    );

    expect(events.map((event) => event.id)).toEqual(["1", "2"]);
  });

  it("reassembles a frame split across two reads", async () => {
    // The case a server almost never produces on demand, and the one that would otherwise
    // drop half an event with no way to reproduce it afterwards.
    const events = await collect(
      streamOf("id: 1\nevent: st", 'ep\ndata: {"step":"che', 'cking"}\n\n'),
    );

    expect(events).toEqual([
      { id: "1", event: "step", data: { step: "checking" } },
    ]);
  });

  it("ignores keep-alive comments", async () => {
    // What an idle stream sends. A client that rendered them would show a run doing
    // something every fifteen seconds for ever.
    const events = await collect(
      streamOf(": ping - 2026-01-01\n\nid: 1\nevent: step\ndata: {}\n\n"),
    );

    expect(events).toHaveLength(1);
  });

  it("keeps text that is not JSON as text", async () => {
    const events = await collect(streamOf("event: note\ndata: hello\n\n"));

    expect(events[0]?.data).toBe("hello");
  });

  it("joins a data field split across several lines", async () => {
    const events = await collect(
      streamOf("event: note\ndata: one\ndata: two\n\n"),
    );

    expect(events[0]?.data).toBe("one\ntwo");
  });

  it("yields nothing for a frame carrying no data", async () => {
    const events = await collect(streamOf("event: note\n\n"));

    expect(events).toEqual([]);
  });

  it("stops when the stream ends", async () => {
    const events = await collect(
      streamOf('event: done\ndata: {"end":true}\n\n'),
    );

    expect(events).toHaveLength(1);
  });
});

describe("line endings", () => {
  it("reads the framing this server actually sends", async () => {
    // Captured from the running API, not written by hand. Every other fixture in this
    // file uses bare line feeds because that is what I assumed — and the parser agreed
    // with the assumption rather than with the server, so it yielded nothing at all,
    // for every event, and every test here passed. Found in a browser.
    const crlf =
      "id: 1" +
      CRLF +
      "event: step" +
      CRLF +
      'data: {"step": "checking"}' +
      CRLF +
      CRLF;

    const events = await collect(streamOf(crlf));

    expect(events).toEqual([
      { id: "1", event: "step", data: { step: "checking" } },
    ]);
  });

  it("reads a bare carriage return too", async () => {
    // Permitted by the specification, and the cheapest of the three to get wrong.
    const cr = String.fromCharCode(13);
    const events = await collect(
      streamOf("event: note" + cr + "data: hello" + cr + cr),
    );

    expect(events[0]?.data).toBe("hello");
  });

  it("reassembles a CRLF frame split mid-ending", async () => {
    // The nastiest version: the boundary itself straddles two reads.
    const events = await collect(
      streamOf(
        "event: note" + CRLF + "data: hi" + CRLF.slice(0, 1),
        CRLF.slice(1) + CRLF,
      ),
    );

    expect(events[0]?.data).toBe("hi");
  });
});
