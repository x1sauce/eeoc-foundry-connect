# EEOC Foundry Connect — Quick Start

Use this when Foundry returns:

```text
403 Key based authentication is disabled for this resource.
```

## 1. Azure login

```powershell
az login
az account show --query "{subscription:name,tenant:tenantId,user:user.name}" --output table
```

Expected EEOC DEV subscription:

```text
OIT-COM-PRIV-TEST/UAT
```

## 2A. OMP

```powershell
omp plugin install github:<YOUR-GITHUB-OWNER>/eeoc-foundry-connect
```

Restart OMP, then run:

```text
/foundry-sync
```

Restart OMP again and verify:

```powershell
omp models find foundry
```

## 2B. Any other compatible AI harness

Validate the connection and list the actual deployments:

```powershell
python .\scripts\foundry-connect.py
```

Configure the harness with:

```text
Base URL: https://aif-eeoc-daes-dev.services.ai.azure.com/openai/v1
Auth: Authorization: Bearer <token>
```

Generate the temporary token with:

```powershell
az account get-access-token --resource https://ai.azure.com --query accessToken --output tsv
```

The harness must support an OpenAI-compatible Responses API and bearer-token authentication. Do not save the token in Git or shared config.
