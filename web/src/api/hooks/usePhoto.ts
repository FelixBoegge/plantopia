import { useEffect, useState } from "react";

import { currentToken } from "@/api/session";

/**
 * A photograph, fetched with the session and handed to `<img>` as a blob URL.
 *
 * **An `<img src>` cannot send an `Authorization` header.** The same problem as the event
 * stream, and the same wrong answer available: put the token in the query string, where it
 * lands in the access log and — worse for an image — in the `Referer` of anything the page
 * loads next. So the bytes are fetched properly and the element is given a `blob:` URL,
 * which carries no credential and cannot leave the page.
 *
 * The URL is revoked when the component goes away. Without that, every photograph a person
 * scrolls past is held in memory until the tab is closed.
 */
export function usePhoto(key: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!key) {
      setUrl(null);
      return;
    }

    let revoked: string | null = null;
    let abandoned = false;

    (async () => {
      try {
        const response = await fetch(`/api/v1/photos/${key}`, {
          headers: { Authorization: `Bearer ${currentToken() ?? ""}` },
        });
        if (!response.ok) return;
        const objectUrl = URL.createObjectURL(await response.blob());
        if (abandoned) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        revoked = objectUrl;
        setUrl(objectUrl);
      } catch {
        // A photograph that will not load is a missing picture, not a broken screen.
      }
    })();

    return () => {
      abandoned = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [key]);

  return url;
}
