param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')][string]$Repository,
    [string]$Python = '.venv\Scripts\python.exe'
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
function Invoke-Checked {
    param([string]$Program, [string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Failed: $Program (exit $LASTEXITCODE)" }
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Specify the project Python with -Python.' }
$version = & $Python -c "import pathlib,tomllib;print(tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8-sig'))['project']['version'])"
if ($LASTEXITCODE -ne 0 -or $version -notmatch '^\d+\.\d+\.\d+$') { throw 'Invalid release version.' }
$output = Join-Path 'release\signed' $version
$bundle = 'build\signed\application\CodeDesk'
# Complete this gate before repository creation, pushes, tags or releases.
Invoke-Checked $Python @('scripts\release_check.py', '--directory', $bundle, '--output', $output, '--version', $version)
$dirty = git status --porcelain
if ($LASTEXITCODE -ne 0 -or $dirty) { throw 'Commit the final source and documentation before publishing.' }
$head = git rev-parse HEAD
if ($LASTEXITCODE -ne 0) { throw 'Cannot read Git HEAD.' }
$manifest = Get-Content -LiteralPath (Join-Path $output 'signing-manifest.json') -Raw | ConvertFrom-Json
if ($manifest.source_commit -ne $head) { throw 'Build belongs to another commit. Rebuild and repeat installation acceptance.' }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'Install GitHub CLI, then run gh auth login.' }
Invoke-Checked 'gh' @('auth', 'status')
$origin = git config --get remote.origin.url
if ($LASTEXITCODE -eq 0) {
    if ($origin -notin @("https://github.com/$Repository", "https://github.com/$Repository.git", "git@github.com:$Repository.git")) { throw 'origin does not match -Repository. No remote was changed.' }
} else {
    Invoke-Checked 'gh' @('repo', 'create', $Repository, '--public', '--source', '.', '--remote', 'origin')
}
$tag = "v$version"
$releaseTags = & gh api "repos/$Repository/releases" --paginate --jq '.[].tag_name'
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect existing GitHub releases. No tag was created.' }
if ($tag -in $releaseTags) { throw 'This release already exists. Use a new version; existing releases are never overwritten.' }
$tagHead = git rev-parse --verify --quiet "refs/tags/$tag^{commit}"
if ($LASTEXITCODE -eq 0) {
    if ($tagHead -ne $head) { throw 'Existing tag points to another commit. Tags are never moved.' }
} else {
    Invoke-Checked 'git' @('tag', $tag)
}
Invoke-Checked 'git' @('push', 'origin', 'HEAD:refs/heads/main', "refs/tags/$tag")
$assets = @(
    (Join-Path $output "CodeDesk-Setup-$version.exe"),
    (Join-Path $output "CodeDesk-Portable-$version-win64.zip"),
    (Join-Path $output 'signing-manifest.json'),
    (Join-Path $output 'installation-acceptance.json'),
    (Join-Path $output 'SHA256SUMS.txt')
)
Invoke-Checked 'gh' (@('release', 'create', $tag, '--repo', $Repository, '--verify-tag', '--title', "CodeDesk $version", '--notes-file', 'docs\signed-release-notes.md') + $assets)
