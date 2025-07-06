# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
HTTP client with retry logic and latency timing for ReplicantX.

This module provides a robust HTTP client wrapper around httpx with automatic
retry, exponential backoff, and request timing functionality.
"""

import asyncio
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field


class HTTPResponse(BaseModel):
    """Response from HTTP request with timing information."""
    
    status_code: int = Field(..., description="HTTP status code")
    content: str = Field(..., description="Response content as string")
    headers: Dict[str, str] = Field(default_factory=dict, description="Response headers")
    latency_ms: float = Field(..., description="Request latency in milliseconds")
    url: str = Field(..., description="URL that was requested")
    method: str = Field(..., description="HTTP method used")


class HTTPClient:
    """HTTP client with retry logic and timing."""
    
    def __init__(
        self,
        base_url: str = "",
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        backoff_factor: float = 2.0,
        default_headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize the HTTP client.
        
        Args:
            base_url: Base URL for all requests
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries in seconds
            backoff_factor: Factor to multiply delay by on each retry
            default_headers: Default headers to include in all requests
        """
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.backoff_factor = backoff_factor
        self.default_headers = default_headers or {}
        
        # Create httpx client with default configuration
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
        )
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    def _build_url(self, path: str) -> str:
        """Build full URL from base URL and path.
        
        Args:
            path: URL path or full URL
            
        Returns:
            Complete URL
        """
        if path.startswith(('http://', 'https://')):
            return path
        return urljoin(self.base_url, path)
    
    def _merge_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """Merge default headers with request-specific headers.
        
        Args:
            headers: Request-specific headers
            
        Returns:
            Merged headers dictionary
        """
        merged = self.default_headers.copy()
        if headers:
            merged.update(headers)
        return merged
    
    async def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> HTTPResponse:
        """Make a single HTTP request with timing.
        
        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            json: JSON payload
            data: Form data or raw body
            params: Query parameters
            
        Returns:
            HTTP response with timing information
            
        Raises:
            httpx.HTTPError: If request fails
        """
        full_url = self._build_url(url)
        merged_headers = self._merge_headers(headers)
        
        start_time = time.time()
        
        try:
            response = await self._client.request(
                method=method,
                url=full_url,
                headers=merged_headers,
                json=json,
                data=data,
                params=params,
            )
            
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            # Try to get text content, fall back to string representation
            try:
                content = response.text
            except Exception:
                content = str(response.content)
            
            return HTTPResponse(
                status_code=response.status_code,
                content=content,
                headers=dict(response.headers),
                latency_ms=latency_ms,
                url=full_url,
                method=method.upper(),
            )
            
        except Exception as e:
            end_time = time.time()
            latency_ms = (end_time - start_time) * 1000
            
            # Re-raise with timing information preserved
            raise httpx.HTTPError(
                f"Request failed after {latency_ms:.2f}ms: {str(e)}"
            ) from e
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> HTTPResponse:
        """Make HTTP request with retry logic.
        
        Args:
            method: HTTP method
            url: Request URL
            headers: Request headers
            json: JSON payload
            data: Form data or raw body
            params: Query parameters
            max_retries: Override default max retries
            
        Returns:
            HTTP response with timing information
            
        Raises:
            httpx.HTTPError: If all retries fail
        """
        retries = max_retries if max_retries is not None else self.max_retries
        delay = self.retry_delay
        last_exception = None
        
        for attempt in range(retries + 1):
            try:
                return await self._make_request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=json,
                    data=data,
                    params=params,
                )
            except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                
                if attempt < retries:
                    await asyncio.sleep(delay)
                    delay *= self.backoff_factor
                else:
                    # Final attempt failed
                    raise e
        
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise httpx.HTTPError("Unexpected error in retry logic")
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> HTTPResponse:
        """Make GET request.
        
        Args:
            url: Request URL
            headers: Request headers
            params: Query parameters
            max_retries: Override default max retries
            
        Returns:
            HTTP response with timing information
        """
        return await self._request_with_retry(
            method="GET",
            url=url,
            headers=headers,
            params=params,
            max_retries=max_retries,
        )
    
    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> HTTPResponse:
        """Make POST request.
        
        Args:
            url: Request URL
            headers: Request headers
            json: JSON payload
            data: Form data or raw body
            params: Query parameters
            max_retries: Override default max retries
            
        Returns:
            HTTP response with timing information
        """
        return await self._request_with_retry(
            method="POST",
            url=url,
            headers=headers,
            json=json,
            data=data,
            params=params,
            max_retries=max_retries,
        )
    
    async def put(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> HTTPResponse:
        """Make PUT request.
        
        Args:
            url: Request URL
            headers: Request headers
            json: JSON payload
            data: Form data or raw body
            params: Query parameters
            max_retries: Override default max retries
            
        Returns:
            HTTP response with timing information
        """
        return await self._request_with_retry(
            method="PUT",
            url=url,
            headers=headers,
            json=json,
            data=data,
            params=params,
            max_retries=max_retries,
        )
    
    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        max_retries: Optional[int] = None,
    ) -> HTTPResponse:
        """Make DELETE request.
        
        Args:
            url: Request URL
            headers: Request headers
            params: Query parameters
            max_retries: Override default max retries
            
        Returns:
            HTTP response with timing information
        """
        return await self._request_with_retry(
            method="DELETE",
            url=url,
            headers=headers,
            params=params,
            max_retries=max_retries,
        ) 