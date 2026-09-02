/**
 * What the server will accept from an upload.
 *
 * Stated here so the form can say it before somebody picks a file, rather than after the
 * server has refused one. A person who chose four photographs, waited for them to upload
 * and was then told the third was a HEIC has done work the screen could have saved them.
 *
 * **These are the server's numbers, copied.** They come from `Settings` —
 * `max_images_per_observation`, `max_upload_bytes` — and the formats are what
 * `core/guards.py` recognises by magic bytes. Copied rather than fetched, because an
 * endpoint for three constants is more machinery than the fact deserves; and
 * `tests/api/test_upload_limits_agree.py` fails if they and the settings ever disagree,
 * which is the part that would otherwise go unnoticed.
 */

/** How many photographs one diagnosis may carry. */
export const MAX_IMAGES = 4;

/** The largest a single photograph may be, in megabytes. */
export const MAX_IMAGE_MB = 8;

/**
 * What the file picker offers.
 *
 * Not `image/*`. The server validates by magic bytes and knows only PNG and JPEG, so a
 * picker offering every image format invites a HEIC straight off an iPhone and a refusal
 * that arrives after the upload.
 */
export const ACCEPTED_TYPES = "image/png,image/jpeg";
