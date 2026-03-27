# Copyright 2025 Helix Technologies Limited
# Licensed under the Apache License, Version 2.0 (see LICENSE file).
"""
Supabase magic link authentication provider for ReplicantX.
"""

import uuid
from typing import Optional, Tuple

from playwright.async_api import BrowserContext

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
            access_token, refresh_token = self._generate_and_verify(email)

            # Use the browser context's APIRequestContext to call the app
            # refresh endpoint — Set-Cookie headers update the browser
            # context cookie jar automatically (Playwright feature).
            request_context = self._browser_context.request
            response = await request_context.post(
                self.app_refresh_endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
                data={
                    "refresh_token": refresh_token,
                },
            )

            if not response.ok:
                body = await response.text()
                raise Exception(
                    f"Failed to call refresh endpoint: "
                    f"{response.status} {response.status_text} — {body}"
                )

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
            access_token, _ = self._generate_and_verify(email)
            self._token = access_token
            return access_token

        except Exception as e:
            raise Exception(f"Supabase magic link authentication failed: {str(e)}")

    def _generate_and_verify(self, email: str) -> Tuple[str, str]:
        """
        Generate a magic link and immediately verify it to obtain session tokens.

        1. Admin generate_link → email_otp (raw OTP)
        2. client.auth.verify_otp with email + token → session

        Returns:
            (access_token, refresh_token)
        """
        link_params: dict = {"type": "magiclink", "email": email}
        if self.redirect_to:
            link_params["options"] = {"redirect_to": self.redirect_to}

        link_resp = self.client.auth.admin.generate_link(link_params)
        props = link_resp.properties

        # Use the actual verification_type from the response — for new
        # users Supabase returns "signup" instead of "magiclink".
        auth_resp = self.client.auth.verify_otp(
            {"type": props.verification_type, "token_hash": props.hashed_token}
        )

        if not auth_resp.session:
            raise Exception("No session returned from OTP verification")

        return auth_resp.session.access_token, auth_resp.session.refresh_token

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
