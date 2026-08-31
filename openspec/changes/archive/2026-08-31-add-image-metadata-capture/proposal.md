## Why

A photograph already knows two things the owner is currently asked for, or that nobody asks
for at all: when it was taken, and where.

**When** is the more consequential of the two, and it is silently wrong today. An observation
is dated when it was uploaded, and the weather window is anchored on that date. Somebody who
photographs a struggling plant on Sunday and gets round to uploading it on Wednesday is
diagnosed against three days of weather the plant did not experience, and against symptoms
attributed to the wrong day. Nothing in the system notices, because the two dates are
indistinguishable once the file is stored.

**Where** is currently a question — outdoor plants are asked which town they are in, and a
person who does not answer gets no weather at all. The photograph frequently carries a GPS
fix that would answer it without asking.

Both are enrichment rather than a new source of truth. Photographs shared through messaging
apps arrive stripped, browser camera capture often carries no metadata at all, and a screen
grab has neither. So everything here has to degrade to exactly what happens today.

## What Changes

- **Metadata is read from the original bytes on arrival**, before the orientation
  normalisation that would destroy it. `core/images.py:upright_bytes` calls
  `ImageOps.exif_transpose` and re-saves, which clears the orientation tag and can take the
  rest of the metadata block with it. This ordering is a correctness constraint, not a
  preference, and it is easy to reverse by accident.
- **The capture date, where the photograph declares one, dates the observation** and anchors
  the weather window. Where it does not, the upload date does, exactly as now.
- **A GPS fix is coarsened on arrival and the precise position is never stored.** Rounded to
  roughly a tenth of a degree — about eleven kilometres — which is indistinguishable from the
  doorstep for weather purposes and is not somebody's address.
- **A coarse position is turned into a place name** by a reverse-geocoding lookup, so the
  wizard can say "detected: near Berlin" rather than a pair of numbers. Free, keyless, and
  degrading to the coordinates alone when it fails.
- **Everything detected is shown and editable before the run starts.** A detected date or
  place is a suggestion the owner can correct or clear, not a fact imposed on them.
- **The reverse-geocoding source is credited wherever its data appears**, on the requirement
  already in the web-client spec for exactly this reason.

Not in scope, deliberately:

- **Using the finer weather data this unlocks.** A correct date and position make an hourly
  window and a forecast worth having; both are `add-granular-weather`, and doing them here
  would mean two changes in one.
- **Reading metadata from anything but the photograph.** No IP geolocation, no browser
  location prompt. The photograph is the only source, so a person who strips metadata has
  actually opted out rather than merely appearing to.
- **A timeline of when things happened.** `add-plant-timeline` needs this and the weather
  change to have anything to draw.

## Capabilities

### New Capabilities

- `image-metadata`: What is read from an uploaded photograph, what is kept, what is
  deliberately discarded, and what happens when there is nothing to read.

### Modified Capabilities

- `photo-storage`: The ordering constraint — metadata is read before normalisation — is a
  property of how a photograph is stored, and the existing requirement about leaving pixels
  alone is where somebody would look for it.
- `diagnosis-wizard`: The upload step gains a detected date and place, both editable, and the
  location question is skipped when the photograph already answered it.

## Impact

- **A fourth external service, on the upload path.** Reverse geocoding is the first thing
  here that runs while somebody is waiting to press a button, rather than inside a
  ninety-second run. It must be fast, optional, and invisible when it fails.
- **Privacy.** This change reads location data out of people's photographs. The precise fix
  is discarded before anything is written, which is the property the whole design rests on:
  a database that never holds it cannot leak it.
- `core/images.py` (reading before normalising), a new `core/metadata.py`,
  `tools/geocoding.py`, `data/models.py` and a migration for the observation's captured date
  and coarse position, `agent/state.py`, `api/routers/runs.py`, `web/`.
- **The evaluation harness must not move.** Golden cases carry no photographs with metadata;
  nothing here is on the harness's path. Verified by running it rather than by reasoning.
