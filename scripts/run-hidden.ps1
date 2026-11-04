param(
    [Parameter(Mandatory = $true)][string]$CommandFile,
    [int]$WaitSeconds = 10,
    [string]$LogDir = "",
    [string]$Label = "run",
    [string]$WorkDir = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($WorkDir)) { $WorkDir = (Get-Location).Path }
if ([string]::IsNullOrWhiteSpace($LogDir)) {
    $LogDir = Join-Path (Split-Path -Parent $PSScriptRoot) "runtime\logs"
}
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$id = "{0}_{1}" -f (Get-Date -Format "yyyyMMdd_HHmmss"), ([guid]::NewGuid().ToString("N").Substring(0, 8))
$dir = Join-Path $LogDir $id
New-Item -ItemType Directory -Path $dir -Force | Out-Null

$outPath = Join-Path $dir "stdout.log"
$errPath = Join-Path $dir "stderr.log"
$psPath = Join-Path $dir "command.ps1"
$metaPath = Join-Path $dir "meta.json"
$exitPath = Join-Path $dir "exit.txt"

$text = [IO.File]::ReadAllText($CommandFile, [Text.Encoding]::UTF8)
[IO.File]::WriteAllText($psPath, $text, (New-Object Text.UTF8Encoding($true)))

$psExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$inner = '"' + $psExe + '" -NoProfile -ExecutionPolicy Bypass -File "' + $psPath + '" > "' + $outPath + '" 2> "' + $errPath + '"; exit $LASTEXITCODE'
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $env:ComSpec
$psi.Arguments = '/d /s /c "' + $inner + '"'
$psi.UseShellExecute = $false
$psi.CreateNoWindow = $true
$psi.WindowStyle = [System.Diagnostics.ProcessWindowStyle]::Hidden
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.WorkingDirectory = $WorkDir
$psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
$psi.EnvironmentVariables["PYTHONUTF8"] = "1"

$p = [System.Diagnostics.Process]::Start($psi)
$p.StandardInput.Close()
$finished = $p.WaitForExit($WaitSeconds * 1000)

$meta = [ordered]@{
    jobId       = $id
    label       = $Label
    pid         = $p.Id
    commandFile = $psPath
    workDir     = $WorkDir
    stdout      = $outPath
    stderr      = $errPath
    status      = if ($finished) { "exited" } else { "running" }
}
if ($finished) {
    $meta.exitCode = $p.ExitCode
    [IO.File]::WriteAllText($exitPath, [string]$p.ExitCode, (New-Object Text.UTF8Encoding($false)))
}
[IO.File]::WriteAllText($metaPath, ($meta | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding($false)))

"job_id=$id"
"pid=$($p.Id)"
"status=$($meta.status)"
"stdout=$outPath"
"stderr=$errPath"

if ($finished) {
    "exit_code=$($p.ExitCode)"
    $stdout = if (Test-Path $outPath) { [IO.File]::ReadAllText($outPath, [Text.Encoding]::UTF8) } else { "" }
    $stderr = if (Test-Path $errPath) { [IO.File]::ReadAllText($errPath, [Text.Encoding]::UTF8) } else { "" }
    if ($stdout.Trim().Length -gt 0) { "--- stdout ---"; $stdout.TrimEnd() }
    if ($stderr.Trim().Length -gt 0) { "--- stderr ---"; $stderr.TrimEnd() }
}
