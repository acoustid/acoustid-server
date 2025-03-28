import logging
from types import TracebackType
from typing import Annotated, Any, TypeVar, overload
from urllib.parse import urljoin

import aiohttp
import msgspec

logger = logging.getLogger(__name__)


UInt32 = Annotated[int, msgspec.Meta(gt=0, lt=2**32)]
UInt64 = Annotated[int, msgspec.Meta(gt=0, lt=2**64)]


class ErrorResponse(msgspec.Struct):
    error: str = msgspec.field(name="e")


class Insert(msgspec.Struct):
    id: UInt32 = msgspec.field(name="i")
    hashes: list[UInt32] = msgspec.field(name="h")


class Delete(msgspec.Struct):
    id: UInt32 = msgspec.field(name="i")


class SetAttribute(msgspec.Struct):
    name: str = msgspec.field(name="n")
    value: UInt64 = msgspec.field(name="v")


class Change(msgspec.Struct):
    insert: Insert | None = msgspec.field(name="i", default=None)
    delete: Delete | None = msgspec.field(name="d", default=None)
    set_attribute: SetAttribute | None = msgspec.field(name="s", default=None)


class UpdateRequest(msgspec.Struct):
    changes: list[Change] = msgspec.field(name="c")


class SearchRequest(msgspec.Struct):
    query: list[int] = msgspec.field(name="q")
    timeout: int | None = msgspec.field(name="t", default=None)
    limit: int | None = msgspec.field(name="l", default=None)


class SearchResult(msgspec.Struct):
    id: UInt32 = msgspec.field(name="i")
    score: int = msgspec.field(name="s")


class SearchResponse(msgspec.Struct):
    results: list[SearchResult] = msgspec.field(name="r")


class GetIndexResponse(msgspec.Struct):
    version: int = msgspec.field(name="v")
    segments: int = msgspec.field(name="s")
    docs: int = msgspec.field(name="d")
    attributes: dict[str, int] = msgspec.field(name="a")


class EmptyResponse(msgspec.Struct):
    pass


class UpdateFingerprintRequest(msgspec.Struct):
    hashes: list[int] = msgspec.field(name="h")


class GetFingerprintResponse(msgspec.Struct):
    version: int = msgspec.field(name="v")


class FingerprintIndexClientError(Exception):
    """Base exception for fingerprint index client errors"""


