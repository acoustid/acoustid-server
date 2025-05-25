from starlette.testclient import TestClient


def test_list_by_mbid(client: TestClient) -> None:
    response = client.get("/v3/track/list_by_mbid", params={"mbid": "38f33829-0a01-4593-b000-c8900902d1e8"})
    assert response.status_code == 200


def test_list_by_fingerprint(client: TestClient) -> None:
    response = client.get("/v3/track/list_by_fingerprint", params={"id": "b700e9ff-c8b0-4563-8033-e073b886be56"})
    assert response.status_code == 200
