[CmdletBinding()]
param(
    [string]$Destination,
    [string[]]$SkillName = @('ste-fr', 'lexicon-ingest', 'market-review', 'trade-execution', 'us-market-review'),
    [switch]$Prune
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    if ($env:CODEX_HOME) {
        $Destination = Join-Path $env:CODEX_HOME 'skills'
    } else {
        $Destination = Join-Path $env:USERPROFILE '.codex\skills'
    }
}
$destinationRoot = [System.IO.Path]::GetFullPath($Destination)

foreach ($skill in $SkillName) {
    if ($skill -notmatch '^[a-z0-9][a-z0-9-]*$') {
        throw "Invalid skill name: $skill"
    }
    $sourceRoot = Join-Path (Join-Path $repositoryRoot 'skills') $skill
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot 'SKILL.md') -PathType Leaf)) {
        throw "Skill does not exist: $skill"
    }
}

foreach ($skill in $SkillName) {
    $sourceRoot = Join-Path (Join-Path $repositoryRoot 'skills') $skill
    $targetRoot = Join-Path $destinationRoot $skill
    if ([System.IO.Path]::GetFullPath($sourceRoot) -eq [System.IO.Path]::GetFullPath($targetRoot)) {
        throw 'The installation destination must differ from the source directory.'
    }
    $sourceRelative = @()
    foreach ($file in (Get-ChildItem -LiteralPath $sourceRoot -Recurse -File)) {
        if ($file.Name -like '*.local.json') { continue }
        if ($file.FullName -match '[\\/]__pycache__[\\/]') { continue }
        $relativePath = $file.FullName.Substring($sourceRoot.Length + 1)
        $sourceRelative += $relativePath
        $targetFile = Join-Path $targetRoot $relativePath
        New-Item -ItemType Directory -Path (Split-Path -Parent $targetFile) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $targetFile -Force
        if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne (Get-FileHash -LiteralPath $targetFile).Hash) {
            throw "Installed file differs: $targetFile"
        }
    }
    if ($Prune -and (Test-Path -LiteralPath $targetRoot)) {
        # Remove installed files that no longer exist in the source; local configs are kept.
        foreach ($installed in (Get-ChildItem -LiteralPath $targetRoot -Recurse -File)) {
            if ($installed.Name -like '*.local.json') { continue }
            $installedRelative = $installed.FullName.Substring($targetRoot.Length + 1)
            if ($sourceRelative -notcontains $installedRelative) {
                Remove-Item -LiteralPath $installed.FullName -Force
                Write-Output "Pruned stale file: $skill\$installedRelative"
            }
        }
        Get-ChildItem -LiteralPath $targetRoot -Recurse -Directory |
            Sort-Object { $_.FullName.Length } -Descending |
            Where-Object { -not (Get-ChildItem -LiteralPath $_.FullName -Force) } |
            Remove-Item
    }
    Write-Output "Installed and verified: $skill -> $targetRoot"
}
