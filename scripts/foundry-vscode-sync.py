#!/usr/bin/env python3
"""No-Azure-CLI Foundry OMP sync using VS Code Azure Resources credentials.

Reads Azure Resource Manager resources with GET only. Keeps the original
foundry-sync.py as the model/YAML implementation to avoid duplicating metadata
and to preserve other providers. Nothing is written unless --apply is specified.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shlex
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_VERSION = "2025-06-01"
ARM_BASE = "https://management.azure.com"
ARM_SCOPE = "https://management.azure.com/.default"
DEFAULT_ENDPOINT = "https://aif-eeoc-daes-dev.services.ai.azure.com"
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
RG_RE = re.compile(r"/resourceGroups/([^/]+)/", re.IGNORECASE)


def legacy_sync():
    source = Path(__file__).with_name("foundry-sync.py")
    if not source.is_file():
        raise RuntimeError("Place this file alongside the existing scripts/foundry-sync.py (v1.2.0).")
    spec = importlib.util.spec_from_file_location("eeoc_legacy_foundry_sync", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load original foundry-sync.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_credential(tenant_id: str | None = None):
    try:
        from azure.identity import VisualStudioCodeCredential
    except ImportError as exc:
        raise RuntimeError(
            "azure-identity and azure-identity-broker are required and must be IT-approved."
        ) from exc
    return VisualStudioCodeCredential(**({"tenant_id": tenant_id} if tenant_id else {}))


def validate_arm_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc.lower() != "management.azure.com":
        raise RuntimeError("Azure ARM pagination URL failed host validation")
    return url


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a bearer token to a redirect target.
        raise RuntimeError("Azure ARM redirect rejected; token was not forwarded")


def arm_get(url: str, credential) -> dict:
    """One HTTPS GET with ARM-scoped Entra token; never print token."""
    validate_arm_url(url)
    token = credential.get_token(ARM_SCOPE).token
    request = urllib.request.Request(
        url,
        method="GET",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    try:
        opener = urllib.request.build_opener(_NoRedirect)
        with opener.open(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Do not print response body: proxy/gateway errors may echo credentials.
        raise RuntimeError(f"Azure ARM request failed (HTTP {exc.code}); verify subscription, RBAC and network") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("Expected an Azure ARM JSON object")
    return payload


def arm_list(url: str, credential) -> list[dict]:
    results: list[dict] = []
    next_url: str | None = url
    seen: set[str] = set()
    while next_url:
        if next_url in seen:
            raise RuntimeError("Azure ARM returned a pagination cycle")
        seen.add(next_url)
        payload = arm_get(next_url, credential)
        rows = payload.get("value")
        if not isinstance(rows, list):
            raise RuntimeError("Expected an Azure ARM value array")
        results.extend(item for item in rows if isinstance(item, dict))
        next_url = payload.get("nextLink")
        if next_url is not None and not isinstance(next_url, str):
            raise RuntimeError("Invalid Azure ARM pagination link")
        if next_url:
            validate_arm_url(next_url)
    return results


def account_group(subscription_id: str, account: str, explicit_group: str | None, credential) -> str:
    if explicit_group:
        if not re.fullmatch(r"[A-Za-z0-9_.()\-]{1,90}", explicit_group):
            raise ValueError("Invalid Azure resource-group name")
        return explicit_group
    url = (
        f"{ARM_BASE}/subscriptions/{subscription_id}/providers/Microsoft.CognitiveServices/accounts"
        f"?api-version={API_VERSION}"
    )
    matches = [x for x in arm_list(url, credential) if str(x.get("name", "")).lower() == account.lower()]
    if len(matches) != 1:
        raise RuntimeError(
            "Could not uniquely find the Foundry account in this subscription. "
            "Supply an authorized --resource-group, or check subscription Reader access."
        )
    result = RG_RE.search(str(matches[0].get("id", "")))
    if not result:
        raise RuntimeError("Could not parse Azure resource group from account ARM ID")
    return urllib.parse.unquote(result.group(1))


def deployments_for(subscription_id: str, group: str, account: str, credential) -> list[dict]:
    url = (
        f"{ARM_BASE}/subscriptions/{subscription_id}/resourceGroups/{urllib.parse.quote(group, safe='')}"
        f"/providers/Microsoft.CognitiveServices/accounts/{urllib.parse.quote(account, safe='')}"
        f"/deployments?api-version={API_VERSION}"
    )
    rows = arm_list(url, credential)
    result = []
    for dep in rows:
        props = dep.get("properties") if isinstance(dep.get("properties"), dict) else {}
        state = str(props.get("provisioningState") or dep.get("provisioningState") or "").lower()
        if dep.get("name") and (not state or state == "succeeded"):
            result.append(dep)
    if not result:
        raise RuntimeError("No succeeded Foundry deployments visible; refusing to overwrite models.yml")
    return result


def token_command(python_path: str, helper_path: Path, tenant_id: str | None) -> str:
    args = [python_path, str(helper_path), "token"]
    if tenant_id:
        args += ["--tenant-id", tenant_id]
    if os.name == "nt":
        return "!" + subprocess.list2cmdline(args)
    return "!" + shlex.join(args)


def sync(*, endpoint: str, subscription_id: str, resource_group: str | None, tenant_id: str | None, apply: bool):
    if not GUID_RE.fullmatch(subscription_id):
        raise ValueError("--subscription-id must be the Azure subscription GUID (not its display name)")
    legacy = legacy_sync()
    endpoint = legacy.normalize_endpoint(endpoint)
    account = legacy.infer_account_name(endpoint)
    credential = create_credential(tenant_id)
    try:
        group = account_group(subscription_id, account, resource_group, credential)
        deployments = deployments_for(subscription_id, group, account, credential)
    finally:
        credential.close()
    provider = legacy.build_provider(endpoint, deployments)
    helper = Path(__file__).with_name("foundry-vscode-auth.py").resolve()
    if not helper.is_file():
        raise RuntimeError("Missing scripts/foundry-vscode-auth.py")
    provider["apiKey"] = token_command(sys.executable, helper, tenant_id)
    provider["authHeader"] = True
    if legacy.MODELS_YML.is_file() and legacy.yaml is None:
        raise RuntimeError(
            "An existing models.yml was found; approved PyYAML is required to safely preserve other providers."
        )
    document = legacy.merge_document(provider)
    print(f"Account: {account}; resource group: {group}; succeeded deployments: {len(deployments)}")
    print("Authentication: VS Code Azure Resources broker, no Azure CLI, no stored tokens")
    legacy.write_models(document, dry_run=not apply)
    if apply:
        print("Wrote local OMP models.yml. Restart OMP, then use `omp models find foundry`.")
    else:
        print("Preview only; no local files changed. Add --apply only after authorized review.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Foundry deployments to OMP with VS Code Azure Resources; no Azure CLI")
    parser.add_argument("--subscription-id", required=True, help="Actual GUID shown in VS Code Azure Resources")
    parser.add_argument("--resource-group", help="Known resource group; if omitted, discover via ARM read-only list")
    parser.add_argument("--tenant-id", default=os.environ.get("AZURE_TENANT_ID"))
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--apply", action="store_true", help="Write models.yml (default is preview only)")
    args = parser.parse_args()
    try:
        sync(
            endpoint=args.endpoint,
            subscription_id=args.subscription_id,
            resource_group=args.resource_group,
            tenant_id=args.tenant_id,
            apply=args.apply,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Foundry VS Code sync failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        # Don't expose HTTP headers, access tokens, proxy content, or raw SDK errors.
        print(f"Foundry VS Code sync failed ({type(exc).__name__}); verify VS Code sign-in, broker, RBAC and network.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
