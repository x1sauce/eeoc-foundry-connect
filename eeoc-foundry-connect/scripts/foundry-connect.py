#!/usr/bin/env python3
"""Show reusable EEOC Azure AI Foundry connection details for any compatible AI harness.

This helper validates Azure CLI access, discovers the Foundry account/resource group,
and lists the active deployments. It does not write harness-specific configuration and
never prints the bearer token itself.

Typical usage:
    python foundry-connect.py

Machine-readable output:
    python foundry-connect.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from urllib.parse import urlparse

DEFAULT_ENDPOINT = "https://aif-eeoc-daes-dev.services.ai.azure.com"
DEFAULT_SUBSCRIPTION = "OIT-COM-PRIV-TEST/UAT"
FOUNDRY_RESOURCE = "https://ai.azure.com"
TOKEN_COMMAND = (
    "az account get-access-token --resource https://ai.azure.com "
    "--query accessToken --output tsv"
)


def run_az(args: list[str], *, timeout: int = 45) -> str:
    command = ["az", *args]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=(os.name == "nt"),
        )
    except FileNotFoundError:
        sys.exit("Azure CLI (`az`) was not found. Install Azure CLI, run `az login`, and retry.")
    except subprocess.TimeoutExpired:
        sys.exit(f"Azure CLI timed out: {' '.join(command)}")
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        sys.exit(f"Azure CLI command failed:\n  {' '.join(command)}\n\n{detail}")
    return result.stdout.strip()


def normalize_endpoint(value: str) -> str:
    endpoint = value.strip().rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        sys.exit(f"Foundry endpoint must be an HTTPS URL (got: {value!r})")
    if not parsed.hostname.endswith((".services.ai.azure.com", ".openai.azure.com")):
        sys.exit(
            "Foundry endpoint must use a supported Azure AI host "
            "(.services.ai.azure.com or .openai.azure.com)."
        )
    return endpoint


def infer_account_name(endpoint: str) -> str:
    hostname = urlparse(endpoint).hostname or ""
    account = hostname.split(".", 1)[0].strip()
    if not account:
        sys.exit(f"Could not infer Azure AI account name from endpoint: {endpoint}")
    return account


def ensure_subscription(subscription: str | None) -> dict:
    raw = run_az(["account", "show", "--output", "json"])
    account = json.loads(raw)
    if subscription:
        current_name = str(account.get("name") or "")
        current_id = str(account.get("id") or "")
        if subscription not in {current_name, current_id}:
            run_az(["account", "set", "--subscription", subscription])
            account = json.loads(run_az(["account", "show", "--output", "json"]))
    return account


def validate_token() -> None:
    token = run_az(
        [
            "account",
            "get-access-token",
            "--resource",
            FOUNDRY_RESOURCE,
            "--query",
            "accessToken",
            "--output",
            "tsv",
        ]
    )
    if not token:
        sys.exit("Azure CLI returned an empty Foundry access token.")


def discover_resource_group(account_name: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    query = f"[?name=='{account_name}'].resourceGroup | [0]"
    group = run_az(["cognitiveservices", "account", "list", "--query", query, "--output", "tsv"])
    if not group:
        sys.exit(
            f"Could not find Cognitive Services account '{account_name}' in the active subscription.\n"
            "Pass --resource-group explicitly or verify `az account show`."
        )
    return group


def list_deployments(account_name: str, resource_group: str) -> list[dict]:
    raw = run_az(
        [
            "cognitiveservices",
            "account",
            "deployment",
            "list",
            "--name",
            account_name,
            "--resource-group",
            resource_group,
            "--output",
            "json",
        ]
    )
    try:
        items = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.exit(f"Could not parse deployment list: {exc}")
    if not isinstance(items, list):
        sys.exit("Azure CLI returned an unexpected deployment-list response.")
    return [
        item
        for item in items
        if isinstance(item, dict)
        and str(item.get("properties", {}).get("provisioningState", "")).lower() == "succeeded"
        and item.get("name")
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and show reusable EEOC Azure AI Foundry connection details."
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--subscription", default=DEFAULT_SUBSCRIPTION)
    parser.add_argument("--resource-group")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    endpoint = normalize_endpoint(args.endpoint)
    account_name = infer_account_name(endpoint)
    account = ensure_subscription(args.subscription or None)
    validate_token()
    resource_group = discover_resource_group(account_name, args.resource_group)
    deployments = list_deployments(account_name, resource_group)

    result = {
        "endpoint": endpoint,
        "base_url": f"{endpoint}/openai/v1",
        "token_resource": FOUNDRY_RESOURCE,
        "token_command": TOKEN_COMMAND,
        "auth_header": "Authorization: Bearer <token>",
        "subscription": str(account.get("name") or ""),
        "account_name": account_name,
        "resource_group": resource_group,
        "deployments": [
            {
                "deployment": str(item.get("name") or ""),
                "model": str(item.get("properties", {}).get("model", {}).get("name") or ""),
            }
            for item in deployments
        ],
    }

    if args.as_json:
        print(json.dumps(result, indent=2))
        return

    print("EEOC Azure AI Foundry connection: OK")
    print(f"Base URL:      {result['base_url']}")
    print(f"Auth:          {result['auth_header']}")
    print(f"Token command: {result['token_command']}")
    print(f"Subscription:  {result['subscription']}")
    print(f"Account:       {result['account_name']}")
    print(f"Deployments:   {len(result['deployments'])}")
    for item in result["deployments"]:
        model = f" -> {item['model']}" if item["model"] else ""
        print(f"  - {item['deployment']}{model}")


if __name__ == "__main__":
    main()
