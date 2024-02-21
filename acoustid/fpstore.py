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

    def _build_search_request(
        self, query: List[int], limit: int, fast_mode: bool, min_score: float
    ) -> requests.Request:
        url = f"{self.base_url}/_search"
        body = {
            "fingerprint": {
                "version": 1,
                "hashes": [h & 0xFFFFFFFF for h in query],
            },
            "limit": limit,
            "fast_mode": fast_mode,
            "min_score": min_score,
        }
        return requests.Request("POST", url, json=body)

    def _parse_search_response(
        self, response: requests.Response
    ) -> List[FpstoreSearchResult]:
        if response.status_code != 200:
            logger.error(
                f"Failed to search fingerprint store: {response.status_code} {response.text}"
            )
            response.raise_for_status()

        results = []
        for result in response.json()["results"]:
            results.append(
                FpstoreSearchResult(
                    fingerprint_id=int(result["id"]),
                    score=float(result["score"]),
                )
            )
        return results

    def search(
        self, query: List[int], limit: int = 10, fast_mode: bool = True,
        min_score: float = 0.0
    ) -> List[FpstoreSearchResult]:
        request = self._build_search_request(query, limit, fast_mode, min_score)
        prepared_request = self.session.prepare_request(request)
        response = self.session.send(prepared_request)
        return self._parse_search_response(response)
