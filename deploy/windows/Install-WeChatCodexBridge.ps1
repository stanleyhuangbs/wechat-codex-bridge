param([Parameter(Mandatory=$true)][string]$SourceRoot,[string]$RuntimeRoot="$env:LOCALAPPDATA\WeChatCodexBridge")
$ErrorActionPreference="Stop"
$codex=(Get-Command codex -ErrorAction Stop).Source; $python=(Get-Command python -ErrorAction Stop).Source
$stamp=(Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"); $release=Join-Path $RuntimeRoot "releases\$stamp"
$wheel=Join-Path $release "wheel"; $state=Join-Path $RuntimeRoot "state"; $workspace=Join-Path $RuntimeRoot "workspace"; $recovery=Join-Path $RuntimeRoot "recovery"
New-Item -ItemType Directory -Force -Path $wheel,$state,$workspace,$recovery | Out-Null
& icacls $RuntimeRoot /inheritance:r /grant:r "$env:USERNAME`:(OI)(CI)F" | Out-Null
& $python -m pip wheel --no-deps --no-build-isolation --wheel-dir $wheel $SourceRoot
$artifact=@(Get-ChildItem $wheel -Filter *.whl); if($artifact.Count -ne 1){throw "expected one wheel"}
& $python -m venv (Join-Path $release "venv"); $venvPython=Join-Path $release "venv\Scripts\python.exe"
& $venvPython -m pip install --no-deps $artifact[0].FullName
$token=Join-Path $RuntimeRoot "token"; if(-not (Test-Path $token)){$bytes=New-Object byte[] 48; $rng=[Security.Cryptography.RandomNumberGenerator]::Create(); try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}; [IO.File]::WriteAllText($token,[Convert]::ToBase64String($bytes))}
& icacls $token /inheritance:r /grant:r "$env:USERNAME`:F" | Out-Null
$program=Join-Path $release "venv\Scripts\wechat-codex-bridge.exe"
$args="--bind 127.0.0.1 --port 18791 --token-path `"$token`" --state-dir `"$state`" --workspace `"$workspace`" --codex `"$codex`""
$action=New-ScheduledTaskAction -Execute $program -Argument $args
$principal=New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
$trigger=New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
Register-ScheduledTask -TaskName "WeChatCodexBridge" -Action $action -Principal $principal -Trigger $trigger -Force | Out-Null
Start-ScheduledTask -TaskName "WeChatCodexBridge"
Set-Content -Path (Join-Path $RuntimeRoot "current.txt") -Value $release
Write-Output "service=WeChatCodexBridge bind=127.0.0.1:18791"
