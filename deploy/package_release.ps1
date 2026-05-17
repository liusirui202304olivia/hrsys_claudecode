param(
    [string]$OutputDir = "release"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $RepoRoot
try {
    $status = git status --porcelain
    if ($status) {
        Write-Error "Working tree is not clean. Commit or stash changes before packaging."
    }

    $commit = (git rev-parse --short HEAD).Trim()
    $resolvedOutputDir = Join-Path $RepoRoot $OutputDir
    New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null

    $archivePath = Join-Path $resolvedOutputDir ("hr_mcp_release_{0}.zip" -f $commit)
    if (Test-Path $archivePath) {
        Remove-Item -LiteralPath $archivePath
    }

    git archive --format=zip --output=$archivePath HEAD

    Write-Host ("Created release archive: {0}" -f $archivePath)
    Write-Host "Transfer this zip to nx2 with NoMachine, then unpack it on the intranet deployment machine."
    Write-Host "Intranet deployment target: /workspace/devops/env_prod/service/ai/hr_mcp"
}
finally {
    Pop-Location
}
