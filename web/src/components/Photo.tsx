import { usePhoto } from "@/api/hooks/usePhoto";

/**
 * A stored photograph.
 *
 * Empty alt text on purpose: these are decorative next to the plant's name, and a screen
 * reader announcing "photograph of a plant" before every card is noise. Where a photograph
 * carries meaning, pass one.
 */
export function Photo({
  photoKey,
  alt = "",
  className,
}: {
  photoKey: string | null | undefined;
  alt?: string;
  className?: string;
}) {
  const url = usePhoto(photoKey);

  if (!url) {
    return <div className={`bg-muted ${className ?? ""}`} aria-hidden="true" />;
  }
  return <img src={url} alt={alt} className={className} />;
}
