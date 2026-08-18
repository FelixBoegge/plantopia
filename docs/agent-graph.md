# The agent graphs

Plantopia runs two graphs, not one. The diagnosis pipeline is an explicit state
machine, because two orderings have to be guaranteed — identification precedes
diagnosis, and the clarifying-question interrupt always fires. Chat is a ReAct loop,
because follow-up conversation has no predictable shape. Neither is nested inside the
other: they have separate lifetimes and separate checkpoint files.

Both diagrams below are generated from the graphs themselves — `get_graph()
.draw_mermaid()` on what `agent/diagnosis_graph.py` and `agent/chat_agent.py` build —
rather than drawn by hand, so they cannot quietly disagree with the code. Dotted edges
are conditional; the label is the branch a router returns.

## Diagnosis pipeline

```mermaid
graph TD;
	__start__([__start__]):::first
	guard_input(guard_input)
	quality_check(quality_check)
	identify_plant(identify_plant)
	assess_symptoms(assess_symptoms)
	select_questions(select_questions)
	gather_context(gather_context)
	hypothesise(hypothesise)
	enrich(enrich)
	diagnose(diagnose)
	check_contagion(check_contagion)
	build_roadmap(build_roadmap)
	persist(persist)
	compare_progress(compare_progress)
	revise_roadmap(revise_roadmap)
	__end__([__end__]):::last
	__start__ --> guard_input;
	guard_input -. reject .-> __end__;
	guard_input -. continue .-> quality_check;
	quality_check -. retake .-> __end__;
	quality_check -. recheck .-> assess_symptoms;
	quality_check -. continue .-> identify_plant;
	identify_plant --> assess_symptoms;
	assess_symptoms -. recheck .-> compare_progress;
	assess_symptoms -. continue .-> select_questions;
	compare_progress -. escalate .-> hypothesise;
	compare_progress -. revise .-> revise_roadmap;
	select_questions --> gather_context;
	gather_context --> hypothesise;
	hypothesise --> enrich;
	enrich --> diagnose;
	diagnose --> check_contagion;
	check_contagion --> build_roadmap;
	build_roadmap --> persist;
	revise_roadmap --> persist;
	persist --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Four things the picture does not say on its own:

- **The interrupt is at `gather_context`.** The run stops there and waits for the
  owner's answers to the clarifying questions; resuming needs a checkpointer, which is
  why every builder call that intends to *run* the graph must pass one.
- **`hypothesise` reasons before it retrieves.** It names the disorders worth reading
  about, from the list of ids the corpus actually holds, and `enrich` then fetches those
  documents directly instead of hoping similarity ranks them. Measured against the
  golden set, the correct document reached the model in 23 of 28 cases on similarity
  alone and 28 of 28 with this step — it was sitting at rank 16, 17, 21, 24 and 35 of
  43 in the cases that failed. Both routes into `enrich` pass through it, so a re-check
  that escalates reads the same shortlist a first diagnosis would.
- **Two paths reach `__end__` early.** `guard_input` rejects an upload that is not
  plant material, and `quality_check` asks for a retake. Both are refusals, not
  failures.
- **A re-check is the same graph on a different route.** `quality_check` sends a
  re-check straight to `assess_symptoms`, skipping identification, and
  `compare_progress` then either revises the existing roadmap or escalates into the
  full differential.

## Chat: the ReAct loop

```mermaid
graph TD;
	__start__([__start__]):::first
	model(model)
	tools(tools)
	__end__([__end__]):::last
	__start__ --> model;
	model -. no tool call .-> __end__;
	model -. tool call .-> tools;
	tools --> model;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

Built by `langchain.agents.create_agent` in `agent/chat_agent.py`. The cycle is the
whole point: the model either answers, or calls a tool and gets another turn with the
result. Its tools are read-only wrappers over what the diagnosis pipeline already has
— the knowledge base, local weather, a care-profile lookup, this plant's journal —
plus `suggest_new_diagnosis`, which is how the agent declines to diagnose from text
alone and hands back to the wizard.

## Opening these in LangGraph Studio

Studio is no longer a separate application: a local API server serves the graphs and
Studio renders them inside LangSmith. Run it in its own terminal, from the repository
root:

```bash
uv run langgraph dev --studio-url https://eu.smith.langchain.com
```

That reads `langgraph.json`, imports the factories in `agent/studio.py`, and serves
both graphs on `http://127.0.0.1:2024`. Pick `diagnosis` or `chat` from the graph
selector. Studio draws the topology, and can run a thread, stop at the interrupt, show
state at every step, and fork from any point.

`--studio-url` is not optional here. This project's LangSmith key is on the **EU**
instance, and the CLI defaults to the US one: it tries to derive the host from the
tracing environment, but `langgraph.json`'s `env: .env` reaches the *graph* process
rather than the CLI, so the derivation finds nothing and falls back. Without the flag it
prints and opens `https://smith.langchain.com/...`, which is a different workspace and
shows nothing. The equivalent link, if the server is already running:

```
https://eu.smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

Two things that are *not* this:

- A **project** view with `?mode=graph` draws the graph reconstructed from one trace's
  spans — the path a single run took, and only once traces exist. It is a view of
  history, not of topology.
- Nothing about the graph is stored on LangSmith. Studio reads it from the server on
  your machine, so the diagram is blank whenever `langgraph dev` is not running.

Two things worth knowing before pressing run:

- **`langgraph dev` loads `.env`**, so a run in Studio uses the real OpenRouter key and
  costs real money, exactly as the app does. Looking at the diagram costs nothing.
- **The chat graph needs to know which plant.** It reads `plant_id` from the run's
  config; set it in Studio's configuration panel, or leave it and the newest plant is
  used.
