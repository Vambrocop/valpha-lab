# tools/local_publish.ps1
# ASCII-only on purpose: Windows PowerShell 5.1 reads .ps1 as system ANSI (GBK) without a BOM,
# so non-ASCII in the source breaks parsing. Keep this file ASCII. The Python script's Chinese
# output is captured via the UTF-8 console encoding set below.
#
# Valpha LOCAL AUTO-PUBLISH -- scheduling shell for tools\local_publish.py.
#
# WHY THIS EXISTS (2026-11-07):
#   GitHub Actions is blocked by an ACCOUNT-LEVEL BILLING LOCK since 2026-11-05 20:23 UTC
#   (jobs rejected at creation: 3-4s, 0 steps, no runner;
#    "The job was not started because your account is locked due to a billing issue.").
#   Nothing in the repo can fix that -- see CODEX_HANDOFF.md section 1.
#   But GitHub Pages deployment does NOT consume Actions quota, so pushing docs/ still
#   updates the live site. Local therefore became the only publisher.
#
# WHAT IT DOES: all the gating lives in local_publish.py (fail-closed). This shell only
#   (a) sets up the environment, (b) runs it, (c) turns the exit code into a notification.
#
# EXIT CODES from local_publish.py:
#   0 = published (or nothing to publish, or --dry-run passed)
#   1 = a gate failed / push failed  -> needs a human
#   2 = refused to start (code changes in worktree, behind origin, no baseline)
#
# SCHEDULE (task "ValphaDailyPublish"): daily 10:00 Adelaide.
#   Daily -- not Mon/Wed/Fri like the old ValphaWeeklyRefresh -- because this is now the
#   ONLY thing publishing data. The old task is DISABLED (its steps are a strict subset:
#   run_all covers fetch_insider + insider_signal + ledger_sidecar, and build_ndx is in
#   POST_GATE_SCRIPTS). Re-enable it only if this one is retired:
#       schtasks /change /tn "ValphaWeeklyRefresh" /enable
#
# Run manually:  powershell -NoProfile -ExecutionPolicy Bypass -File E:\finance\tools\local_publish.ps1
# Dry run:       powershell -NoProfile -ExecutionPolicy Bypass -File E:\finance\tools\local_publish.ps1 -DryRun
# Remove task:   schtasks /delete /tn "ValphaDailyPublish" /f

param([switch]$DryRun)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$repo = "E:\finance"
Set-Location $repo
$env:PYTHONUTF8 = "1"

$logdir = Join-Path $repo "tools\refresh_logs"
if (-not (Test-Path $logdir)) { New-Item -ItemType Directory -Force -Path $logdir | Out-Null }
$shellLog = Join-Path $logdir "local_publish_shell.log"

function Log([string]$m) {
  $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m
  Write-Output $line
  Add-Content -Path $shellLog -Value $line -Encoding utf8
}

function Show-Toast([string]$title, [string]$msg) {
  # best-effort Windows toast; the Desktop flag file is the real can't-miss signal
  try {
    $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
    $tmpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $tn = $tmpl.GetElementsByTagName("text")
    $tn.Item(0).AppendChild($tmpl.CreateTextNode($title)) | Out-Null
    $tn.Item(1).AppendChild($tmpl.CreateTextNode($msg))   | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($tmpl)
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
  } catch { Log ("(toast unavailable: {0})" -f $_.Exception.Message) }
}

Log "=== ValphaDailyPublish START (DryRun=$DryRun) ==="

$argsList = @("tools\local_publish.py")
if ($DryRun) { $argsList += "--dry-run" }

& py @argsList
$code = $LASTEXITCODE
Log ("local_publish.py exit = {0}" -f $code)

# --- notify ---------------------------------------------------------------
# If "Valpha - PUBLISH NEEDS YOU.txt" is NOT on the Desktop, everything is fine.
$desktop = [Environment]::GetFolderPath('Desktop')
$flag    = Join-Path $desktop "Valpha - PUBLISH NEEDS YOU.txt"
$summary = Join-Path $logdir "LATEST_PUBLISH.txt"

if ($code -eq 0) {
  if (Test-Path $flag) { Remove-Item $flag -Force -ErrorAction SilentlyContinue }
  Show-Toast "Valpha published OK" "Data refreshed and pushed. Site updates via Pages. Nothing to do."
  Log "NOTIFY: success -> confirm toast (nothing on your Desktop = all good)"
} else {
  try { if (Test-Path $summary) { Copy-Item -Path $summary -Destination $flag -Force } } catch {}
  if ($code -eq 2) {
    Show-Toast "Valpha publish SKIPPED" "Refused to start (code changes in worktree, or behind origin). See Desktop file."
    Log "NOTIFY: refused to start -> Desktop flag + toast"
  } else {
    Show-Toast "Valpha publish BLOCKED" "A safety gate stopped the publish. Open the file on your Desktop."
    Log "NOTIFY: gate blocked -> Desktop flag + toast"
  }
}

Log "=== ValphaDailyPublish DONE (exit $code) ==="
exit $code
