Write-Host "=== EcodiaOS Clean Eject Script ===" -ForegroundColor Cyan

# --- Stop Docker ---
Write-Host "Stopping Docker service..."
Stop-Service com.docker.service -ErrorAction SilentlyContinue

Write-Host "Shutting down WSL..."
wsl --shutdown

# --- Close Chrome (including background apps) ---
Write-Host "Closing Chrome..."
Stop-Process -Name chrome -Force -ErrorAction SilentlyContinue

# --- Kill common dev processes that might hold files open ---
Write-Host "Stopping Python/Node processes..."
Get-Process python, node, npm -ErrorAction SilentlyContinue | Stop-Process -Force

Write-Host "Stopping Docker/Container processes..."
Get-Process *docker*, *containerd* -ErrorAction SilentlyContinue | Stop-Process -Force

# --- Optional: Kill VSCode if it’s using your SSD projects ---
Write-Host "Closing VSCode..."
Stop-Process -Name Code -Force -ErrorAction SilentlyContinue

# --- Pause to let things settle ---
Start-Sleep -Seconds 3

Write-Host "All major processes stopped. You can now safely eject the SSD." -ForegroundColor Green
