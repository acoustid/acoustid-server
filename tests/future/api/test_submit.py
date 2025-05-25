from starlette.testclient import TestClient

TEST_FINGERPRINT = (
    "AQAAO1PSRBmTJXjgC_5I9Mnx48fxPOiTJWjkiAX07MEPXiKaJ8nRHw-eF-iPJk-OH8elJT"
    "8-Hf3BO4KP_Ej8wz9-BdaPPkmOy8eD53hyPEyC5svQH_rxPLiI5snRLzieHz96-LnQA8-D"
    "--jxCOYNEIlRTBjOnECCMAOEUI4IqKBBTCIggJGEMDCIUYII5gwRTAjCmZDCIMEYYYQQQh"
    "zARiElIiBCgQY"
)


def test_submit(client: TestClient) -> None:
    response = client.post(
        "/v3/submit",
        headers={
            "X-App-Key": "test",
            "X-User-Key": "test",
        },
        json={
            "submissions": [
                {
                    "fingerprint": TEST_FINGERPRINT,
                    "duration": 10,
                    "mbid": "3dbf7643-cba5-4e6c-a62b-2dc5b2300666",
                    "metadata": {
                        "artist": "Artist",
                        "title": "Title",
                        "album": "Album",
                        "album_artist": "Album Artist",
                        "track_no": 1,
                        "disc_no": 1,
                        "year": 2021,
                    },
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json() == {"submissions": [{"id": 1, "status": "pending"}]}
