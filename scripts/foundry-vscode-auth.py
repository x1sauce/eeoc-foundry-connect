#!/usr/bin/env python3
"""Issue an Entra token using the signed-in VS Code Azure Resources identity.

Never writes tokens to files. `token` prints ONLY the token to stdout for OMP's
`!command` credential resolution. `check` prints no credential data.
"""
from __future__ import annotations

import argparse
import os
import sys

FOUNDRY_SCOPE = "https://ai.azure.com/.default"
ARM_SCOPE = "https://management.azure.com/.default"


def create_vscode_credential(tenant_id: str | None = None):
    """Create VS Code broker credential; SDK imports are lazy for offline tests."""
    try:
        from azure.identity import VisualStudioCodeCredential
    except ImportError as exc:
        raise RuntimeError(
            "Missing approved Python dependencies: azure-identity and azure-identity-broker. "
            "Ask IT before installing them on a managed device."
        ) from exc
    kwargs = {"tenant_id": tenant_id} if tenant_id else {}
    return VisualStudioCodeCredential(**kwargs)


def request_token(*, tenant_id: str | None = None, scope: str = FOUNDRY_SCOPE) -> str:
    credential = create_vscode_credential(tenant_id)
    try:
        token = credential.get_token(scope).token
        if not token:
            raise RuntimeError("VS Code credential returned an empty access token")
        return token
    finally:
        credential.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Azure Resources (VS Code) Entra token helper, no Azure CLI")
    parser.add_argument("action", choices=("token", "check"), help="token: print bearer token ONLY for OMP; check: safe status")
    parser.add_argument("--tenant-id", default=os.environ.get("AZURE_TENANT_ID"))
    args = parser.parse_args()
    try:
        token = request_token(tenant_id=args.tenant_id)
    except Exception as exc:
        print(
            f"VS Code Entra authentication failed ({type(exc).__name__}). "
            "Verify Azure Resources sign-in, the selected tenant, the broker dependency, and IT policy. "
            "No token was saved.",
            file=sys.stderr,
        )
        return 1
    if args.action == "token":
        # OMP consumes stdout. Never log, store, or paste this output.
        sys.stdout.write(token + "\n")
    else:
        print("VS Code Entra credential: token acquisition OK (resource authorization not yet verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
