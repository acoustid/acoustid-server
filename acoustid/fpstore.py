from dataclasses import dataclass
from typing import List

import requests

from acoustid.config import FpstoreConfig


@dataclass(frozen=True)
class FpstoreSearchResult:
    fingerprint_id: int
    score: float


class FpstoreClient:
    def __init__(self, cfg: FpstoreConfig) -> None:
        self.base_url = f"http://{cfg.host}:{cfg.port}/v1/fingerprint"
        self.session = requests.Session()

    def __enter__(self) -> "FpstoreClient":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def close(self) -> None:
        self.session.close()

    def search(
        self, query: List[int], limit: int = 10, fast_mode: bool = True
    ) -> List[FpstoreSearchResult]:
        url = f"{self.base_url}/_search"
        request_body = {
            "fingerprint": {
                "version": 1,
                "hashes": query,
            },
            "limit": limit,
            "fast_mode": fast_mode,
        }

        response = self.session.get(url, json=request_body)
        response.raise_for_status()

        results = []
        for result in response.json()["results"]:
            results.append(
                FpstoreSearchResult(
                    fingerprint_id=result["id"],
                    score=result["score"],
                )
            )
        return results
