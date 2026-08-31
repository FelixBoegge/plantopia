## Context

See `proposal.md` — Why. What shapes the approach is where the existing pieces sit and what
they already destroy.

`core/images.py:store_upload` validates an upload, then calls `upright_bytes`, which applies
the declared orientation with `ImageOps.exif_transpose` and re-saves. That re-save clears the
orientation tag on purpose — so nothing turns the image a second time — and takes an
unpredictable amount of the rest of the metadata block with it. Anything to be read from a
photograph has to be read before that line.

`Observation` carries `created_at` and nothing about the photograph. The weather window is
anchored on the observation's date, and `tools/weather.py` takes a *place name*, forward
geocodes it through Open-Meteo, and summarises three weeks of history. So a position read
from a photograph has to become something that tool can use.

`tools/weather.py` is also the pattern for a keyless external service: no credential, returns
`None` on every failure, and the diagnosis widens rather than stopping. `tools/plantnet.py`
is the pattern for a credentialled one. Reverse geocoding is the first kind, not the second.

## Goals / Non-Goals

**Goals:**

- An observation dated when the photograph was taken, so the weather window covers the days
  the plant actually had.
- A position good enough for weather and useless for finding somebody's house.
- Degradation that is the ordinary path rather than a fallback, because most photographs
  carry nothing.
- Everything detected visible and correctable before a run costs anybody money.

**Non-Goals:**

- Any use of the finer data this makes possible. Hourly windows and forecasts are
  `add-granular-weather`.
- Metadata from any source but the photograph. No IP lookup, no browser location prompt.
- Camera, lens, or any other metadata a photograph carries. Read what is used, ignore the
  rest.

## Decisions

### Reading happens in `store_upload`, before `upright_bytes`, and returns with the reference

The read is one line above the line that would destroy it. Putting it anywhere else — a
second pass over the stored bytes, a separate call from the router — means either reading a
file that no longer has the data, or reading the same file twice for no reason.

So `store_upload` returns what it read alongside the `ImageRef`. That changes its signature,
which is deliberate: the ordering constraint becomes a property of the one function that
owns both operations, rather than a rule two callers have to remember.

Rejected: reading in the router before calling `store_upload`. It would work and it would put
the constraint in the wrong place — the next caller of `store_upload` would have to know to
do the same thing first, and would not.

### The coarsening is arithmetic, not a service, and happens before anything is written

Rounding to one decimal degree is a `round(value, 1)`. It happens in the same function that
reads the fix, and the precise value exists only as a local. Nothing downstream is given the
opportunity to store it, log it, or send it anywhere, because nothing downstream is ever
handed it.

One decimal degree is about eleven kilometres of latitude, less of longitude away from the
equator. That is the resolution weather is worth having at, and it is a large enough area
that it identifies a district rather than an address.

### Reverse geocoding is keyless, cached, and allowed to fail

Nominatim, OpenStreetMap's own service: no credential, so the path works on a fresh clone
rather than being dark until somebody registers — which is what `U1` records about the
web-search path, and what this change is in a position to avoid.

Its terms are the cost: a descriptive `User-Agent` identifying the application, at most one
request a second, and attribution for the data. All three are requirements rather than
preferences, and the first is the one most often ignored.

Two consequences for the design. The base URL and the user agent are configuration, so a
deployment can point at its own instance rather than a shared free service. And results are
cached on the coarsened position — which is a small, naturally repetitive key, since every
upload from one garden rounds to the same place — so a person diagnosing the same plant
weekly makes one lookup, not one a week.

**It runs while somebody is waiting**, which nothing else external here does; every other
service is inside a ninety-second run. A short timeout, and a failure that produces
coordinates rather than an error.

### The capture date is validated, and the earliest wins

A declared date in the future is a wrong clock. A date before digital photography is a wrong
clock the other way. Both are ignored rather than believed, because the failure they cause is
a weather window somewhere the plant has never been in time.

