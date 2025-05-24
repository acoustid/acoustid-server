
def test_get_fingerprint_success(client):
    response = client.post(
        "/v2/fingerprint/_get",
        json={"fingerprint_id": 123},
    )
    assert response.status_code == 200
    assert response.text == "123"


def test_get_fingerprint_missing_id(client):
    response = client.post(
        "/v2/fingerprint/_get",
        json={},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "Object missing required field `fingerprint_id`"


def test_get_fingerprint_invalid_json(client):
    response = client.post(
        "/v2/fingerprint/_get",
        data="invalid json",
    )
    assert response.status_code == 400
    assert response.json()["error"] == "JSON is malformed: invalid character (byte 0)"
