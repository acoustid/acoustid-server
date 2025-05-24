def test_search_success(client):
    response = client.post(
        "/v2/fingerprint/_search",
        json={"fingerprint_id": 123},
    )
    assert response.status_code == 200
    assert response.text == "OK"
