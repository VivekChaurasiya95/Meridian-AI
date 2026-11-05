# Meridian M10 live smoke: signup -> workspace -> project -> ZIP upload ->
# investigation -> stages/activity -> verification + report.
# Run from an UNSANDBOXED PowerShell with API+worker+db+minio up:
#   powershell -ExecutionPolicy Bypass -File .\smoke_m10.ps1
# Read-only except for the throwaway smoke workspace it creates. No secrets printed.
$ErrorActionPreference = "Stop"
$API = "http://127.0.0.1:8010"
$stamp = Get-Date -Format "yyyyMMddHHmmss"
$jar = Join-Path $env:TEMP "meridian_smoke_$stamp.cookies.txt"
$zipPath = Join-Path $env:TEMP "meridian_smoke_$stamp.zip"

function Call($method, $path, $bodyJson) {
    $args = @("-sS", "-w", "`n%{http_code}", "-X", $method, "-c", $jar, "-b", $jar,
        "-H", "Content-Type: application/json", "-H", "Origin: http://localhost:3010", "$API$path")
    # PS 5.1 strips inner double-quotes when passing -d inline to native exes
    # (JSON decode error server-side), so send the body via a temp file.
    if ($bodyJson) {
        $bodyFile = Join-Path $env:TEMP ("meridian_smoke_body_{0}.json" -f [guid]::NewGuid())
        [IO.File]::WriteAllText($bodyFile, $bodyJson)
        $args += @("-d", "@$bodyFile")
    }
    $raw = & curl.exe @args
    $code = $raw[-1]
    $payload = ($raw[0..($raw.Length - 2)] -join "`n") | ConvertFrom-Json
    if ([int]$code -ge 400) { throw "$method $path -> HTTP $code : $($payload.error.message)" }
    return $payload.data
}

function Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

try {
    Step "1. Health"
    $live = Invoke-RestMethod "$API/health/live"
    if ($live.status -ne "ok") { throw "liveness failed" }
    Write-Host "live ok"
    try { $ready = Invoke-RestMethod "$API/health/ready"; Write-Host "ready ok" }
    catch { Write-Host "ready not green yet (continuing): $($_.Exception.Message)" -ForegroundColor Yellow }

    Step "2. Signup (throwaway account)"
    $email = "smoke+$stamp@example.com"
    $me = Call "POST" "/api/v1/auth/signup" (@{email = $email; password = "Smoke-Test-12345";
        display_name = "smoke $stamp" } | ConvertTo-Json -Compress)
    Write-Host "user id: $($me.id)"

    Step "3. Workspace + project"
    $ws = Call "POST" "/api/v1/workspaces" (@{name = "smoke $stamp"; slug = "smoke-$stamp" } |
        ConvertTo-Json -Compress)
    Write-Host "workspace id: $($ws.id)"
    $proj = Call "POST" "/api/v1/workspaces/$($ws.id)/projects" (@{name = "smoke app";
        slug = "smoke-app"; description = "M10 smoke project" } | ConvertTo-Json -Compress)
    Write-Host "project id: $($proj.id)"

    Step "4. ZIP upload -> snapshot"
    $stage = Join-Path $env:TEMP "meridian_smoke_$stamp"
    New-Item -ItemType Directory $stage | Out-Null
    "# smoke app" | Out-File (Join-Path $stage "README.md") -Encoding utf8
    "print('smoke ok')" | Out-File (Join-Path $stage "main.py") -Encoding utf8
    # M6 browser repro serves static snapshots: include a minimal HTML entrypoint.
    "<!doctype html><html><body><button id='go'>Go</button></body></html>" |
        Out-File (Join-Path $stage "index.html") -Encoding utf8
    Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zipPath
    $up = & curl.exe -sS -c $jar -b $jar -H "Origin: http://localhost:3010" `
        -F "file=@$zipPath;type=application/zip" `
        "$API/api/v1/projects/$($proj.id)/source-uploads" | ConvertFrom-Json
    if ($up.error) { throw "upload failed: $($up.error.message)" }
    $snapId = $up.data.snapshot.id
    Write-Host "snapshot id: $snapId"

    Step "5. Investigation"
    $inv = Call "POST" "/api/v1/projects/$($proj.id)/investigations" (@{title = "smoke repro";
        bug_report = "Smoke test: landing page button does nothing when clicked.";
        severity = "low"; repository_snapshot_id = "$snapId";
        reproduction_context = @{route = "/" } } | ConvertTo-Json -Compress)
    Write-Host "investigation id: $($inv.id)"

    Step "6. Poll jobs + stages (worker must be running, ~3 min max)"
    for ($i = 0; $i -lt 36; $i++) {
        Start-Sleep -Seconds 5
        $jobs = @((Call "GET" "/api/v1/workspaces/$($ws.id)/jobs"))
        $jobStates = ($jobs | ForEach-Object { "$($_.job_type)=$($_.status)" }) -join " "
        $stages = @((Call "GET" "/api/v1/investigations/$($inv.id)/stages"))
        $states = ($stages | ForEach-Object { "$($_.stage_key)=$($_.status)" }) -join " "
        Write-Host "  [$i] jobs: [$jobStates] stages: [$states]"
        $busy = (@($jobs.status) | Where-Object { $_ -in "queued", "claimed", "running" }).Count -gt 0 -or
            (@($stages.status) | Where-Object { $_ -in "pending", "running" }).Count -gt 0
        if (-not $busy -and $stages.Count -gt 0) { break }
    }

    Step "7. Evidence modules"
    $finalJobs = @((Call "GET" "/api/v1/workspaces/$($ws.id)/jobs"))
    foreach ($j in $finalJobs) {
        if ($j.status -notin "completed", "succeeded") {
            Write-Host "job $($j.job_type)=$($j.status) err=$($j.error_code): $($j.error_message)"
        }
    }
    $finalStages = @((Call "GET" "/api/v1/investigations/$($inv.id)/stages"))
    foreach ($s in $finalStages) {
        if ($s.error_code) { Write-Host "stage $($s.stage_key)=$($s.status) err=$($s.error_code): $($s.error_message)" }
    }
    $act = @((Call "GET" "/api/v1/investigations/$($inv.id)/activity"))
    Write-Host "activity events: $($act.Count)"
    try { $hyps = @((Call "GET" "/api/v1/investigations/$($inv.id)/hypotheses"))
        Write-Host "hypotheses: $($hyps.Count)" }
    catch { Write-Host "hypotheses unavailable: $($_.Exception.Message)" -ForegroundColor Yellow }
    try { $reps = @((Call "GET" "/api/v1/investigations/$($inv.id)/reports"))
        Write-Host "reports: $($reps.Count)" }
    catch { Write-Host "reports unavailable: $($_.Exception.Message)" -ForegroundColor Yellow }
    try { $runs = @((Call "GET" "/api/v1/investigations/$($inv.id)/verification-runs"))
        Write-Host "verification runs: $($runs.Count)" }
    catch { Write-Host "verification unavailable: $($_.Exception.Message)" -ForegroundColor Yellow }

    Write-Host "`nSMOKE COMPLETE: workspace $($ws.id) / investigation $($inv.id)" -ForegroundColor Green
}
finally {
    Remove-Item $jar, $zipPath -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:TEMP "meridian_smoke_body_*.json") -ErrorAction SilentlyContinue
    Remove-Item (Join-Path $env:TEMP "meridian_smoke_$stamp") -Recurse -ErrorAction SilentlyContinue
}
