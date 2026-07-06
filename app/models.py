"""Gemini model configuration for local gcloud auth and Cloud Run ADC."""

from __future__ import annotations

import os
import subprocess
from functools import cached_property

from google.adk.models import Gemini
from google.genai import Client, types
from google.oauth2.credentials import Credentials


class GcloudAwareGemini(Gemini):
    """Use a short-lived gcloud token locally and runtime ADC when deployed."""

    @cached_property
    def api_client(self) -> Client:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        location = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")
        kwargs: dict[str, object] = {
            "vertexai": True,
            "project": project,
            "location": location,
            "http_options": types.HttpOptions(retry_options=self.retry_options),
        }
        if os.environ.get("FORMBRIDGE_USE_GCLOUD_AUTH", "").lower() == "true":
            completed = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                check=True,
                capture_output=True,
                text=True,
            )
            token = completed.stdout.strip()
            if not token:
                raise RuntimeError("gcloud returned an empty access token")
            kwargs["credentials"] = Credentials(token=token)
        return Client(**kwargs)
