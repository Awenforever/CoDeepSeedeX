param(
  [switch]$DryRun
)

Write-Host "CodeXchange Windows installer bootstrap"
Write-Host "Recommended path: install inside WSL/Linux first."
Write-Host ""
Write-Host "Run in WSL:"
Write-Host "  git clone <repo-url> ~/codexchange"
Write-Host "  cd ~/codexchange"
Write-Host "  bash scripts/install.sh"
Write-Host ""
if (Get-Command wsl.exe -ErrorAction SilentlyContinue) {
  Write-Host "WSL is available on this machine."
} else {
  Write-Host "WSL was not detected. Install WSL first or use Linux/macOS."
}
if ($DryRun) {
  Write-Host "Dry run only. No changes were made."
}
