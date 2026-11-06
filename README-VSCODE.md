# Proposed branch: `feature/vscode-broker-no-az`

**Status: offline prototype.** Not deployed, not synced against EEOC Foundry, no real Microsoft Entra credentials tested. Continue only after EEOC IT approves the new dependencies and Justin lifts the relevant Foundry restrictions. Do not treat this as a bypass of administrative security controls.

## Additive design

Leave v1.2.0 `scripts/foundry-sync.py`, `scripts/foundry-connect.py` and `src/main.ts` unchanged. Add:

- `scripts/foundry-vscode-auth.py`: requests an Entra token from the VS Code Azure Resources sign-in using the official Python broker; prints token only in `token` mode for OMP's `!command` credential resolution.
- `scripts/foundry-vscode-sync.py`: reads actual Azure Cognitive Services deployments using Microsoft Azure Resource Manager GET requests; reuses the original sync script's model metadata and `models.yml` merging/backups; defaults to preview, requires `--apply` to write.
- `tests/test_foundry_vscode.py`: offline mocked tests.
- `src/vscode.ts`: optional OMP command `/foundry-vscode-sync` that calls the new Python sync path.
- `package.json`: additive change declaring the new extension alongside the original `src/main.ts`; branch-only overlay, version bump deferred until release.

No Azure CLI and no Foundry API key. No model inference during discovery. No token printed during a sync or written to a file.

## Laptop prerequisites (after IT approval)

- Windows VS Code with the **Azure Resources** extension and an EEOC Entra login (`Azure: Sign In`).
- Python 3.13, already installed on the laptop.
- Admin-approved Python packages `azure-identity`, `azure-identity-broker`, and `pyyaml` (PyYAML recommended to merge existing configs without losing other providers).
- Azure subscription GUID (not display name), and optionally the Foundry resource group and tenant GUID, from Azure Resources.
- Azure RBAC **read** permission for Cognitive Services accounts/deployments to sync; separate appropriate **data plane inference** permission to call models.
- Network connectivity to `management.azure.com` and the Foundry endpoint, plus organization-approved corporate CA trust.

This is NOT guaranteed to work in all organizations: VS Code broker sign-in, Conditional Access, tenant selection and RBAC may prevent the process from acquiring or using the token.

## Offline verification (no Azure calls)

Copy the files to a local clone of `eeoc-foundry-connect` keeping the existing files. Run from the repository root:

```powershell
python -m unittest discover -s tests -p test_foundry_vscode.py -v
python .\scripts\foundry-vscode-sync.py --help
```

## Approved staged checks (real authentication / ARM reads)

```powershell
# Python packages only with explicit IT approval:
python -m pip install --user azure-identity azure-identity-broker pyyaml

# Identity check (does not call a Foundry deployment; never output a token):
python .\scripts\foundry-vscode-auth.py check

# Subscription ID: find it in VS Code Azure Resources > subscription > properties.
# This performs read-only ARM GETs, previews the provider, and doesn't write local files:
python .\scripts\foundry-vscode-sync.py --subscription-id "<GUID>"

# Once checked and authorized, opt in to writing local ~/.omp/agent/models.yml:
python .\scripts\foundry-vscode-sync.py --subscription-id "<GUID>" --apply
```

For an account that cannot list all resources in the subscription, supply a known authorized resource group via `--resource-group <RG>`; sync still requires ARM read access to that account's deployments. If tenant selection is ambiguous, add `--tenant-id <TENANT-GUID>` to both preview and apply; sync stores the tenant GUID in the *non-secret* `!` command, not an access token.

After adding the new `src/vscode.ts` and overlay `package.json` on a working **branch** (not in the installed production plugin), the OMP extension also provides:

```text
/foundry-vscode-sync <SUBSCRIPTION-GUID>
/foundry-vscode-sync <SUBSCRIPTION-GUID> --apply
```

This optional slash command has the same preview-first behavior as the Python CLI. The original `/foundry-sync` remains Azure-CLI-based for backward compatibility.

Restart OMP after writing and verify model catalog **without inference**:

```powershell
omp models find foundry
```

After the EEOC team explicitly reauthorizes Foundry model calls, test one small deployment request (this invokes paid inference):

```powershell
omp --model foundry/<APPROVED_DEPLOYMENT> --no-session -p "Reply with exactly: OK"
```

## Known risks / acceptance gates

1. The official VS Code Python credential requires the `azure-identity-broker` integration and may fail on a managed machine; do not scrape VS Code tokens or disable TLS.
2. `models.yml` uses an OMP `apiKey: "!<python> <token-helper> token"` shell command, so **OMP's command execution and successful-token caching/refresh semantics must be validated on OMP 18.17.0**. Restart OMP / refresh credentials if a token expires. No claim of permanent refresh reliability until long-session testing and 401 re-auth behavior pass.
3. Confirm the actual provider generated by the installed `foundry-sync.py` supports the chosen deployments, Responses API compatibility, and correct metadata.
4. Only succeeded deployments are synced; only local `models.yml` is written when `--apply` is passed. An existing file is backed up by the original sync code. The preview includes a token **command**, never a token.
5. Do not install Azure CLI, modify system trust, bypass admin controls, or access Foundry without permission.
6. This ZIP is a **branch overlay**, not a full repository. It adds `src/vscode.ts` and modifies only `package.json` to register the new command. It must be applied over the existing v1.2.0 repository source in a new working branch; the remote GitHub branch has **not** been created or pushed.

## Sources

- Microsoft Azure Identity `VisualStudioCodeCredential`: https://learn.microsoft.com/en-us/python/api/azure-identity/azure.identity.visualstudiocodecredential
- Microsoft Azure Cognitive Services accounts list REST: https://learn.microsoft.com/en-us/rest/api/aifoundry/accountmanagement/accounts/list?view=rest-aifoundry-accountmanagement-2025-06-01
- Microsoft Azure deployments list REST: https://learn.microsoft.com/en-us/rest/api/microsoftfoundry/accountmanagement/deployments/list?view=rest-microsoftfoundry-accountmanagement-2025-06-01
- Foundry Entra auth and Responses: https://learn.microsoft.com/azure/ai-foundry/foundry-models/how-to/configure-entra-id
