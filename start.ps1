# Windows PowerShell, Automatisoitu käynnistysskripti
# Skripti käynnistää Docker Compose -määritellyt mikropalvelut ja näyttää niiden tilatiedot.
# Lopuksi se hakee Cloudflare-tunnelin julkisen URL-osoitteen ja näyttää sen käyttäjälle.

# Vaiheet käynnistämiseen:

# 1. Avaa PowerShell-terminaali ja siirry projektin kansioon. Esimerkiksi: cd C:\polku\docker-yhteenveto\docker-light
# 2. Aseta skriptien suoritus sallituksi: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
# 3. Suorita tämä skripti komennolla: .\start.ps1

Write-Host ""
Write-Host "  ╔════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     Docker Mikropalvelut               ║" -ForegroundColor Cyan
Write-Host "  ╚════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# Käynnistä kontit
Write-Host "Käynnistetään kontteja..." -ForegroundColor Yellow
docker compose up -d
$composeExitCode = $LASTEXITCODE

if ($composeExitCode -ne 0) {
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Red
    Write-Host "  Virhe: Docker Compose epäonnistui!" -ForegroundColor Red
    Write-Host "════════════════════════════════════════" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Tarkista Docker-tila: " -NoNewline; Write-Host "docker ps" -ForegroundColor Cyan
    Write-Host "  Katso lokit: " -NoNewline; Write-Host "docker compose logs" -ForegroundColor Cyan
    Write-Host ""
    exit 1
}

# Tarkista että kontit ovat käynnissä
Start-Sleep -Seconds 2
$runningContainers = (docker compose ps --status running -q 2>$null | Measure-Object -Line).Lines
$expectedServices = (docker compose config --services 2>$null | Measure-Object -Line).Lines

if ($runningContainers -eq 0) {
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Red
    Write-Host "  Virhe: Yhtään konttia ei käynnissä!" -ForegroundColor Red
    Write-Host "════════════════════════════════════════" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Tarkista lokit: " -NoNewline; Write-Host "docker compose logs" -ForegroundColor Cyan
    Write-Host ""
    exit 1
} elseif ($runningContainers -lt $expectedServices) {
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  Varoitus: Vain $runningContainers/$expectedServices konttia käynnissä" -ForegroundColor Yellow
    Write-Host "════════════════════════════════════════" -ForegroundColor Yellow
}

# Odota että tunnel-kontti käynnistyy
Write-Host "Odotetaan Cloudflare-tunnelia..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# Hae tunnelin URL lokeista (max 30 sekuntia). Hyödynnetään regexiä.
$tunnelUrl = $null
for ($i = 1; $i -le 30; $i++) {
    $logs = docker compose logs tunnel 2>&1
    $match = [regex]::Match($logs, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($match.Success) {
        $tunnelUrl = $match.Value
        break
    }
    Start-Sleep -Seconds 1
}

Write-Host ""
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Palvelut käynnissä!" -ForegroundColor Green
Write-Host "════════════════════════════════════════" -ForegroundColor Green
Write-Host ""
Write-Host "  Lokaali:     " -NoNewline; Write-Host "http://localhost" -ForegroundColor Cyan
Write-Host "  Adminer:     " -NoNewline; Write-Host "http://localhost:8080" -ForegroundColor Cyan
Write-Host "  Prometheus:  " -NoNewline; Write-Host "http://localhost:9090" -ForegroundColor Cyan
Write-Host "  Grafana:     " -NoNewline; Write-Host "http://localhost:3000" -ForegroundColor Cyan
Write-Host ""

if ($tunnelUrl) {
    Write-Host "  Julkinen:    " -NoNewline -ForegroundColor Green
    Write-Host $tunnelUrl -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Kopioi linkki: $tunnelUrl"
} else {
    Write-Host "  Tunneli ei vielä valmis. Tarkista:" -ForegroundColor Yellow
    Write-Host "  docker compose logs tunnel | Select-String trycloudflare"
}

Write-Host ""
