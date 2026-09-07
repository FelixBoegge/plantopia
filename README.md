# 🌿 Plantopia

An AI plant-health agent. Upload photos of an ailing plant; Plantopia identifies the
species, asks the questions a photograph cannot answer, and returns a ranked
differential diagnosis with an integrated-pest-management treatment plan.

## Why this exists

Plant symptoms are many-to-one ambiguous. Yellowing leaves alone are consistent with
overwatering, underwatering, nitrogen deficiency, insufficient light, root rot, spider
mites, natural senescence and transplant shock. Existing plant apps do one-shot image
classification — they ask nothing, cite nothing, and are confidently wrong often
enough to kill plants.

The information that resolves the ambiguity is not in the photograph. It is watering
cadence, drainage, light hours and recent weather. So Plantopia asks before it
answers, the way a clinician takes a history.

## What it does

- **Rejects non-plant uploads** before anything else runs
- **Identifies the species** and says how confident it is
- **Extracts symptoms with their position** on the plant — interveinal yellowing and
  leaf-tip yellowing have different causes
- **Pauses to ask you two to four questions** chosen for your specific case
- **Reasons before it retrieves.** It shortlists the disorders worth reading about *by
  name*, then fetches those documents from a curated corpus of 43 rather than hoping
  similarity search ranks them — which took the correct document from reaching the
  model in 23 of 28 golden cases to 28 of 28
- **Escalates to web search** only when the corpus falls short
- **Fetches recent weather** for outdoor plants, day by day with dates — a late frost is
  often the diagnosis, and "two frost days in the last three weeks" cannot say whether they
  were last night or a fortnight ago
- **Returns a differential**, not a single answer: two or three ranked candidates,
  each with supporting evidence, contradicting evidence, and a test you can run in
  five minutes to tell them apart
- **Builds a dated treatment plan**, least invasive first
- **Warns about contagion** if the problem can spread to your other plants
- **Says when it cannot tell**, instead of guessing
- **Remembers every plant.** The My Plants grid shows each plant's own photograph, a
  health badge and its pending roadmap steps; the Plant detail page shows its full
  diagnosis history. A plant is named from the identification the agent made, which you
  can confirm or overwrite.
- **Learns about you, not just your plants.** Durable facts extracted from diagnoses
  and chat — *"tends to overwater"*, *"lives in Berlin"* — are injected as priors into
  later runs. The **What we've learned** page lists each one with its source, confidence
  and last-confirmed date, and forgets any of them on one click — a record of inferences a
  system holds about a person belongs somewhere reachable, not folded under a grid of
  plants.
- **Re-checks progress.** Upload a new photo of a known plant and get a verdict —
  improving, static, worsening, or a new problem — against the prior diagnosis,
  without repeating the clarifying questions: roadmap-step completion already
  answers what was tried.
- **Asks for feedback** once you've actually tried a step, not before.
- **Answers follow-up questions in a chat scoped to one plant**, naming the sources each
  reply consulted on the reply itself, and can flag when a described symptom is
  different enough to warrant a fresh look.

## Getting started

Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and Docker.

```bash
git clone <your-repo-url>
cd plantopia
uv sync

docker compose up -d db          # PostgreSQL 17 with pgvector, on port 5433
uv run alembic upgrade head      # create the schema

cp .env.example .env
# add your PLANTOPIA_OPENROUTER_API_KEY and a PLANTOPIA_JWT_SECRET of 32+ characters

uv run uvicorn api.main:create_app --factory --reload --port 8000
```

And the web client, in a second terminal:

```bash
cd web
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api` to port 8000, so the browser sees one origin — which is what lets the
refresh cookie's `SameSite=Strict` be honoured. A frontend on a different origin would not
receive it at all.

The interactive API documentation is at `http://localhost:8000/api/v1/docs`.

**There is no key with a default.** `PLANTOPIA_JWT_SECRET` has none, and the application
refuses to start without it. A generated default would work perfectly in development and
sign everybody out on every restart in production, which is the kind of default that is
discovered by its symptom.

### Getting an account

Registration is open and every account starts unverified; nothing owner-scoped is reachable
until the address is proven.

**No confirmation email will arrive, and nothing is wrong when it does not.** Which mailer
runs is decided by whether a provider is configured rather than by a flag somebody has to
remember, and none is configured by default — so `core/mail.py` falls back to a mailer that
writes the message to the application log instead of sending it. A checkout that has never
been given a key cannot mail a real person by accident. Registering with your own address
is safe: nothing leaves the machine.

To activate an account from the web client, register at `http://localhost:5173/register` as
you normally would. The screen will tell you to check your inbox — ignore it, and look at
the terminal running uvicorn, where the whole message is waiting:

```
INFO core.mail: email not sent (no provider configured); to=you@example.com subject=Confirm your Plantopia address
Welcome to Plantopia.

Confirm this address to finish setting up your account:

http://localhost:5173/verify-email?token=Ilx0YWtlIHRoZSBvbmUgaW4geW91ciBvd24gbG9n
```

Open that link in the same browser. It proves the address, and the account can sign in
immediately afterwards. The link is good for 24 hours; registering again issues a new one.

Piping the server to a file on the way past makes the message easy to find once the terminal
has scrolled:

