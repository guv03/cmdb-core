<#
.SYNOPSIS
  로컬 개발 환경 기동: docker compose 기동 + DB 마이그레이션.

.USAGE
  PS> .\scripts\start.ps1
#>

docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

docker compose exec -T web python manage.py migrate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "기동 완료." -ForegroundColor Green
Write-Host "  대시보드: http://localhost:8000/dashboard/assets/"
Write-Host "  관리자:   http://localhost:8000/admin/"

