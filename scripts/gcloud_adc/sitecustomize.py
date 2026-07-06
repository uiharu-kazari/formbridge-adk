"""Opt-in google.auth adapter for local agents-cli evaluation commands.

Activate only with:
    PYTHONPATH="$PWD/scripts/gcloud_adc" agents-cli eval ...

Cloud Run does not use this adapter; it receives normal runtime ADC.
"""

from __future__ import annotations

import os
import subprocess

import google.auth
from google.oauth2.credentials import Credentials


def _gcloud_default(scopes=None, request=None, quota_project_id=None, **kwargs):
    del scopes, request, quota_project_id, kwargs
    completed = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        check=True,
        capture_output=True,
        text=True,
    )
    token = completed.stdout.strip()
    if not token:
        raise RuntimeError("gcloud returned an empty access token")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0140113557")
    return Credentials(token=token), project


google.auth.default = _gcloud_default
