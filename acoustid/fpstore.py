import logging
from dataclasses import dataclass
from typing import List

import requests

from acoustid.config import FpstoreConfig

logger = logging.getLogger(__name__)


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
                "hashes": [h & 0xFFFFFFFF for h in query],
            },
            "limit": limit,
            "fast_mode": fast_mode,
        }
        logger.info(f"Searching fingerprint store: {url} {request_body}")

        response = self.session.post(url, json=request_body)
        if response.status_code != 200:
            logger.error(
                f"Failed to search fingerprint store: {response.status_code} {response.text}"
            )

        results = []
        for result in response.json()["results"]:
            results.append(
                FpstoreSearchResult(
                    fingerprint_id=result["id"],
                    score=result["score"],
                )
            )
        return results
