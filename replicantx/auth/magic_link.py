# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Supabase magic link authentication provider for ReplicantX.
"""

import uuid
from typing import Optional
from playwright.async_api import BrowserContext, APIRequestContext

from replicantx.auth.base import AuthBase


class SupabaseMagicLinkAuth(AuthBase):
    """
    Supabase magic link authentication using admin API.

    Generates a magic link, verifies it to get tokens, and sets
    cookies in the browser context (for browser mode) or returns
    auth headers (for API mode).
    """

    def __init__(self, config):
        """
        Initialize the Supabase magic link auth provider.

        Config fields:
            project_url: Supabase project URL
            service_role_key: Service role key (admin)
            user_mode: 'generated' or 'fixed'
            email: Email address (required if user_mode='fixed')
            redirect_to: Optional redirect URL for magic link
            app_refresh_endpoint: App endpoint to set httpOnly cookies
        """
        import supabase

        self.project_url = config.project_url
        self.service_role_key = config.service_role_key
        self.user_mode = config.user_mode or "generated"
        self.email = config.email
        self.redirect_to = config.redirect_to
        self.app_refresh_endpoint = config.app_refresh_endpoint

        # Initialize Supabase client with service role key
        self.client = supabase.Client(self.project_url, self.service_role_key)

        self._token = None
        self._browser_context = None
        self._generated_email = None

    async def authenticate(self) -> str:
        """
        Authenticate using Supabase magic link flow.

        Returns:
            Access token

        Raises:
            Exception: If authentication fails
        """
        # Determine email
        if self.user_mode == "generated":
            # Generate unique email
            self._generated_email = f"replicantx+{uuid.uuid4().hex[:12]}@replicantx.org"
            email = self._generated_email
        else:  # fixed
            email = self.email

        # Generate magic link
        if self._browser_context:
            # Browser mode: use browser context to set cookies
            return await self._authenticate_browser_mode(email)
        else:
            # API mode: just get the token
            return await self._authenticate_api_mode(email)

    async def _authenticate_browser_mode(self, email: str) -> str:
        """
        Authenticate for browser mode.

        Generates magic link, verifies it, and sets cookies via the app refresh endpoint.

        Args:
            email: Email address to authenticate

        Returns:
            Access token
        """
        if not self._browser_context:
            raise RuntimeError("Browser context not set. Call set_browser_context() first.")

        try:
            # Generate magic link using Supabase admin API
            from supabase import __version__ as supabase_version

            # Use the admin API to generate a magic link
            # This requires the service role key
            magic_link_data = self.client.auth.admin.generate_link(
                type="magiclink",
                email=email,
                options={"redirect_to": self.redirect_to} if self.redirect_to else None,
            )

            # Extract the access token from the magic link
            # The magic link contains an access_token in the URL fragment or query params
            magic_link_url = magic_link_data.action_link
            access_token = self._extract_token_from_link(magic_link_url)

            if not access_token:
                raise Exception("Could not extract access token from magic link")

            # Use the browser context's APIRequestContext to call the app refresh endpoint
            # This will set the httpOnly cookies in the browser context
            request_context = self._browser_context.request

            # Call the app refresh endpoint with the access token
            # The endpoint should set httpOnly cookies (access_token, refresh_token)
            refresh_url = self.app_refresh_endpoint
            response = await request_context.post(
                refresh_url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )

            if not response.ok:
                raise Exception(
                    f"Failed to call refresh endpoint: {response.status} {response.status_text}"
                )

            # Store the access token
            self._token = access_token

            return access_token

        except Exception as e:
            raise Exception(f"Supabase magic link authentication failed: {str(e)}")

    async def _authenticate_api_mode(self, email: str) -> str:
        """
        Authenticate for API mode.

        Generates magic link and verifies it to get tokens.

        Args:
            email: Email address to authenticate

        Returns:
            Access token
        """
        try:
            # Generate magic link
            magic_link_data = self.client.auth.admin.generate_link(
                type="magiclink",
                email=email,
                options={"redirect_to": self.redirect_to} if self.redirect_to else None,
            )

            # Extract the access token
            magic_link_url = magic_link_data.action_link
            access_token = self._extract_token_from_link(magic_link_url)

            if not access_token:
                raise Exception("Could not extract access token from magic link")

            self._token = access_token
            return access_token

        except Exception as e:
            raise Exception(f"Supabase magic link authentication failed: {str(e)}")

    def _extract_token_from_link(self, magic_link_url: str) -> Optional[str]:
        """
        Extract access token from magic link URL.

        Args:
            magic_link_url: Magic link URL

        Returns:
            Access token or None
        """
        import urllib.parse

        # Parse the URL
        parsed = urllib.parse.urlparse(magic_link_url)

        # Check fragment (for hash-based tokens)
        if parsed.fragment:
            fragment_params = urllib.parse.parse_qs(parsed.fragment)
            if "access_token" in fragment_params:
                return fragment_params["access_token"][0]

        # Check query parameters
        if parsed.query:
            query_params = urllib.parse.parse_qs(parsed.query)
            if "access_token" in query_params:
                return query_params["access_token"][0]

        return None

    def get_headers(self) -> dict:
        """
        Get authentication headers for API requests.

        Returns:
            Dictionary of headers
        """
        headers = {
            "Content-Type": "application/json",
        }

        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        return headers

    def set_browser_context(self, context: BrowserContext):
        """
        Set the browser context for cookie management.

        Args:
            context: Playwright browser context
        """
        self._browser_context = context

    @property
    def generated_email(self) -> Optional[str]:
        """Get the generated email (if user_mode='generated')."""
        return self._generated_email

    def invalidate_token(self):
        """Invalidate the cached token."""
        self._token = None
