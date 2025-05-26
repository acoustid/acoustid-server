from starlette.testclient import TestClient


def test_search(client: TestClient) -> None:
    response = client.post(
        "/v3/search",
        headers={
            "X-App-Key": "test",
        },
        json={},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {}
