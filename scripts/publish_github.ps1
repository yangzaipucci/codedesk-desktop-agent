param([Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI, then run gh auth login.' }
gh auth status
if ($LASTEXITCODE -ne 0) { throw 'Run gh auth login first.' }
gh repo create $Repository --public --source . --remote origin --push
if ($LASTEXITCODE -ne 0) { throw 'Repository creation or push failed. Check the remote before retrying.' }
git tag v1.0.0
git push origin v1.0.0
gh release create v1.0.0 'release/CodeDesk-Setup-1.0.0.exe' --title 'CodeDesk 1.0.0' --notes-file 'docs/release-notes.md'
if ($LASTEXITCODE -ne 0) { throw 'Release publication failed.' }
