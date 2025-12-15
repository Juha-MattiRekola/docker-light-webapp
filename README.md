# Docker Mikropalvelut

Kevyt Docker-mikropalvelusovellus, joka esittelee Docker-osaamista. 8 konttia, yksi verkko.

## Arkkitehtuuri

```
                    ┌─────────────┐
                    │   Selain    │
                    └──────┬──────┘
                           │ :80
                    ┌──────┴──────┐
                    │    nginx    │ ← Reverse Proxy
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
   ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
   │  /api/*     │  │   HTML      │  │   Tunnel    │
   │  Flask API  │  │  Staattinen │  │  Cloudflare │
   └──────┬──────┘  └─────────────┘  └─────────────┘
          │
    ┌─────┴─────┐
    │           │
┌───┴────┐  ┌───┴───┐
│Postgres│  │ Redis │
│ :5432  │  │ :6379 │
└────────┘  └───────┘
```

| Kontti | Kuvaus | Portti |
|--------|--------|--------|
| **nginx** | Reverse proxy + staattiset sivut | :80 |
| **api** | Python Flask backend | :5000 (sisäinen) |
| **db** | PostgreSQL tietokanta | :5432 (sisäinen) |
| **redis** | Välimuisti | :6379 (sisäinen) |
| **adminer** | Tietokannan hallinta | :8080 |
| **prometheus** | Metriikoiden keruu | :9090 |
| **grafana** | Monitorointi | :3000 |
| **tunnel** | Cloudflare tunneli | - |

---

## Käynnistys

### Peruskomennot

```bash
# Käynnistä kaikki kontit taustalle
docker compose up -d

# Käynnistä ja rakenna imaget uudelleen
docker compose up -d --build

# Seuraa lokeja reaaliajassa
docker compose logs -f

# Seuraa tietyn kontin lokeja
docker compose logs -f api

# Pysäytä kaikki kontit
docker compose down

# Pysäytä ja poista myös volyymit (VAROITUS: poistaa tietokannan!)
docker compose down -v
```

### Käynnistysskriptit

Skriptit käynnistävät kaikki kontit ja näyttävät Cloudflare-tunnelin julkisen URL:n automaattisesti.

#### Linux / macOS (Bash)

```bash
# 1. Navigoi projektikansioon
cd /polku/docker-light

# 2. Anna suoritusoikeus (vain kerran)
chmod +x start.sh

# 3. Käynnistä
./start.sh
```

#### Windows (PowerShell)

```powershell
# 1. Navigoi projektikansioon
cd C:\polku\docker-light

# 2. Salli skriptien suoritus (vain kerran, vaatii admin-oikeudet)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# 3. Käynnistä
.\start.ps1
```

**Vinkki:** Voit avata PowerShellin suoraan projektikansiossa kirjoittamalla File Explorerin osoitepalkkiin `powershell` ja painamalla Enter.

#### VS Codessa

