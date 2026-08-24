param([string]$RuntimeRoot="$env:LOCALAPPDATA\WeChatCodexBridge")
$ErrorActionPreference="Stop"; $recovery=Join-Path $RuntimeRoot ("recovery\uninstall-"+(Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ"))
New-Item -ItemType Directory -Force -Path $recovery | Out-Null
Unregister-ScheduledTask -TaskName "WeChatCodexBridge" -Confirm:$false -ErrorAction SilentlyContinue
$current=Join-Path $RuntimeRoot "current.txt"; if(Test-Path $current){Move-Item $current $recovery}
Write-Output "preserved: token state releases backups workspace; recovery=$recovery"
