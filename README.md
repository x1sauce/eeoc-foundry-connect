# EEOC Foundry Connect

An OMP plugin plus reusable connection helpers for accessing the EEOC Azure AI Foundry resource with **Microsoft Entra ID bearer authentication**.

This project fixes the common error:

```text
403 Key based authentication is disabled for this resource.
```

Instead of a static Foundry API key, clients authenticate with an Entra token obtained from Azure CLI:

```text
az account get-access-token --resource https://ai.azure.com
```

No Foundry API key is required, and the tools in this repo do not persist Entra access tokens.

## What this project supports

### OMP

OMP is the fully automated integration. Installing the plugin adds:

```text
/foundry-sync
/foundry-auth-help
```

`/foundry-sync` discovers the actual Azure deployments and writes an Entra/Bearer-authenticated provider into `~/.omp/agent/models.yml`.

### Other AI harnesses

The underlying Foundry connection is not OMP-specific. Any harness that supports:

1. an OpenAI-compatible **Responses API** endpoint, and
2. `Authorization: Bearer <token>` authentication

can use the same Foundry resource.

Run the harness-neutral helper:

```powershell
python .\scripts\foundry-connect.py
```

or machine-readable output:

```powershell
python .\scripts\foundry-connect.py --json
```

It validates Azure access, discovers the real deployments, and prints the connection information without printing or storing the token itself.

The shared connection recipe is:

```text
Base URL:
https://aif-eeoc-daes-dev.services.ai.azure.com/openai/v1

Bearer token command:
az account get-access-token --resource https://ai.azure.com --query accessToken --output tsv

HTTP auth:
Authorization: Bearer <token>
```

If a harness can execute a credential command, point it at the token command. If it only accepts an environment variable or bearer-token field, mint a fresh token when launching that harness. A harness that cannot use an OpenAI-compatible Responses provider will need its own adapter or gateway.

This repo intentionally does **not** maintain one-off setup code for individual harnesses such as Codex. The goal is to keep the Foundry connection reusable rather than couple the project to specific clients.

## Prerequisites

- Azure CLI
- EEOC Entra access to the target Foundry resource
- Python 3
- OMP only if using the OMP plugin integration

Sign in first:

```powershell
az login
az account show --query "{subscription:name,tenant:tenantId,user:user.name}" --output table
```

Default EEOC DEV subscription:

```text
OIT-COM-PRIV-TEST/UAT
```

## OMP setup

### Install

```powershell
omp plugin install github:x1sauce/eeoc-foundry-connect
```

Restart OMP once.

### Sync

Inside OMP:

```text
/foundry-sync
```

Or from PowerShell:

```powershell
& "$HOME\.omp\plugins\node_modules\eeoc-foundry-connect\scripts\foundry-sync.ps1"
```

The generated OMP provider uses:

```yaml
baseUrl: https://aif-eeoc-daes-dev.services.ai.azure.com/openai/v1
api: openai-responses
apiKey: "!az account get-access-token --resource https://ai.azure.com --query accessToken --output tsv"
authHeader: true
```

The sync discovers **actual Azure deployments** with:

```text
az cognitiveservices account deployment list
```

so it does not dump the hundreds of catalog entries returned by `/openai/v1/models` into OMP.

Restart OMP after the sync, then verify:

```powershell
omp models find foundry
omp --model foundry/<deployment> --no-session -p "Reply with exactly: OK"
```

## Generic harness workflow

First validate the shared connection:

```powershell
python .\scripts\foundry-connect.py
```

Then configure the harness with:

```text
Base URL: https://aif-eeoc-daes-dev.services.ai.azure.com/openai/v1
API: OpenAI-compatible Responses
Auth: Authorization: Bearer <token>
```

Generate a temporary token with:

```powershell
az account get-access-token --resource https://ai.azure.com --query accessToken --output tsv
```

A convenience PowerShell helper is also included:

```powershell
.\scripts\foundry-token.ps1
```

Do not commit the returned token or place it in shared configuration.

## Why the old setup fails

The older OMP/Otto sync used static key authentication:

```yaml
api: azure-openai-responses
apiKey: AZURE_OPENAI_API_KEY
```

The EEOC Foundry resource now rejects key-based authentication. This project switches clients to the Foundry OpenAI-compatible v1 Responses endpoint with Entra bearer authentication.

## Important Otto note

An older Otto-bundled `foundry-sync.py` may still generate the old API-key configuration. Do not run that older script after using this project, or it may overwrite the working bearer-auth configuration.

## Security

Do not commit or share:

- output from `az account get-access-token`
- bearer tokens
- old Foundry API keys
- passwords, client secrets, or other credentials

This repo contains connection metadata and configuration logic, not persistent credentials.