1. Avaa terminaali: `Ctrl+ö` (tai `Ctrl+``)
2. Varmista että olet projektikansiossa
3. Aja skripti:
   - **Linux/Mac:** `./start.sh`
   - **Windows:** `.\start.ps1`

#### Skriptien tulostus

```
Käynnistetään Docker Compose...
Odotetaan Cloudflare-tunnelia...

✓ Palvelut käynnissä!

Julkinen URL: https://random-words.trycloudflare.com
Lokaali:      http://localhost
```

---

## Cloudflare-tunneli

Projekti sisältää Cloudflare-tunnelin, joka luo julkisen HTTPS-osoitteen automaattisesti.

### Tunnelin osoitteen hakeminen

**Linux/Mac (Bash):**
```bash
docker compose logs tunnel | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1
```

**Windows (PowerShell):**
```powershell
docker compose logs tunnel 2>&1 | Select-String "trycloudflare"
```

**Windows (CMD):**
```cmd
docker compose logs tunnel 2>&1 | findstr "trycloudflare"
```

Tunnelin URL vaihtuu joka käynnistyskerralla.

---

## Palvelut

| Sivu | URL | Kuvaus |
|------|-----|--------|
| Etusivu | http://localhost/ | Pääsivu ja navigaatio |
| Muistiinpanot | http://localhost/notes.html | CRUD + PostgreSQL + Redis |
| Muistipeli | http://localhost/muistipeli.html | Peli tallennuksella |
| Kuvatyökalu | http://localhost/api/image | Pikselitehoste |
| Arkkitehtuuri | http://localhost/arkkitehtuuri.html | Tekninen dokumentaatio |
| Docker-perusteet | http://localhost/docker.html | Docker-opas |
| Docker Compose | http://localhost/compose.html | Compose-opas |

### Hallintatyökalut

| Työkalu | URL | Tunnukset |
|---------|-----|-----------|
| Adminer | http://localhost:8080 | postgres / postgres |
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin / admin |

---

## API

### Muistiinpanot

```bash
# Hae kaikki muistiinpanot
curl http://localhost/api/notes

# Lisää muistiinpano
curl -X POST http://localhost/api/notes \
  -H "Content-Type: application/json" \
  -d '{"content": "Otsikko|Sisältö tähän"}'

# Muokkaa muistiinpanoa
curl -X PUT http://localhost/api/notes/1 \
  -H "Content-Type: application/json" \
  -d '{"content": "Uusi otsikko|Uusi sisältö"}'

# Poista muistiinpano
curl -X DELETE http://localhost/api/notes/1
```

### Muistipelin tallennukset (Redis)

```bash
# Hae kaikki tallennukset
curl http://localhost/api/memory/saves

# Tallenna peli
curl -X POST http://localhost/api/memory/save \
  -H "Content-Type: application/json" \
  -d '{"name": "Peli 1", "state": {"cards": [], "matched": 0}}'

# Lataa tallennettu peli
curl http://localhost/api/memory/load/Peli%201

# Poista tallennus
curl -X DELETE http://localhost/api/memory/delete/Peli%201
```

### Health check ja metriikat

```bash
# Tarkista API:n tila
curl http://localhost/health

# Prometheus-metriikat
curl http://localhost/api/metrics
```

---

## Docker-komennot

### Imaget

```bash
# Listaa projektiin liittyvät imaget
docker images | grep docker-light

# Rakenna imaget uudelleen
docker compose build

# Rakenna tietty image uudelleen
docker compose build api

# Poista käyttämättömät imaget
docker image prune
```

### Kontit

```bash
# Listaa käynnissä olevat kontit
docker compose ps

# Listaa kaikki kontit (myös pysäytetyt)
docker ps -a

# Käynnistä yksittäinen kontti uudelleen
docker compose restart api

# Avaa shell konttiin
docker compose exec api sh

# Suorita komento kontissa
docker compose exec db psql -U postgres -d notes -c "SELECT * FROM notes;"
```

### Volyymit

```bash
# Listaa volyymit
docker volume ls

# Tarkastele volyymin tietoja
docker volume inspect docker-light_db_data

# Poista käyttämättömät volyymit
docker volume prune
```

### Verkot

```bash
# Listaa verkot
docker network ls

# Tarkastele projektin verkkoa
docker network inspect docker-light_default
```

### Siivous

```bash
# Poista kaikki pysäytetyt kontit
docker container prune

# Poista kaikki käyttämättömät resurssit
docker system prune

# Poista kaikki volumet (varoitus!). Vastaa "y" tai "yes" mikäli haluat poistaa volumet.
docker system prune -a --volumes
```

---

## Tiedostorakenne

```
docker-light/
├── docker-compose.yaml     # Palvelumäärittelyt (8 konttia)
├── prometheus.yml          # Prometheus scrape config
├── start.sh                # Käynnistysskripti (Bash, Linux)
├── start.ps1               # Käynnistysskripti (PowerShell)
├── README.md               # Tämä dokumentaatio
├── api/
│   ├── Dockerfile          # Python 3.12-alpine
│   ├── app.py              # Flask-sovellus
│   └── requirements.txt    # flask, pillow, psycopg2, redis
├── nginx/
│   ├── Dockerfile          # nginx:stable-alpine
│   └── nginx.conf          # Reverse proxy config
└── html/
    ├── index.html          # Etusivu
    ├── notes.html          # Muistiinpanot
    ├── muistipeli.html     # Muistipeli
    ├── arkkitehtuuri.html  # Arkkitehtuuridokumentaatio
    ├── docker.html         # Docker-perusteet
    └── compose.html        # Docker Compose -opas
```

---

## Docker-ominaisuudet

Projektissa käytetyt Docker-ominaisuudet:

- **Multi-container** - 8 erillistä palvelua samassa verkossa
- **Reverse Proxy** - Nginx ohjaa liikennettä sisäisille palveluille
- **Volumes** - PostgreSQL-data säilyy `db_data` volumessa
- **Bind mounts** - HTML-tiedostot kehitystä varten (`:ro`)
- **Environment variables** - Tietokanta- ja Redis-yhteydet
- **Health checks** - API:n terveystarkistus ennen nginx-käynnistystä
- **depends_on + condition** - Palveluiden käynnistysjärjestys ja -ehdot
- **Custom images** - Omat Dockerfilet nginx:lle ja API:lle
- **Alpine images** - Pienet, turvalliset base imaget
- **Cloudflare tunnel** - Julkinen HTTPS ilman porttien avausta

---

## Teema

Kaikilla sivuilla on tumma/vaalea teemavaihto. Teema tallennetaan selaimen localStorageen ja säilyy sivujen välillä.
