import { Link, useParams } from "react-router-dom";

import { usePlant } from "@/api/hooks/plants";
import { readable } from "@/api/problems";
import { Notice } from "@/components/Notice";
import { Chat } from "@/screens/chat/Chat";

/**
 * The conversation about one plant, on a page of its own.
 *
 * It used to be a column beside the plant page. Two things were wrong with that. A
 * conversation is something somebody sits with, and a third of the width is not sitting
 * room; and everything it is about — the finding, the plan, the history — was competing
 * with it for the same screen rather than being a click away.
 *
 * Narrower than the page allows, deliberately. The shell has no maximum width, and a line
 * of chat running the full span of a wide monitor is a line nobody can follow back to its
 * start.
 *
 * The plant is loaded here only for its name. A conversation headed "Ask about this plant"
 * with no plant in sight is a page you can arrive at from a link and not know what it is
 * about.
 */
export function ChatPage() {
  const { plantId = "" } = useParams();
  const { data, isPending, error } = usePlant(plantId);

  if (isPending) return <p role="status">Loading…</p>;

  if (error) {
    return (
      <Notice tone="failure" title="This plant could not be loaded">
        {readable(error)}
      </Notice>
    );
  }

  if (!data) return null;

  return (
    <div className="grid max-w-3xl gap-6">
      <div className="grid gap-1">
        <h1 className="text-2xl font-semibold">{data.plant.name}</h1>
        <Link
          to={`/plants/${plantId}`}
          className="text-muted-foreground w-fit text-sm underline underline-offset-4"
        >
          Back to this plant
        </Link>
      </div>

      <Chat plantId={plantId} />
    </div>
  );
}
