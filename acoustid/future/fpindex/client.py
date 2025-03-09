import logging
from types import TracebackType
from typing import Any
from urllib.parse import urljoin

import aiohttp

logger = logging.getLogger(__name__)


class FingerprintIndexClientError(Exception):
    """Base exception for fingerprint index client errors"""


class FingerprintIndexClient:
    """Asyncio client for the acoustid-index HTTP API"""

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        """Initialize the client with the base URL of the index service

        Args:
            base_url: Base URL of the acoustid-index service
            timeout: Default timeout for HTTP requests in seconds
        """
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.session = aiohttp.ClientSession()

    async def __aenter__(self) -> "FingerprintIndexClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the HTTP session"""
        await self.session.close()

    def _url(self, path: str) -> str:
        """Build a URL for the given path"""
        return urljoin(self.base_url, path)

    async def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        timeout: float | None = None,
        expected_status: list[int] | None = None,
    ) -> tuple[int, Any]:
        """Send HTTP request and return the response

        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path
            data: Optional JSON data for the request
            timeout: Request timeout in seconds
            expected_status: List of expected HTTP status codes

        Returns:
            Tuple of (status_code, response_data)
        """
        url = self._url(path)

        kwargs: dict[str, Any] = {
            "timeout": aiohttp.ClientTimeout(total=timeout or self.timeout),
        }
        if data is not None:
            kwargs["json"] = data

        try:
            async with self.session.request(method, url, **kwargs) as response:
                status = response.status

                if expected_status and status not in expected_status:
                    body = await response.text()
                    logger.error(
                        "Unexpected status %s for %s %s: %s", status, method, url, body
                    )
                    raise FingerprintIndexClientError(
                        f"Unexpected status {status}: {body}"
                    )

                if (
                    response.content_length
                    and response.content_type == "application/json"
                ):
                    result = await response.json()
                else:
                    result = await response.text()

                return status, result
        except aiohttp.ClientError as e:
            logger.error("Error making request: %s", e)
            raise FingerprintIndexClientError(f"Error making request: {e}") from e

    # Index management methods

    async def index_exists(self, index_name: str) -> bool:
        """Check if index exists

        Args:
            index_name: Name of the index

        Returns:
            True if index exists, False otherwise
        """
        status, _ = await self._request(
            "HEAD", f"/{index_name}", expected_status=[200, 404]
        )
        return status == 200

    async def get_index_info(self, index_name: str) -> dict:
        """Get information about an index

        Args:
            index_name: Name of the index

        Returns:
            Dictionary with index information
        """
        _, result = await self._request("GET", f"/{index_name}", expected_status=[200])
        return result

    async def create_index(self, index_name: str) -> dict:
        """Create a new index

        Args:
            index_name: Name of the index

        Returns:
            Response data
        """
        _, result = await self._request(
            "PUT", f"/{index_name}", expected_status=[200, 201]
        )
        return result

    async def delete_index(self, index_name: str) -> dict:
        """Delete an index

        Args:
            index_name: Name of the index

        Returns:
            Response data
        """
        _, result = await self._request(
            "DELETE", f"/{index_name}", expected_status=[200]
        )
        return result

    # Fingerprint management methods

    async def update(self, index_name: str, changes: list[dict[str, Any]]) -> dict:
        """Perform multiple operations on an index

        Args:
            index_name: Name of the index
            changes: List of changes to apply (insert/delete operations)

        Returns:
            Response data
        """
        data = {"changes": changes}
        _, result = await self._request(
            "POST", f"/{index_name}/_update", data=data, expected_status=[200]
        )
        return result

    async def search(
        self, index_name: str, query: list[int], timeout: float | None = None
    ) -> dict:
        """Search for a fingerprint in the index

        Args:
            index_name: Name of the index
            query: List of hash values
            timeout: Search timeout in seconds

        Returns:
            Search results
        """
        data: dict[str, Any] = {"query": query}
        if timeout is not None:
            data["timeout"] = timeout

        _, result = await self._request(
            "POST", f"/{index_name}/_search", data=data, expected_status=[200]
        )
        return result

    async def fingerprint_exists(self, index_name: str, fingerprint_id: int) -> bool:
        """Check if fingerprint exists

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint

        Returns:
            True if fingerprint exists, False otherwise
        """
        status, _ = await self._request(
            "HEAD", f"/{index_name}/{fingerprint_id}", expected_status=[200, 404]
        )
        return status == 200

    async def get_fingerprint_info(self, index_name: str, fingerprint_id: int) -> dict:
        """Get information about a fingerprint

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint

        Returns:
            Fingerprint information
        """
        _, result = await self._request(
            "GET", f"/{index_name}/{fingerprint_id}", expected_status=[200]
        )
        return result

    async def update_fingerprint(
        self, index_name: str, fingerprint_id: int, hashes: list[int]
    ) -> dict:
        """Update a single fingerprint

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint
            hashes: List of hash values

        Returns:
            Response data
        """
        data = {"hashes": hashes}
        _, result = await self._request(
            "PUT", f"/{index_name}/{fingerprint_id}", data=data, expected_status=[200]
        )
        return result

    async def delete_fingerprint(self, index_name: str, fingerprint_id: int) -> dict:
        """Delete a single fingerprint

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint

        Returns:
            Response data
        """
        _, result = await self._request(
            "DELETE", f"/{index_name}/{fingerprint_id}", expected_status=[200]
        )
        return result

    # System utility methods

    async def healthcheck(self, index_name: str | None = None) -> dict:
        """Get service health status

        Args:
            index_name: Optional index name for index-specific health check

        Returns:
            Health status information
        """
        path = f"/{index_name}/_health" if index_name else "/_health"
        _, result = await self._request("GET", path, expected_status=[200])
        return result

    async def metrics(self) -> str:
        """Get Prometheus metrics

        Returns:
            Metrics in Prometheus format
        """
        _, result = await self._request("GET", "/_metrics", expected_status=[200])
        return result
