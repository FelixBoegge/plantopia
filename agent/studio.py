"""Graph factories for the LangGraph dev server, which is what LangGraph Studio draws.

``langgraph dev`` reads ``langgraph.json``, imports the factories named there, and
serves the compiled graphs over a local API; Studio renders that topology and can run
threads against it. Both factories build the same objects the API does, via
``agent/wiring.py``, so what Studio shows is the graph that actually runs.

Neither passes a checkpointer. The API server supplies its own persistence and rejects
a graph that arrives with one already attached — which is also why these are factories
rather than module-level graphs: building at import time would run the whole
dependency wiring (models, Chroma, the database) merely to import the module.

Two graphs rather than one nested diagram: the diagnosis pipeline is a fixed
``StateGraph``, and chat is an independently compiled ReAct loop with its own
lifetime and its own checkpoint file. Studio lists them side by side, which is what
they are. Presenting the ReAct loop as a subgraph of the pipeline would draw a
relationship that does not exist.
"""

import asyncio
import functools
import logging

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from agent.chat_agent import make_chat_agent
from agent.deps import Deps
from agent.diagnosis_graph import build_diagnosis_graph
from agent.wiring import build_deps, build_profile_service, harness_owner_id, open_session
from core.config import get_settings

logger = logging.getLogger(__name__)


@functools.cache
def _deps() -> Deps:
    """The wiring, built once for the life of the dev server.

    Cached because the server calls a factory per request: without this, every glance
    at the graph would re-open the database and re-embed the corpus.
    """
    owner = harness_owner_id(open_session(get_settings()))
    profile = build_profile_service(user_id=owner)
    return build_deps(user_id=owner, profile_facts=profile.facts_for_prompt)


async def _wiring() -> Deps:
    """``_deps()`` off the event loop.

    Both factories are async and offload for one reason: the dev server calls them
    from its event loop and watches for blocking calls, and this wiring is thoroughly
    blocking — a connection pool, Chroma, an embeddings request. Left inline it trips
    the server's blocking-call detector and the graph fails to load at all, which
    ``langgraph dev --allow-blocking`` would paper over rather than fix. A SQLAlchemy
    session is not shared across threads, and the pool hands each caller its own
    connection, so building on a worker thread and using it from another is safe.
    """
    return await asyncio.to_thread(_deps)


async def diagnosis_graph() -> CompiledStateGraph:
    """The diagnosis pipeline: guards, identification, questions, differential, roadmap.

    The interrupt before the clarifying questions is part of the topology and shows up
    in Studio as such — a run stops there until the thread is resumed with answers.
    """
    return build_diagnosis_graph(await _wiring(), checkpointer=None)


async def chat_graph(config: RunnableConfig) -> CompiledStateGraph:
    """The plant-scoped ReAct loop: model, tools, back to the model until it is done.

    Which plant to scope to comes from the run's own config, because the agent's
    system prompt is built from that plant's record and its latest diagnosis::

        {"configurable": {"plant_id": 1}}

    Studio exposes that as an editable field on the run, so the plant can be chosen
    per thread. Falling back to the newest plant keeps the graph loadable with no
    configuration at all — the point of opening Studio is often just to look at the
    shape, and a factory that raised on an empty config would draw nothing.
    """
    deps = await _wiring()

    plant_id = (config.get("configurable") or {}).get("plant_id")
    if plant_id is None:
        plants = await asyncio.to_thread(deps.plants.list_all)
        if not plants:
            raise ValueError(
                "No plants exist yet, so there is no conversation to scope. Run a "
                "diagnosis in the app first, or pass {'configurable': {'plant_id': N}}."
            )
        plant_id = plants[0].id
        logger.info("no plant_id in config; scoping chat to the newest plant %s", plant_id)

    # make_chat_agent reads the plant and its latest diagnosis to build the system
    # prompt, so it is two more queries that must not run on the event loop.
    agent, _escalation = await asyncio.to_thread(
        make_chat_agent, deps, int(plant_id), checkpointer=None
    )
    return agent
