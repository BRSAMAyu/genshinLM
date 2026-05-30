param(
    [Parameter(Mandatory=$true)][string]$Goal,
    [Parameter(Mandatory=$true)][string]$WindowTitle,
    [string]$Game = "genshin",
    [switch]$Execute,
    [switch]$IUnderstandAuthorizedWindow,
    [int]$MaxIterations = 30
)

$root = Split-Path -Parent $PSScriptRoot
$argsList = @(
    "$PSScriptRoot\launch_real_game.py",
    "--game", $Game,
    "--goal", $Goal,
    "--window-title", $WindowTitle,
    "--max-iterations", "$MaxIterations"
)

if ($Execute) {
    $argsList += "--execute"
}
if ($IUnderstandAuthorizedWindow) {
    $argsList += "--i-understand-authorized-window"
}

Push-Location $root
try {
    python @argsList
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
