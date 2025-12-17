#!/bin/bash

# Ylimääräinen toiminto: Skripti käynnistää Docker Compose -määritellyt mikropalvelut ja näyttää niiden tilatiedot.
# Docker Mikropalvelut - Automatisoitu käynnistysskripti Linux/MacOS.
# Tämä skripti käynnistää Docker Compose -määritellyt mikropalvelut ja näyttää niiden tilatiedot.
# Lopuksi se hakee Cloudflare-tunnelin julkisen URL-osoitteen ja näyttää sen käyttäjälle.


# Vaiheet käynnistämiseet:

# 1. Mene projektin kansioon PowerShell-terminaalissa. Esimerkiksi: cd /home/jmr/docker-yhteenveto/docker-light
# 2. Anna suoritusoikeus: chmod +x start.sh
# 3. Suorita tämä skripti komennolla: ./start.sh

# Värimäärittelyt
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Ei väriä

echo -e "${CYAN}"
echo "  ╔════════════════════════════════════════╗"
echo "  ║     Docker Mikropalvelut               ║"
echo "  ╚════════════════════════════════════════╝"
echo -e "${NC}"

# Käynnistä kontit
echo -e "${YELLOW}Käynnistetään kontteja...${NC}"
if ! docker compose up -d; then
    echo -e "\n${RED}════════════════════════════════════════${NC}"
    echo -e "${RED}  Virhe: Docker Compose epäonnistui!${NC}"
    echo -e "${RED}════════════════════════════════════════${NC}"
    echo -e "\n  Tarkista Docker-tila: ${CYAN}docker ps${NC}"
    echo -e "  Katso lokit: ${CYAN}docker compose logs${NC}\n"
    exit 1
fi

# Tarkista että kontit ovat käynnissä
sleep 2
RUNNING_COUNT=$(docker compose ps --status running -q 2>/dev/null | wc -l)
EXPECTED_COUNT=$(docker compose config --services 2>/dev/null | wc -l)

if [ "$RUNNING_COUNT" -eq 0 ]; then
    echo -e "\n${RED}════════════════════════════════════════${NC}"
    echo -e "${RED}  Virhe: Yhtään konttia ei käynnissä!${NC}"
    echo -e "${RED}════════════════════════════════════════${NC}"
    echo -e "\n  Tarkista lokit: ${CYAN}docker compose logs${NC}\n"
    exit 1
elif [ "$RUNNING_COUNT" -lt "$EXPECTED_COUNT" ]; then
    echo -e "\n${YELLOW}════════════════════════════════════════${NC}"
    echo -e "${YELLOW}  Varoitus: Vain $RUNNING_COUNT/$EXPECTED_COUNT konttia käynnissä${NC}"
    echo -e "${YELLOW}════════════════════════════════════════${NC}"
fi

# Odota että tunnel-kontti käynnistyy
echo -e "${YELLOW}Odotetaan Cloudflare-tunnelia...${NC}"
sleep 5

# Hae tunnelin URL lokeista (max 30 sekuntia). Hyödynnetään grep ja regex.
for i in {1..30}; do
    TUNNEL_URL=$(docker compose logs tunnel 2>/dev/null | grep -oP 'https://[a-z0-9-]+\.trycloudflare\.com' | tail -1)
    if [ -n "$TUNNEL_URL" ]; then
        break
    fi
    sleep 1
done

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Palvelut käynnissä!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "  Lokaali:     ${CYAN}http://localhost${NC}"
echo -e "  Adminer:     ${CYAN}http://localhost:8080${NC}"
echo -e "  Prometheus:  ${CYAN}http://localhost:9090${NC}"
echo -e "  Grafana:     ${CYAN}http://localhost:3000${NC}"
echo ""

if [ -n "$TUNNEL_URL" ]; then
    echo -e "  ${GREEN}Julkinen osoite:    ${YELLOW}${TUNNEL_URL}${NC}"
    echo ""
    echo -e "  Kopioi tästä linkki: ${TUNNEL_URL}"
else
    echo -e "  ${YELLOW}Tunneli ei vielä valmis. Tarkista:${NC}"
    echo -e "  docker compose logs tunnel | grep trycloudflare"
fi

echo ""