```bash
uv run uvicorn api.main:create_app --factory --reload --port 8000 | tee api.log
grep -A6 "Confirm your Plantopia address" api.log
```

Setting `PLANTOPIA_RESEND_API_KEY` switches to real delivery, with the caveat that Resend's
default sender only reaches the address that owns the Resend account — mailing anyone else
needs a verified domain. Password reset works the same way and lands in the same log.

The same three steps over the API, for anyone working without the web client:

```bash
curl -X POST localhost:8000/api/v1/auth/register   -H 'content-type: application/json'   -d '{"email":"you@example.com","password":"at-least-twelve-characters","accepted_privacy_notice":true}'
```

The token to spend is the one at the end of the link in the log:

```bash
curl -X POST localhost:8000/api/v1/auth/verify   -H 'content-type: application/json' -d '{"token":"<from the log>"}'

curl -X POST localhost:8000/api/v1/auth/login   -H 'content-type: application/json'   -d '{"email":"you@example.com","password":"at-least-twelve-characters"}'
```

Sign-in returns an access token in the body and sets the refresh token as an httpOnly
cookie. Send the access token as `Authorization: Bearer <token>` on every owner-scoped
request; when it expires — fifteen minutes — `POST /api/v1/auth/refresh` issues another
from the cookie.

**Refresh is never retried.** Each use rotates the token, so presenting a spent one is
indistinguishable from a stolen one being used, and is treated as one: the session ends
and the account signs in again. A client whose refresh fails sends the person to sign in
rather than trying again.

### Diagnosing a plant

A diagnosis takes about ninety seconds and stops part-way to ask you something, so it is
not a request — it is a run you start and then watch.

```bash
TOKEN=<the access token from signing in>

curl -X POST localhost:8000/api/v1/runs   -H "Authorization: Bearer $TOKEN"   -F location_kind=indoor -F photographs=@leaf.jpg
```

Photographs and whether it lives indoors or outdoors, and that is all that is required. The
plant is named by whatever the identification finds and can be renamed afterwards; where it
is and when the photograph was taken are asked at the pause, already filled in with whatever
the file knew. `stated_species` and `plant_name` are accepted here if you have them.

That answers immediately with a run and its status. Follow it:

```bash
curl -N localhost:8000/api/v1/runs/<run-id>/events -H "Authorization: Bearer $TOKEN"
```

Events name what is happening — "Identifying the species", "Consulting the disorder
reference" — and part-way through, one carries the questions the agent needs answered.
Answer them and the same stream continues:

```bash
curl -X POST localhost:8000/api/v1/runs/<run-id>/answers   -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json'   -d '{"answers":{"watering":"every other day","drainage":"No drainage holes","captured_at":"2026-08-31","location":"Frankfurt"}}'
```

Each question says whether it is `required` and what it is already filled in with. A
submission that leaves a required one empty is refused with a 400 naming the keys — the
capture date always, and the location for an outdoor plant.

