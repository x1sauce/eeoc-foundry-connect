param(
    [string]$Endpoint = "https://aif-eeoc-daes-dev.services.ai.azure.com",
    [string]$Subscription = "OIT-COM-PRIV-TEST/UAT"
)

$ErrorActionPreference = "Stop"
$Script = Join-Path $PSScriptRoot "foundry-sync.py"

$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) {
    & python $Script --endpoint $Endpoint --subscription $Subscription
    exit $LASTEXITCODE
}

$Py = Get-Command py -ErrorAction SilentlyContinue
if ($Py) {
    & py -3 $Script --endpoint $Endpoint --subscription $Subscription
    exit $LASTEXITCODE
}

throw "Python 3 was not found. Install Python 3, then re-run this script."
