"""Taking your data out.

Read from the archive rather than from the service's return value wherever possible: the
promise is that somebody can open this file without the application, so the tests open it the
way they would.
"""

import io
import json
import zipfile

from services.export import MANIFEST, PHOTOGRAPHS
from tests.accounts import populate


def _archive(response) -> zipfile.ZipFile:
    assert response.status_code == 200
    return zipfile.ZipFile(io.BytesIO(response.content))


def _manifest(response) -> dict:
    return json.loads(_archive(response).read(MANIFEST))


class TestWhatIsInIt:
    def test_it_is_a_readable_archive(self, client, db, seeded):
        response = client.get("/api/v1/me/export")

        assert MANIFEST in _archive(response).namelist()

    def test_the_account_itself(self, client, db, owner, seeded):
        manifest = _manifest(client.get("/api/v1/me/export"))

        assert manifest["account"]["id"] == str(owner)
        assert manifest["account"]["consent_version"]
        assert "exported_at" in manifest

    def test_the_plants_and_their_history(self, client, db, seeded):
        manifest = _manifest(client.get("/api/v1/me/export"))

        plant = manifest["plants"][0]
        assert plant["name"] == "Kitchen basil"
        assert plant["observations"]
        assert plant["diagnoses"]
        assert plant["treatment_steps"]
        assert plant["conversation"]

    def test_the_photographs(self, client, db, seeded):
        """The bytes, not just the references. A manifest naming photographs it does not
        contain is a manifest that describes somebody else's file."""
        archive = _archive(client.get("/api/v1/me/export"))
        stored = [name for name in archive.namelist() if name.startswith(f"{PHOTOGRAPHS}/")]

        assert stored
        assert archive.read(stored[0]) == bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"pixels"

    def test_every_photograph_the_manifest_mentions_is_present(self, client, db, seeded):
        archive = _archive(client.get("/api/v1/me/export"))
        manifest = json.loads(archive.read(MANIFEST))

        mentioned = {
            key
            for plant in manifest["plants"]
            for observation in plant["observations"]
            for key in observation["photographs"]
        }

        assert mentioned
        for key in mentioned:
            assert f"{PHOTOGRAPHS}/{key}" in archive.namelist()

    def test_no_password_hash_or_token_leaves_with_it(self, client, db, seeded):
        """An export is a file somebody will keep, mail to themselves, and drop in a folder.
        It should not carry anything that could be used to become them."""
        body = _archive(client.get("/api/v1/me/export")).read(MANIFEST).decode()

        assert "password_hash" not in body
        assert "token_hash" not in body


class TestItReadsWithoutTheApplication:
    def test_a_diagnosis_names_its_plant(self, client, db, seeded):
        """Not only `plant_id: 01a0…`. An archive whose records reference each other by
        identifier alone is complete and unreadable."""
        manifest = _manifest(client.get("/api/v1/me/export"))

        diagnosis = manifest["plants"][0]["diagnoses"][0]
        assert diagnosis["plant"] == "Kitchen basil"

    def test_a_treatment_step_names_its_plant(self, client, db, seeded):
        manifest = _manifest(client.get("/api/v1/me/export"))

        assert manifest["plants"][0]["treatment_steps"][0]["plant"] == "Kitchen basil"

    def test_a_message_says_who_said_it(self, client, db, seeded):
        manifest = _manifest(client.get("/api/v1/me/export"))

        message = manifest["plants"][0]["conversation"][0]
        assert message["who"] in {"user", "assistant", "tool"}
        assert message["said"]

    def test_the_dates_are_readable(self, client, db, seeded):
        manifest = _manifest(client.get("/api/v1/me/export"))

        assert manifest["plants"][0]["created_at"].startswith("2026-")


class TestWhoseDataItIs:
    def test_nothing_belonging_to_another_owner(self, client, db, owner, seeded):
        """A second populated account exists. None of it may appear."""
        stranger = populate(db)
        db.commit()

        manifest = _manifest(client.get("/api/v1/me/export"))

        assert manifest["account"]["id"] == str(owner)
        assert str(stranger.plant_id) not in json.dumps(manifest)
        assert stranger.email not in json.dumps(manifest)

    def test_an_account_with_nothing_in_it(self, client, db, owner):
        """Valid and empty rather than an error. Somebody who has created nothing is still
        entitled to be told that."""
        manifest = _manifest(client.get("/api/v1/me/export"))

        assert manifest["plants"] == []
        assert manifest["learned_about_you"] == []
        assert manifest["account"]["id"] == str(owner)

    def test_signed_out(self, client):
        client.headers.pop("Authorization", None)

        assert client.get("/api/v1/me/export").status_code == 401


class TestTheResponse:
    def test_it_is_named_so_a_browser_can_save_it(self, client, db, owner, seeded):
        response = client.get("/api/v1/me/export")

        disposition = response.headers["content-disposition"]
        assert disposition.startswith("attachment;")
        assert f"plantopia-export-{owner}.zip" in disposition

    def test_it_says_what_it_is(self, client, db, seeded):
        assert client.get("/api/v1/me/export").headers["content-type"] == "application/zip"


class TestTheSizeGuard:
    def test_an_account_over_the_limit_is_refused(self, client, db, api_settings, seeded):
        """Refused rather than truncated: half of somebody's data in a file labelled as all
        of it is worse than being told to ask for help."""
        api_settings.max_export_bytes = 1

        response = client.get("/api/v1/me/export")

        assert response.status_code == 413
        assert "too much" in response.json()["title"].lower()

    def test_an_account_within_it_is_served(self, client, db, api_settings, seeded):
        api_settings.max_export_bytes = 10 * 1024 * 1024

        assert client.get("/api/v1/me/export").status_code == 200