That same event can carry an `identification` block, and the answer can carry a `species`
— see [Two opinions on what the plant is](#two-opinions-on-what-the-plant-is).

`GET /api/v1/runs/{id}` reports the status at any time, and `DELETE` abandons a run — the
step already running finishes, so cancelling during a model call still pays for that call.

**Reconnecting costs nothing.** Send the last event's id back as `Last-Event-ID` and the
stream resumes from there. A closed laptop or a flaky tunnel loses the view of a run, not
the run.

Chat works the same way if you want to watch it: `POST /plants/{id}/messages` returns the
whole reply, and `POST /plants/{id}/messages/stream` delivers it as it is produced, saying
which source the agent is consulting. Both leave the same transcript — the streaming one is
the same call with somebody watching.

**One process.** The run pool, the event bus and the rate limiter all live in the API
process, so this does not scale horizontally as it stands. `M28` in
`docs/known-limitations.md` says what has to be substituted first.

### Two opinions on what the plant is

Everything downstream rests on the species: the same drooping leaves mean different things
on a peace lily and on a cactus. So two methods identify it, and **neither is told what you
think it is** — not the species you typed, not the name you gave the plant. A model told the
answer tends to return the answer, and then agreement is one claim counted twice rather than
two methods corroborating each other.

- A general-purpose vision model reads the photographs, and reports which part of the plant
  each one shows.
- [Pl@ntNet](https://my.plantnet.org)'s classifier reads the same photographs, with those
  organs as a hint — it is markedly more accurate given them.

You may also type a species when starting a run. It is optional and stays optional: most
people asking what is wrong with a plant do not know what it is, which is frequently why
they are asking.

**If everything agrees, nothing is asked.** Where the two methods and anything you typed
name the same plant, the run proceeds — being asked to confirm what nobody disputed is an
interruption, not a choice. Where they disagree, the pause that already exists for the
clarifying questions also asks which one is right. Each answer says how it was reached
("read from your photo", "matched against a plant database") and how sure it is, in words.
Choosing is optional; leaving it alone proceeds on the leading candidate.

What leads: **what you typed, then what both methods agree on, then the vision model's.**
Never the highest confidence across methods — the two report on scales that were never
calibrated against each other, so comparing one's 0.71 with the other's 0.62 would be
arithmetic on incomparable quantities.

`GET /api/v1/diagnoses/{id}` reports `species_method` and `species_confirmed`, so a wrong
diagnosis can be attributed afterwards: bad reasoning about the right plant, or good
reasoning about the wrong one. `null` means unknown, which is what every diagnosis made
before this existed honestly says about itself.

**Set `PLANTOPIA_PLANTNET_API_KEY` to turn the second opinion on.** Free tier: 500
identifications a day, commercial use permitted, European hosting; register at
[my.plantnet.org](https://my.plantnet.org). Without it, a diagnosis runs on the vision
model's identification alone, exactly as it did before the service existed — no choice is
offered and nothing in the interface mentions it.

**Showing a Pl@ntNet result obliges you to credit Pl@ntNet on the same surface.** That is a
term of the free tier rather than a courtesy, and the interface does it for you: the credit
is rendered by the component that renders the candidate, so a screen that shows one cannot
omit it.

### What a photograph tells us, and what it is not allowed to keep

A photograph already knows two things worth having, and one of them was silently wrong
before this existed.

**When it was taken.** An observation used to be dated by its upload, and the weather window
anchored on that date — so somebody who photographed a plant on Sunday and got round to
uploading it on Wednesday was diagnosed against three days of weather the plant never had.
Nothing noticed, because the two dates are indistinguishable once the file is stored. The
capture date is now read from the file and shown at the pause in a field that always holds a
date: what the camera recorded, or today. It is required, because an empty date is not a
smaller answer than a wrong one — it is no weather at all.

**Roughly where.** A GPS fix is **coarsened to about eleven kilometres before anything is
written down**, and the precise position never leaves the function that read it. Weather at
that distance is indistinguishable from weather at the doorstep, which is the only thing the
position is for, and eleven kilometres describes a district rather than an address.

**The photograph itself is stripped too.** Coarsening the number in the database does nothing
about the precise fix still inside the uploaded file, and that file is stored as well. The
metadata is cut out of the bytes — not re-encoded around, so the picture the model sees is
the picture you uploaded, to the hash — and an upload whose position cannot be removed is
refused rather than stored.

Nothing else is read. Cameras write lens, exposure and serial numbers; none of it is used, so
none of it is looked at.

**And a photograph can be too old to trust.** A plant changes. A three-week-old photograph
shows a plant that no longer exists, and a diagnosis of it is a diagnosis of the past
presented as advice about the present — confident, detailed, and about something that has
since recovered or got considerably worse. Past a threshold (seven days by default,
`PLANTOPIA_STALE_PHOTOGRAPH_DAYS`) the age is said out loud twice: at the pause, where you
can still go and take another one before paying for a diagnosis, and in the diagnosis itself,
which is told the age and instructed to say so. The run always completes either way —
somebody whose plant died last week and who has only last week's photograph is exactly who
needs an answer. The age is judged by the date left in the field, not the one the camera
recorded, so correcting a wrong camera clock corrects the verdict.

### Your data, and getting rid of it

Registration records what you agreed to. The account screen is where you can act on it.

**Download everything.** One file — a ZIP holding a JSON document and every photograph you
uploaded. The JSON opens in anything; records carry the *name* of what they point at as well
as its identifier, so a diagnosis says which plant it was about rather than only
`plant_id: 01a0…`. It contains your plants, observations, diagnoses, treatment plans and
their outcomes, conversations, the facts Plantopia has inferred about you, and what your runs
have cost. It contains no password hash and no token.

**Delete the account.** Everything goes: every table that reaches you, the stored
photographs, and the conversation checkpoints that live outside the application's own schema.
It asks for your password and for the phrase `delete my account`, typed out — both checked on
the server, because a confirmation only the browser enforces is one a script does not have to
type. There is no undo.

What "everything" means is **proven against the schema rather than asserted**: a test creates
an account with a row in every owned table, deletes it, then walks `Base.metadata` and
requires each table to be empty or explicitly classified as reference data. A table added
later has to be classified before its own tests pass, so it cannot be quietly missed. The
disorder corpus and the researched species care baselines survive — they describe plants, not
people, and deleting your account should not degrade the system for everybody else.

One honest limit: an access token already issued keeps parsing until it expires, up to
fifteen minutes. Refresh tokens are revoked, so the session cannot be extended, and there is
nothing of yours left for that token to read. Closing the window entirely would mean a
database read on every request in the application; `U18` records the trade.

### A plant's history, in one sequence

Each diagnosis is a verdict on one moment. The question you actually have after the second or
third is the one no single verdict answers: **is this getting better?**

The plant page carries a timeline for that — observations, diagnoses and treatment steps in
one order, newest first, with the weather drawn underneath where it was recorded:

- **What you saw** — each observation with its photographs, dated by when the photograph was
  *taken* rather than when it was uploaded. Those differ for anybody who does not upload
  immediately, and a history ordered by upload puts events in an order the plant never
  experienced. Where a photograph carried no capture date, the timeline says it is showing
  the upload date rather than quietly presenting one as the other.
- **What it was judged to be** — each diagnosis and its leading candidate, with the full
  differential one click away.
- **What you did** — treatment steps that were completed or skipped. Steps you have not done
  yet stay in the plan below, which is where you tick them; showing the same item in both
  places, where only one of them can be acted on, would be worse than showing it once.
- **What the agent flagged** — when a conversation described symptoms different enough to
  warrant a fresh look, that is an event in the plant's history, with the reason it gave.
- **What the weather was doing** — the recorded daily series for that observation, as a small
  chart with a sentence naming the range and the notable days.

The chart is drawn by hand rather than by a charting library, and it is **not** the content:
the same series is also a table, present and read by a screen reader, because colour is never
the only carrier of meaning here. If the drawing fails you still have the numbers.

Nothing is invented. An observation from before capture dates and weather were recorded shows
what it has and says nothing about what it does not — no zero temperature, no epoch date. The
seven-day forecast stored alongside each series is deliberately not drawn: it was the week
ahead of the run, which is the past by the time anybody reads a history.

### What "this plant wants" is based on

A diagnosis needs a baseline to answer "is this normal for this plant?" — a fern dropping
fronds in dry air is a different situation from a succulent doing the same thing. There are
18 hand-written profiles, and Pl@ntNet can name upwards of 50,000 species, so sharper
identification *widened* that gap rather than closing it: a run that identifies *Ocimum
africanum* precisely and then has no idea what it wants is worse off than one that guessed
"basil".

So there are three tiers, in order:

1. **Hand-written**, in `tools/care_profiles.py`. Always wins, and is never shadowed.
2. **Already researched**, from a shared cache keyed by species.
3. **Researched now** — one web search and one cheap extraction, the first time anybody's
   plant is identified as that species. Every run afterwards reads the cache.

The cache carries no owner, deliberately. What *Monstera deliciosa* wants is the same fact
for everybody, and scoping it per account would mean researching the same plant again for
every new person who photographs one. Nothing personal is stored there — a species name and
public care guidance.

**It refuses more readily than it answers.** Web search returns near misses confidently:
asked about *Ocimum africanum* it comes back with four results, three about *Ocimum
basilicum* and not one mentioning *africanum*. A profile written from that would describe the
wrong plant with complete assurance. So the extraction reports which species the material was
actually about, that is compared against the species asked for, and a mismatch produces
nothing. No results, a failed call and an unreadable response all land the same way. A caller
told nothing is known widens its differential and lowers its confidence; a caller told the
wrong thing does neither, which is why refusing is the safe direction.

**A researched profile says it was researched**, wherever you read it. Ask the chat agent
about a plant's care and a generated baseline comes back with the sources it was built from
and a note that it is a starting point rather than an authority. The diagnosis prompt is told
the same thing in a clause, so the model weights it slightly less against an observation that
contradicts it. A curated profile is never described that way. Same rule the differential
already follows: a guess in the shape of an answer should say which it is.

The evaluation harness uses the curated tier **only** — no cache, no research — for the same
reason it stubs species identification: a network call inside a measurement, and a score that
depended on which species previous runs happened to have researched, would both make the
numbers mean less.

### What weather a diagnosis sees

Two windows, because there are two questions.

**What the plant stood in** — the three weeks ending the day the photograph was taken. Not
the three weeks ending today: a plant photographed a week ago did not stand in this week's
weather.

**What it is about to face** — the seven days ahead, from today. Every diagnosis ends in a
plan, and a plan that does not know a frost is due on Thursday has a hole in it.

Neither is dumped into the prompt. Thirty-seven rows of unremarkable weather bury the one
frost date that explains the plant and cost tokens on every outdoor run to do it, so what the
model reads is a *reading*: the notable events with their dates — frosts, heat spells,
droughts, prolonged wet — then the seven days immediately before the photograph and the seven
ahead, day by day. An unremarkable window is one sentence rather than a table.

Where a photograph carried a position and you accepted the place name derived from it, that
position is used directly rather than resolved back from the name — a round trip that loses a
little at each end. Change the name and what you typed wins, because a correction that lost
to the coordinates behind it would be a control that does nothing.

The series is **kept on the observation**, so a diagnosis's evidence stays recoverable: "why
did it say frost damage?" has an answer only while the frost is still on the record. It comes
back on the diagnosis endpoint, and the chat agent answers weather questions from it before
it reaches for the network — which is not only cheaper but is what keeps the answer
consistent with the diagnosis, made against those same days.

Indoor plants fetch no weather. Unchanged, and deliberate: the connection is weak enough that
demanding a place for it would be demanding it for nothing.

**Most photographs carry none of this**, and that is the ordinary path rather than a
fallback. Messaging apps strip metadata, browser camera capture rarely has any, and a screen
grab never did. Then the date field offers today and the location field is empty, and an
outdoor plant has to be given one.

Turning a position into a place name needs a service, and this one needs no key:
[Nominatim](https://nominatim.openstreetmap.org), OpenStreetMap's own. Its terms are
requirements rather than courtesies, and all three are met — a `User-Agent` that identifies
the application, at most one request a second (which the cache makes true, since every
photograph from one garden rounds to the same position), and **attribution wherever the data
appears**, which the interface does for you. Set `PLANTOPIA_GEOCODING_USER_AGENT` to
something with your own contact address, and point `PLANTOPIA_GEOCODING_URL` at your own
instance if you outgrow the shared one. Without either, a name is simply not offered and the
field is empty.

### Accounts and roles

`GET /api/v1/me` answers who you are: your address, tier, the privacy notice you agreed to,
and how many runs you have left this month. The last is there so an interface can warn you
before a diagnosis is refused rather than after.

Every account is a `member`. One thing is not available to members — the evaluation
harness's results at `GET /api/v1/evaluation/latest` — because it is the only thing in the
system nobody owns, so tenancy has nothing to say about who may see it. Promote an account
by hand:

```sql
UPDATE users SET role = 'admin' WHERE email = 'you@example.com';
```

A member asking for it gets 404, not 403: a refusal that distinguishes "you may not" from
"there is nothing here" tells a stranger the route exists.

**Port 5433, not 5432.** A machine with PostgreSQL already installed has a service on
5432, and on Windows both it and Docker's proxy will bind the port — so connections reach
whichever won, and the symptom is `password authentication failed for user "plantopia"`
from a container that is demonstrably healthy. Publishing elsewhere removes the ambiguity
rather than asking anyone to stop their own database.

**One key, four models.** Everything — chat *and* embeddings — is routed through
[OpenRouter](https://openrouter.ai), which mirrors the OpenAI API shape on both its
`/chat/completions` and `/embeddings` endpoints. Switching providers is a
configuration change rather than a code change, and there is one key and one bill.

The pipeline uses separate tiers because its jobs differ enormously in difficulty, and
the price gap between tiers is often more than tenfold:

| Tier | Used by | Default |
|---|---|---|
| `gate` | the two binary image checks, which run on every diagnosis | `google/gemini-2.5-flash-lite` |
| `vision` | species identification, symptom extraction | `google/gemini-2.5-flash` |
| `reasoning` | question selection, diagnosis, treatment planning | `openai/gpt-4o` |
| `embedding` | corpus indexing and query retrieval | `openai/text-embedding-3-small` |

Every one of those was verified reachable **and tool-calling** on a restricted,
college-issued OpenRouter key. That qualifier matters more than it sounds: a model that
answers a chat request but cannot emit a tool call is useless here, because the whole
pipeline depends on structured output.

### Checking what your key can reach

OpenRouter gates providers by data policy, and organisation-issued keys are often
restricted. A blocked model returns

```
404 No endpoints available matching your guardrail restrictions and data policy
```

which is an **account setting, not a bad slug** — worth knowing before you spend an hour
on the wrong hypothesis. On the key this was developed against, `anthropic/claude-sonnet-4.5`,
`openai/gpt-4.1`, `google/gemini-2.5-pro` and `gemini-embedding-001` were all blocked
while `openai/gpt-4o` and the Gemini Flash models worked. Distinguish the three failure
modes by their message: `No endpoints available matching your guardrail…` is policy,
`Model X does not exist` is a wrong slug, and `No endpoints found for X` is a real slug
with nothing serving it.

`.env.example` lists the stronger models as commented-out upgrades to try if your policy
permits them.

### Cross-modal retrieval is off by default

The design includes a second retrieval path that embeds the photograph itself and
searches the same corpus, bypassing the vision model's written description — two paths
that fail independently (spec §10.4). It needs an embedding model accepting image input,
and none is currently reachable: the OpenAI embedding models refuse images outright
(*"OpenAI embeddings do not support image_url inputs"*), and `gemini-embedding-001`, the
only candidate, is data-policy blocked on restricted keys.

So `PLANTOPIA_MULTIMODAL_EMBEDDINGS` defaults to `false` and diagnosis runs on the text
path alone. The code stays in place and tested; set that flag to `true` alongside a
multimodal `PLANTOPIA_EMBEDDING_MODEL` and the path lights up with no code change.

When it is off, the pipeline says so rather than staying quiet about it. The retriever
reports that it cannot search by image, so the enrich node skips the call and does not
list `search_by_photograph` among the tools used; the diagnose prompt states outright
that no photograph-matched material is available. Both exist because the first live run
showed what silence costs — the model narrated visual corroboration it had never been
given, and the UI credited a search that could not have happened.

A Tavily key is optional. Without it, web-search escalation is skipped and diagnosis
relies on the curated corpus alone.

A LangSmith key is optional too. Without it, tracing is skipped and the app runs
unchanged; with it, every graph run is traced under the configured project.

## Example

> **You upload** three photos of a basil plant with yellowing lower leaves.
>
> **Plantopia asks** how often you water it, whether the pot has drainage holes, and
> how many hours of direct light it gets.
>
> **You answer** every other day, no drainage holes, about three hours.
>
> **Plantopia returns:**
>
> 1. **Overwatering — 65%** · 🟡 Act this week
>    *How to confirm:* push a finger 3 cm into the soil three days after watering. If
>    it is still wet, water is going in faster than the plant can use it.
>    *Points to it:* no drainage holes, watering every other day, yellowing on the
>    oldest leaves, soil wet in the photo.
>    *Argues against it:* the plant is not wilting, and the stem base looks firm.
>
> 2. **Insufficient light — 22%** · 🟢 Monitor
>    *How to confirm:* compare the spacing between new leaves with older growth. Long
>    gaps mean the plant is stretching for light.
>
> **Treatment plan**
> 1. Stop watering until the top 3 cm is dry — *today*
> 2. Repot into a container with drainage holes — *within 3 days*
> 3. Move to your brightest windowsill — *today*

## How it works

```
photos ──▶ guard_input ──▶ quality_check ──▶ identify_plant ──▶ assess_symptoms
              │                  │                                     │
        not a plant         too blurry                                 ▼
              ▼                  ▼                            select_questions
            stop               stop                                    │
                                                                       ▼
                                                              gather_context
                                                           ══ interrupt() ══
                             ┌─────────────────────────────────────────┘
                             ▼
                       hypothesise ── name the disorders worth reading about
                             │
                             ▼
                          enrich ── knowledge base (the shortlist, fetched by name)
                             │   ├─ weather        (outdoor plants only)
                             │   └─ web search     (only if retrieval is weak)
                             ▼
                        diagnose ──▶ check_contagion ──▶ build_roadmap ──▶ persist
```

A re-check of a known plant is the same graph on a different route: `quality_check`
sends it straight to `assess_symptoms`, skipping identification, and `compare_progress`
then either revises the existing roadmap or escalates into the full differential —
through `hypothesise`, so an escalating re-check reads the same shortlist a first
diagnosis would. [`docs/agent-graph.md`](docs/agent-graph.md) has both graphs drawn from
the code itself, so they cannot quietly disagree with it.

**Two agent architectures, deliberately.** The diagnosis pipeline is an explicit
LangGraph state machine, because two orderings must be guaranteed: identification
precedes diagnosis, and the clarifying-question interrupt always fires. A free-form
ReAct agent asked to do this reliably will sometimes skip a step. Conversational
follow-up has no predictable shape, so it uses a ReAct loop instead.

**When RAG, when search.** The curated corpus is authoritative and reproducible, so it
is consulted first. Web search fires only when the best retrieval score falls below a
threshold or the species could not be identified — the case where the corpus may
simply not cover this plant. Web results are labelled as such in the UI.

**Why a model names the disorders before retrieval runs.** Similarity search answers
"which corpus text resembles this description", which is not the question "what could be
wrong with this plant". On the nutrient cases the two came apart badly: the owner's words
(*"faded to a flat, dull yellow"*) and the corpus's (*"uniform pale green or yellow, veins
included"*) are not near neighbours, and the correct document sat at rank 16, 17 and 21 of
43 — far enough down that no reordering of six results reaches it. The `hypothesise` node
asks the model to name candidates from the list of ids the corpus actually holds, and
`enrich` fetches those by name. Rank stops mattering once you can look something up by
name. It is a shortlist for *reading*, never a conclusion: nothing there writes to the
differential, and `diagnose` is free to reject every hypothesis it offered. If the call
fails the pipeline falls back to similarity search alone.

**Memory.** Short-term state lives in a LangGraph Postgres checkpointer, which is what
lets the graph pause for your answers and survive a page reload — or a redeploy. Long-term
memory is the application's own tables — plants, observations, diagnoses, roadmap steps
and learned facts about the owner — which is what makes contagion triage, the re-check
flow and the learned profile possible. Both live in the same PostgreSQL, along with the
photographs themselves.

Both graphs share one checkpointer. They used to have a SQLite file each, because the
diagnosis one grew by ~100 MB per run: graph state carried whole photographs as base64
and LangGraph re-serialises state at every superstep. State carries blob keys now, so a
completed diagnosis leaves under a kilobyte behind and there is nothing to keep apart.
What does keep runs apart is the thread id, which carries its owner — a handle resumes a
paused diagnosis that has already been paid for, so it is checked before use.

## Safety

- Non-plant uploads are rejected, closing the "upload a person, get medical advice" path
- Retrieved and web content is fenced as untrusted data; instructions found inside it
  are reported, never followed
- Uploads are validated by magic bytes, not filename
- Treatment escalates cultural → mechanical → biological → chemical, and never states
  a dose for a chemical product
- Below a confidence threshold, the agent says it cannot tell and names the evidence
  that would resolve the question
- Every chat reply names the sources it consulted, on the reply rather than behind a
  click, and the agent is told to admit when it answered from its own knowledge instead of
  a lookup — a grounded answer should be distinguishable from an ungrounded one at a
  glance. An empty lookup points it at web search rather than back at its memory

### How much of a conversation the model sees

Every turn resends what came before, so an unbounded history is a cost that compounds: turn
*N* pays for turns 1..*N*. Measuring where that weight actually sits was the surprise —

| What one turn adds | Tokens |
|---|---|
| A web-search result | **~1,315** |
| A knowledge-base lookup | ~295 |
| A weather block | ~250 |
| Everything a person and the agent *said* | ~200 |

— tool output is the bulk by roughly six to one, and web search is the common path rather
than the rare one.

So two things happen, cheapest first. Past `PLANTOPIA_CHAT_CLEAR_TOOLS_AFTER_TOKENS` the
**older tool results stop being replayed**, keeping the most recent three whole; that costs
no model call and loses nothing anybody chose to say. Past a much higher
`PLANTOPIA_CHAT_SUMMARISE_AFTER_TOKENS` the **conversation itself is condensed** into a
summary, keeping recent exchanges verbatim — a backstop that takes hundreds of turns to
reach, and exists because without it there is still no bound.

Measured across a scripted conversation:

| Turns | Sent without limits | Sent with them | Billed across the whole conversation |
|---|---|---|---|
| 5 | 6,738 | 6,738 (untouched) | 20,216 → 20,216 |
| 10 | 13,477 | 4,277 | 74,126 → 41,270 |
| 20 | 26,962 | 4,618 | 283,068 → 85,924 |
| 40 | 53,932 | 5,298 | 1,105,503 → 185,434 |

The middle column stops growing, which is the point. A short conversation is sent exactly as
it happened.

**The stored transcript is never altered.** Only what reaches the model changes: every
message stays readable on the page, in an export, and behind the timeline's events. That is
held in place by its own tests rather than by care.

## Capstone showcase

The capstone brief requires this README to link to the project's entry on
[showcase.turingcollege.com](https://showcase.turingcollege.com/), and requires that entry to
reflect the project's current state. **That link is not here yet, and belongs here:**

> Showcase: _(add the link once the project is uploaded)_

Uploading is something only the project's owner can do, so it is recorded here rather than
done. The review does not pass without it.

## Development

```bash
docker compose up -d db          # a prerequisite: the suite uses a real database
uv run pytest                    # unit, graph and API tests, ~2½ minutes
uv run ruff check . && uv run ruff format .
```

**There are two suites, and passing one says nothing about the other.**

```bash
cd web
npm run build                    # the typecheck and the production build, in one command
npm test                         # components and hooks against a mocked API, ~20 seconds
npx playwright test              # the browser tests, against the real stack, ~1½ minutes
```

**All of it runs on every push.** `.github/workflows/ci.yml` runs ruff, the Python suite
against a PostgreSQL service container, the frontend typecheck and unit suite, a production
build, and the browser tests — the same commands as above, not a parallel set that can drift
from them. The coverage floor is enforced by `pyproject.toml`, so moving it moves CI too.

No step reads a secret, because no test needs one, so a pull request from a fork is verified
exactly as a branch is. The evaluation harness is never run there: it makes real model calls
and costs about $1.50 a time.

`npx playwright install chromium` once, first. The browser tests start their own API and
their own Vite server on ports of their own, so they cannot collide with anything you have
open, and they recreate and migrate their own database on every run — `docker compose up
-d db` is the only prerequisite.

1,606 tests at 95% coverage, gated at 85%.

**Tests make no LLM calls.** That constraint is absolute: models arrive through
`core/llm.py`, which tests replace with a scripted fake, and HTTP is mocked at the
transport layer with `respx`. Tests assert on structure and control flow, never on
generated prose — model output is not deterministic enough to assert on, even at
temperature 0.

They do talk to a database. The suite used to advertise "no network calls" as well, and
that claim is retired rather than quietly falsified: repository, blob-store, retriever and
checkpoint tests run against real PostgreSQL in a container, on a throwaway database
created per session and dropped afterwards, each test inside a transaction that is rolled
back. Mocking the database in a project whose subject is the database would produce tests
that assert on the mock.

**Nothing is tested outside the gated run any more.** The `ui` tier went with the retired UI,
and `api/` and `identity/` are measured in the default run, so the gate sees everything
except the evaluation CLI and two one-shot migration tools — each omitted for being
real-infrastructure wiring with nothing in it a test could assert that would not be a mock
asserting on itself.

**The browser tests script the models too.** Everything below the browser is real — a real
API, a real database, the real graph with its real interrupt — and only the models are
replaced, from `tests/e2e/models.py`. The patch lives in test code rather than behind a
setting on purpose: a `PLANTOPIA_SCRIPTED_MODELS` flag would be a switch that silently
disables the model, shipped in the same package as the thing it disables.

They exist because a green component suite has repeatedly described screens that did not
work. An SSE parser that yielded nothing because the server sends CRLF; a registration that
flushed and never committed; every clarifying question rendering as an unlabelled text box
because the client type said `prompt` where the graph says `text`. Each was invisible in
jsdom and obvious in a browser within seconds. If you change a screen, run both.

### Opening the graphs in LangGraph Studio

```bash
uv run langgraph dev --studio-url https://eu.smith.langchain.com
```

Serves both graphs from `langgraph.json` on `http://127.0.0.1:2024` and renders them in
Studio, where you can run a thread, stop at the interrupt, inspect state at every step and
fork from any point. `--studio-url` is not optional: this project's LangSmith key is on the
**EU** instance and the CLI defaults to the US one, where it silently shows nothing.
`langgraph dev` loads `.env`, so running a thread there costs real money — looking at the
diagram does not. See [`docs/agent-graph.md`](docs/agent-graph.md) for the details.

### Evaluation

```bash
uv run python -m eval.run_eval
```

Runs the golden-set harness against a real model — question selection, differential
diagnosis and retrieval, scored for top-1/top-3 accuracy and Ragas retrieval metrics,
with the same case run several times to measure how stable the diagnosis is under
byte-identical input. It takes several minutes and makes real, billed model calls, so
it is never invoked by the test suite or by the app itself. It writes a timestamped
JSON file to `eval/results/` and a human-readable `eval/REPORT.md`.

Where it currently stands, over 28 golden cases (2026-08-19, `overwaterer` profile — see
`--profile` below):

| Metric | Score |
|---|---|
| Top-1 diagnostic accuracy | 89.3% |
| Top-3 diagnostic accuracy | 96.4% |
| Top-1 agreement on byte-identical input | 100.0% |

Every category reaches 100% at top-3 except `other`, which is two cases. Of the three
top-1 misses, one landed on a disorder its own case listed as a confusable neighbour.
Reasoning before retrieval (`hypothesise`) is what moved top-1 from 75.0% to 89.3%, and
took nutrient deficiencies — the category that used to fail at 33.3% on *both* top-1 and
top-3 — to 100% at top-3.

All four Ragas metrics now score all 28 rows. Earlier runs lost roughly half the judge
calls to dropped connections and averaged over whatever survived, so figures from before
that fix are not comparable with these. `eval/REPORT.md` carries the full table, the
per-metric row counts, and a **What this does not measure** section — the short version
being that golden cases inject symptoms as text, so none of these numbers say anything
about the vision layer.

```bash
uv run python -m eval.run_eval --profile overwaterer
```

`--profile` injects a fixture from `eval/profiles/` as a run-level prior, the same
block a real owner's learned facts would produce, so the harness can measure whether
the profile moves diagnosis rather than just trusting that it does. It defaults to
`empty`, which renders as no block at all. Two such runs are recorded in
`docs/known-limitations.md`: an empty profile reproduces the Phase 3 baseline exactly,
and a deliberately lopsided one changes candidates and clarifying questions on a
minority of cases without pulling any category's top diagnosis toward the biased
disorder.

Both of those gates predate `hypothesise`, and no neutral-profile run has been made since
it landed — so the table above is a lopsided-profile run, and the 75.0% → 89.3% lift is
measured between two `overwaterer` runs rather than against the `empty` baseline. That
keeps the comparison clean but leaves the current neutral figure unmeasured; an `empty` run
is the cheapest thing to do next.

Results are written to `eval/results/` as timestamped JSON and Markdown. The page that
used to render them went with the retired UI; reading the newest file is the interface until
the React frontend has somewhere to put it.

The harness runs as its own account — created on demand, unverified, with an unusable
password, so nothing can sign in as it. Its plants and diagnoses are real rows in the real
database, which is what lets a surprising score be investigated afterwards rather than only
re-run.

`ragas` and `pyyaml`, used only by the harness, are `dev`-dependency-group packages —
the shipped app never imports them.

## Project structure

| Directory | Responsibility |
|---|---|
| `api/` | FastAPI routers, dependencies and response schemas |
| `identity/` | Passwords, tokens, sessions, accounts |
| `agent/` | Both graphs, nodes, state, schemas, prompts |
| `tools/` | The seven function tools |
| `knowledge/` | Disorder corpus, ingestion, retrieval |
| `data/` | Models, repositories, Alembic migrations |
| `core/` | Config, model factory, guards, image handling, cost, tracing |
| `eval/` | Golden set, harness, metrics, report renderer |
| `services/` | The boundary the routers call |
| `tests/` | `unit/`, `graph/` and `api/` tiers |
| `docs/` | Graph diagrams, code tour, plans, limitations |

## Known limitations

- **The vision layer is unmeasured.** Golden cases supply symptoms as text and are
  injected past `identify_plant` and `assess_symptoms`, so no number in `eval/REPORT.md`
  says anything about species identification or symptom extraction from a photograph.
  Diagnosis is stable on byte-identical *text*; the one badly unstable run on record
  differed in its photographs, which makes vision the prime suspect and the measurement
  most worth buying next
- The corpus covers common houseplant and small-garden disorders. Unusual species fall
  back to web search and generic physiology, with lower confidence
- Registration is open to anybody who can receive email. There is no invitation, no approval step, and no way to close it short of taking the deployment down — which matters more now that a run costs money
- Photographs cannot show root condition, so root disorders always depend on the
  confirming test rather than the image
- Chat token usage and cost are not tracked at all, so the saving from bounding the context
  is measurable in a test and invisible in production (`M17`)
- Uploads are capped at 1568px on the long edge (`max_image_edge_px`) before they reach
  the vision model — an image already inside the cap is returned unchanged and never
  re-encoded. The cap is a cost bound, not a claim about accuracy: nothing in this project
  measures the vision layer (`M19`), so this does not claim the cap leaves a diagnosis
  unchanged, only that it stops paying for pixels above the size the model itself
  downscales to

A fuller accounting — every gap raised in review, why it was carried, and what fixing it
would take — is in [`docs/known-limitations.md`](docs/known-limitations.md).

## Design documents

- [`project_brief_Sprint4.md`](project_brief_Sprint4.md) — the sprint-4 assignment
  this was built against
- [`docs/agent-graph.md`](docs/agent-graph.md) — both graphs, drawn from the code, and how
  to open them in LangGraph Studio
- [`docs/code-tour.md`](docs/code-tour.md) — a reading order through the codebase
- [`docs/plans/`](docs/plans/) — implementation plans
- [`docs/known-limitations.md`](docs/known-limitations.md) — carried work and non-goals
- [`eval/REPORT.md`](eval/REPORT.md) — the newest evaluation run in full
