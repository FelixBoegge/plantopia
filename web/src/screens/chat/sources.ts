/**
 * What a lookup is called when somebody is told about it.
 *
 * The same table the server keeps for its streamed events, because a reply's chips and the
 * progress shown while it was produced must not name the same source two different ways.
 * A test asserts they agree.
 */

const NAMES: Record<string, string> = {
  search_plant_knowledge: "the disorder reference",
  lookup_plant_care_profile: "care guidance for this species",
  get_local_weather: "the local weather",
  web_search_plant_info: "the web",
  get_plant_journal: "this plant's history",
  suggest_new_diagnosis: "whether this needs a fresh diagnosis",
};

const UNKNOWN = "another source";

/** How one tool is announced. An unmapped one is never named by its own identifier. */
export function sourceName(tool: string): string {
  return NAMES[tool] ?? UNKNOWN;
}

export const KNOWN_SOURCES = NAMES;
