"""Serving a photograph."""

from core.ids import new_id

PNG = bytes([137, 80, 78, 71, 13, 10, 26, 10]) + b"pixels"


def test_a_photograph_is_served_with_its_content_type(client, seeded):
    response = client.get(f"/api/v1/photos/{seeded['photo_key']}")

    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers["content-type"] == "image/png"


def test_an_unknown_key_is_not_found(client):
    assert client.get(f"/api/v1/photos/{new_id()}").status_code == 404


def test_a_key_that_is_not_a_key_is_refused(client):
    assert client.get("/api/v1/photos/not-a-key").status_code == 422