class BatchUpdate:
    def __init__(self) -> None:
        self.changes: list[Change] = []

    def insert(self, id: int, hashes: list[int]) -> None:
        self.changes.append(
            Change(
                insert=Insert(
                    id=id,
                    hashes=hashes,
                )
            )
        )

    def delete(self, id: int) -> None:
        self.changes.append(
            Change(
                delete=Delete(
                    id=id,
                )
            )
        )

    def set_attribute(self, name: str, value: int) -> None:
        self.changes.append(
            Change(
                set_attribute=SetAttribute(
                    name=name,
                    value=value,
                )
            )
        )


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

    T = TypeVar("T", bound=msgspec.Struct)

    @overload
    async def _request(  # NOQA: E704
        self,
        method: str,
        path: str,
        *,
        expected_status: list[int],
        expected_response: None,
        data: msgspec.Struct | None = None,
        timeout: float | None = None,
    ) -> tuple[int, None]: ...

    @overload
    async def _request(  # NOQA: E704
        self,
        method: str,
        path: str,
        *,
        expected_status: list[int],
        expected_response: type[T],
        data: msgspec.Struct | None = None,
        timeout: float | None = None,
    ) -> tuple[int, T]: ...

    async def _request(
        self,
        method: str,
        path: str,
        *,
        expected_status: list[int],
        expected_response: type[T] | None,
        data: msgspec.Struct | None = None,
        timeout: float | None = None,
    ) -> tuple[int, T | None]:
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
            "headers": {"Accept": "application/vnd.msgpack"},
        }
        if data is not None:
            kwargs["data"] = msgspec.msgpack.encode(data)
            kwargs["headers"]["Content-Type"] = "application/vnd.msgpack"

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

                if expected_response is None:
                    return status, None

                content = await response.read()
                return status, msgspec.msgpack.decode(content, type=expected_response)

        except aiohttp.ClientError as e:
            logger.exception("Error making request")
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
            "HEAD",
            f"/{index_name}",
            expected_status=[200, 404],
            expected_response=None,
        )
        return status == 200

    async def get_index_info(self, index_name: str) -> GetIndexResponse:
        """Get information about an index

        Args:
            index_name: Name of the index

        Returns:
            Dictionary with index information
        """
        _, result = await self._request(
            "GET",
            f"/{index_name}",
            expected_status=[200],
            expected_response=GetIndexResponse,
        )
        return result

    async def create_index(self, index_name: str) -> None:
        """Create a new index

        Args:
            index_name: Name of the index

        Returns:
            Response data
        """
        _, _ = await self._request(
            "PUT",
            f"/{index_name}",
            expected_status=[200, 201],
            expected_response=EmptyResponse,
        )

    async def delete_index(self, index_name: str) -> None:
        """Delete an index

        Args:
            index_name: Name of the index

        Returns:
            Response data
        """
        _, _ = await self._request(
            "DELETE",
            f"/{index_name}",
            expected_status=[200],
            expected_response=EmptyResponse,
        )

    # Fingerprint management methods

    async def update(
        self,
        index_name: str,
        changes: BatchUpdate | list[Insert | Delete | SetAttribute],
    ) -> None:
        """Perform multiple operations on an index

        Args:
            index_name: Name of the index
            changes: List of changes to apply (insert/delete operations)

        Returns:
            Response data
        """
        if isinstance(changes, BatchUpdate):
            wrapped_changes = changes.changes
        else:
            wrapped_changes = []
            for change in changes:
                if isinstance(change, Insert):
                    wrapped_changes.append(Change(insert=change))
                elif isinstance(change, Delete):
                    wrapped_changes.append(Change(delete=change))
                elif isinstance(change, SetAttribute):
                    wrapped_changes.append(Change(set_attribute=change))

        _, _ = await self._request(
            "POST",
            f"/{index_name}/_update",
            data=UpdateRequest(changes=wrapped_changes),
            expected_status=[200],
            expected_response=EmptyResponse,
        )

    async def search(
        self,
        index_name: str,
        query: list[int],
        timeout: int | None = None,
        limit: int | None = None,
    ) -> SearchResponse:
        """Search for a fingerprint in the index

        Args:
            index_name: Name of the index
            query: List of hash values
            timeout: Search timeout in seconds
            limit: Maximum number of results to return

        Returns:
            Search results
        """
        _, result = await self._request(
            "POST",
            f"/{index_name}/_search",
            data=SearchRequest(query=query, timeout=timeout, limit=limit),
            expected_status=[200],
            expected_response=SearchResponse,
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
            "HEAD",
            f"/{index_name}/{fingerprint_id}",
            expected_status=[200, 404],
            expected_response=None,
        )
        return status == 200

    async def get_fingerprint_info(
        self, index_name: str, fingerprint_id: int
    ) -> GetFingerprintResponse:
        """Get information about a fingerprint

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint

        Returns:
            Fingerprint information
        """
        _, result = await self._request(
            "GET",
            f"/{index_name}/{fingerprint_id}",
            expected_status=[200],
            expected_response=GetFingerprintResponse,
        )
        return result

    async def update_fingerprint(
        self, index_name: str, fingerprint_id: int, hashes: list[int]
    ) -> None:
        """Update a single fingerprint

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint
            hashes: List of hash values

        Returns:
            Response data
        """
        _, _ = await self._request(
            "PUT",
            f"/{index_name}/{fingerprint_id}",
            data=UpdateFingerprintRequest(hashes=hashes),
            expected_status=[200],
            expected_response=EmptyResponse,
        )

    async def delete_fingerprint(self, index_name: str, fingerprint_id: int) -> None:
        """Delete a single fingerprint

        Args:
            index_name: Name of the index
            fingerprint_id: ID of the fingerprint

        Returns:
            Response data
        """
        _, _ = await self._request(
            "DELETE",
            f"/{index_name}/{fingerprint_id}",
            expected_status=[200],
            expected_response=EmptyResponse,
        )
