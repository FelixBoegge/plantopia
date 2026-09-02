/**
 * What a lookup is called when somebody is told about it.
 *
 * The same table the server keeps for its streamed events, because a reply's chips and the
 * progress shown while it was produced must not name the same source two different ways.
 * A test asserts they agree.
 */

const NAMES: Record<string, string> = {
  search_plant_knowledge: "Plantopia's disorder reference, for what this looks like",
  lookup_plant_care_profile: "Plantopia's care guidance, for what this species needs",
  get_plant_weather: "Open-Meteo, for the weather where this plant is",
  get_local_weather: "Open-Meteo, for the local weather",
  web_search_plant_info: "a web search, for what the reference does not cover",
  get_plant_journal: "Plantopia's record of this plant, for what has happened to it",
  suggest_new_diagnosis: "Plantopia's own check, for whether this needs a fresh diagnosis",
};

const UNKNOWN = "another source";

/** How one tool is announced. An unmapped one is never named by its own identifier. */
export function sourceName(tool: string): string {
  return NAMES[tool] ?? UNKNOWN;
}

export const KNOWN_SOURCES = NAMES;