Where several photographs disagree, the earliest is used: an upload is one observation, and
the earliest is the one whose weather window covers all of them.

### The location moves from the upload form to the pause, as a prefilled question

Nobody is asked where the plant is before the run starts. The photograph usually knows, and
asking somebody to type what the file already says is asking them to do the machine's work.
Where it does not know, the question is put at the pause the run already makes — one
interruption rather than two.

It rides the existing question mechanism rather than becoming a block of its own, which the
identification chooser needed. A location genuinely *is* a clarifying question: a key, a
sentence, a text answer. What it needs that a question could not previously express is a
prefilled answer and a requirement, so `Question` gains `prefill` and `required` — two fields
that are generally meaningful rather than special cases for this one.

Prefilled *as the answer* rather than shown as a suggestion beside an empty box. It is what
will be used unless somebody says otherwise, and a suggestion asks the common case to do work
while a filled field asks only the uncommon one.

`required` is true only outdoors. Weather frequently is the diagnosis for an outdoor plant, so
a missing place costs a real part of the answer; indoors the connection is weak enough that
demanding one would be demanding it for nothing. The check lives on the server as well as in
the form, because a form is a convenience and not a guarantee.

### What is detected is returned to the client, not applied on the server

The upload endpoint answers with what it read. The wizard shows it, lets it be edited, and
sends back whatever the person left — through the fields that already exist for a date and a
place, rather than through new ones that mean "detected".

That keeps the server with one source of truth for each value, and it keeps the correction
where the person is. The alternative — the server applying what it detected and the client
overriding it afterwards — means two values for the same field and a rule about which wins.

## Risks / Trade-offs

- **A third party on the path somebody is waiting on** → short timeout, cached, and a failure
  that costs a place name rather than an upload. The upload succeeds and the coordinates are
  shown instead.
- **Nominatim's rate limit is a shared resource, and this project has no scheduler** → the
  cache is what keeps a normal use pattern well inside one request per second; a deployment
  that outgrows that points the configuration at its own instance, which the terms expect.
- **Metadata is a privacy surface, and reading it is an active choice** → the precise fix is
  discarded in the function that reads it, before any store or log sees it, and everything
  detected is shown to the person before a run starts. A database that never holds a home
  address cannot leak one.
- **A forwarded photograph carries somebody else's date and place** → which is exactly why
  detection is shown and editable rather than applied. It cannot be distinguished
  automatically, and pretending otherwise would produce confident wrong answers.
- **The ordering constraint is one line and easy to reverse** → a test that puts a photograph
  with known metadata through the real `store_upload` and asserts the metadata survived. It
  fails if the two calls are ever swapped.
- **The evaluation harness must not move** → golden cases carry no photographs with metadata,
  so nothing here is on its path. Verified by running it.

## Migration Plan

Additive. One migration adds a nullable captured-at and a nullable coarse position to
`observations`; existing rows keep null, which means "not known", which is true of every
observation made before this.

Order, which is also the order the risk retires:

1. Reading metadata from bytes, with the coarsening, and the ordering test — no service, no
   schema.
2. The reverse-geocoding adapter, keyless and degrading, verified against the live service
   before its tests are written from it.
3. The observation's new columns and the weather anchoring.
4. The upload response and the wizard's detected fields.

**Rollback** is the columns going unread: with nothing detected, every path here is the path
that exists today, which is also what happens for a photograph that carries nothing.

## Open Questions

- **Whether the detected capture date should be correctable, and where.** The place is now a
  prefilled answer at the pause, and the same argument — a forwarded photograph carries
  somebody else's — applies to the date. But a date wants a date control rather than a text
  answer, so it does not ride the question mechanism, and it is not obvious it earns a
  surface of its own. Deferred to the wizard work, where the alternatives can be looked at
  rather than imagined.
- **Whether a coarse position should replace a typed town when both exist.** Today the typed
  one wins by being what the person left in the field. That is probably right and it is not
  obviously right, and it can be settled when `add-granular-weather` makes the position worth
  more than the name.
