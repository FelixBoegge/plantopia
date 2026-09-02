import { useEffect, useRef } from "react";
import { X } from "lucide-react";

import { Photo } from "@/components/Photo";

/**
 * One photograph, large, over the page.
 *
 * The thumbnails in a plant's history are 80 pixels square, which is enough to tell two
 * observations apart and nowhere near enough to see what somebody photographed — the leaf
 * they were worried about is the thing that gets cropped and shrunk away.
 *
 * A plain overlay rather than `<dialog>`: `showModal` gives Escape, a backdrop and a focus
 * trap for free, but it is unevenly implemented in the environment the tests run in, and a
 * viewer that cannot be tested is a viewer that quietly stops closing.
 *
 * So the three things `<dialog>` would have given are here explicitly. Escape closes it,
 * because that is what Escape does. A click on the backdrop closes it — the check is that
 * the click landed on the backdrop itself and not on something inside it, or a click that
 * ends on the image after starting on the backdrop would dismiss what somebody is looking
 * at. And focus moves to the close button on open, so the keyboard is inside the thing that
 * just appeared rather than still behind it.
 */
export function PhotoViewer({
  photoKey,
  onClose,
}: {
  photoKey: string;
  onClose: () => void;
}) {
  const close = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    close.current?.focus();
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Photograph"
      className="bg-background/90 fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <button
        ref={close}
        type="button"
        onClick={onClose}
        aria-label="Close the photograph"
        className="bg-card text-card-foreground hover:bg-muted absolute top-4 right-4 rounded-full border p-2"
      >
        <X className="size-4" />
      </button>

      <Photo
        photoKey={photoKey}
        alt="This plant, as photographed"
        className="max-h-full max-w-full rounded-lg object-contain"
      />
    </div>
  );
}
