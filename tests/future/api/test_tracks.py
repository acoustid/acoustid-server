from starlette.testclient import TestClient


def test_list_by_mbid(client: TestClient) -> None:
    response = client.get(
        "/v3/track/list_by_mbid",
        params={"mbid": "38f33829-0a01-4593-b000-c8900902d1e8"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"tracks": []}


def test_list_by_mbid_missing_mbid(client: TestClient) -> None:
    response = client.get(
        "/v3/track/list_by_mbid",
        params={},
    )
    assert response.status_code == 400, response.text


def test_list_by_mbid_invalid_mbid(client: TestClient) -> None:
    response = client.get(
        "/v3/track/list_by_mbid",
        params={"mbid": "abc"},
    )
    assert response.status_code == 400, response.text


def test_list_by_fingerprint(client: TestClient) -> None:
    response = client.get(
        "/v3/track/list_by_fingerprint",
        params={"id": "1"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"tracks": []}


def test_list_by_fingerprint_missing_id(client: TestClient) -> None:
    response = client.get(
        "/v3/track/list_by_fingerprint",
        params={},
    )
    assert response.status_code == 400, response.text


def test_list_by_fingerprint_invalid_id(client: TestClient) -> None:
    response = client.get(
        "/v3/track/list_by_fingerprint",
        params={"id": "abc"},
    )
    assert response.status_code == 400, response.text
