$ErrorActionPreference = "Stop"
az account get-access-token --resource https://ai.azure.com --query accessToken --output tsv
