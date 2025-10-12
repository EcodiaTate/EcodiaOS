# Kills any python/uvicorn processes by command line match
$procs = Get-CimInstance Win32_Process |
  Where-Object {
    ($_.Name -match 'python.exe' -or $_.Name -match 'uvicorn.exe') -and
    ($_.CommandLine -match 'uvicorn' -or $_.CommandLine -match 'api:app' -or $_.CommandLine -match '5454')
  }

if (!$procs) {
  Write-Host "No uvicorn processes found."
  exit 0
}

$procs | ForEach-Object {
  Write-Host ("Killing PID {0} : {1}" -f $_.ProcessId, ($_.CommandLine -replace '\s+', ' '))
  Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 200
Write-Host "Done."
