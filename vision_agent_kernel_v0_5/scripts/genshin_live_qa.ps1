param(
    [Parameter(Mandatory=$true)][string]$Goal,
    [Parameter(Mandatory=$true)][string]$WindowTitle,
    [switch]$Execute,
    [switch]$Background,
    [int]$MaxIterations = 30,
    [double]$VlmInterval = 3.0
)

$root = Split-Path -Parent $PSScriptRoot
$argsList = @(
    "$PSScriptRoot\launch_real_game.py",
    "--game", "genshin",
    "--goal", $Goal,
    "--window-title", $WindowTitle,
    "--max-iterations", "$MaxIterations",
    "--vlm-interval", "$VlmInterval"
)

if ($Background) {
    $argsList += "--backend"
    $argsList += "flash_focus"
}

if ($Execute) {
    $argsList += "--execute"
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
