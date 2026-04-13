#!/usr/bin/env bash
# Initialise une instance HA fraîche via l'API onboarding.
# Crée un compte admin dev et configure les étapes requises.
# Usage : ./scripts/init_ha_dev.sh [http://localhost:8123]

set -euo pipefail

HA_URL="${1:-http://localhost:8123}"
USERNAME="admin"
PASSWORD="admin"
CLIENT_ID="${HA_URL}/"

echo "Attente du démarrage de Home Assistant..."
until curl -sf "${HA_URL}/api/" -o /dev/null 2>&1; do
  sleep 2
done
echo "Home Assistant est prêt."

echo "Création de l'utilisateur admin..."
RESPONSE=$(curl -sf -X POST "${HA_URL}/api/onboarding/users" \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"${CLIENT_ID}\",
    \"name\": \"Admin\",
    \"username\": \"${USERNAME}\",
    \"password\": \"${PASSWORD}\",
    \"language\": \"fr\"
  }")

AUTH_CODE=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['auth_code'])")

echo "Configuration de la localisation..."
curl -sf -X POST "${HA_URL}/api/onboarding/core_config" \
  -H "Authorization: Bearer ${AUTH_CODE}" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"${CLIENT_ID}\"}" > /dev/null

echo "Validation analytics..."
curl -sf -X POST "${HA_URL}/api/onboarding/analytics" \
  -H "Authorization: Bearer ${AUTH_CODE}" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"${CLIENT_ID}\"}" > /dev/null

echo "Validation intégration..."
curl -sf -X POST "${HA_URL}/api/onboarding/integration" \
  -H "Authorization: Bearer ${AUTH_CODE}" \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"${CLIENT_ID}\", \"redirect_uri\": \"${HA_URL}/?auth_callback=1\"}" > /dev/null

echo ""
echo "Initialisation terminée !"
echo "  URL      : ${HA_URL}"
echo "  Login    : ${USERNAME}"
echo "  Password : ${PASSWORD}"
