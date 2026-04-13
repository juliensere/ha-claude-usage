#!/usr/bin/env python3
"""
Retourne l'usage Claude en JSON pour Home Assistant (command_line sensor).

Config stockée dans ~/.config/claude-usage/config.json (créé automatiquement).

Premier lancement (initialisation) :
    python3 check_session_usage.py --setup

Utilisation normale :
    python3 check_session_usage.py

Sortie JSON :
    {
      "status": "ok",
      "session_5h":  { "utilization": 29.0, "resets_at": "...", "resets_in_minutes": 45 },
      "weekly":      { "utilization": 16.0, "resets_at": "...", "resets_in_minutes": 4380 },
      "extra_usage": { "used": 0.0, "limit": 2000, "utilization": 0.0 },
      "last_updated": "2026-04-13T21:00:00Z"
    }

En cas d'erreur :
    { "status": "error", "error": "session_expired", "message": "..." }
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from http.cookiejar import CookieJar
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor
from urllib.error import HTTPError, URLError
from urllib.parse import quote

CONFIG_PATH = Path.home() / ".config" / "claude-usage" / "config.json"
BASE_URL    = "https://claude.ai"

# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(config: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)

def setup():
    print("=== Configuration claude-usage ===")
    print()
    print("1. Ouvre claude.ai dans ton navigateur (connecté)")
    print("2. F12 → Application → Cookies → https://claude.ai")
    print()
    session_key = input("  Valeur de 'sessionKey'    : ").strip()
    if not session_key:
        print("Erreur : valeur vide.")
        sys.exit(1)

    cf_clearance = input("  Valeur de 'cf_clearance' : ").strip()
    if not cf_clearance:
        print("Erreur : valeur vide. Cloudflare bloque les requêtes sans ce cookie.")
        sys.exit(1)

    print()
    print("3. F12 → Network → recharge claude.ai/settings/usage")
    print("   Cherche une requête /api/organizations/<uuid>/usage")
    print()
    org_id = input("  org_id (UUID) : ").strip()
    if not org_id:
        print("Erreur : valeur vide.")
        sys.exit(1)

    config = {"session_key": session_key, "cf_clearance": cf_clearance, "org_id": org_id}
    save_config(config)
    print()
    print(f"Config sauvegardée dans {CONFIG_PATH}")
    print("Test en cours...")
    print()

    data = fetch_usage(session_key, cf_clearance, org_id)
    if data:
        print("OK — connexion réussie.")
        result = build_output(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_usage(session_key: str, cf_clearance: str, org_id: str) -> dict | None:
    """
    Fait la requête avec les cookies et headers nécessaires pour passer Cloudflare.
    Renouvelle automatiquement sessionKey et cf_clearance si le serveur en retourne
    de nouveaux via Set-Cookie.
    """
    url = f"{BASE_URL}/api/organizations/{org_id}/usage"

    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))

    cookie_header = f"sessionKey={quote(session_key, safe='')}; cf_clearance={quote(cf_clearance, safe='')}"

    req = Request(url, method="GET")
    req.add_header("cookie",           cookie_header)
    req.add_header("accept",           "application/json, text/plain, */*")
    req.add_header("accept-language",  "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7")
    req.add_header("accept-encoding",  "gzip, deflate")
    req.add_header("referer",          "https://claude.ai/settings/usage")
    req.add_header("sec-fetch-dest",   "empty")
    req.add_header("sec-fetch-mode",   "cors")
    req.add_header("sec-fetch-site",   "same-origin")
    req.add_header("user-agent",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )

    try:
        with opener.open(req, timeout=10) as resp:
            raw = resp.read()
            # Décompression gzip si nécessaire
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding == "gzip":
                import gzip
                raw = gzip.decompress(raw)
            elif encoding == "br":
                try:
                    import brotli
                    raw = brotli.decompress(raw)
                except ImportError:
                    pass  # brotli optionnel, urllib demande rarement br

            data = json.loads(raw)

            # Renouvellement automatique des cookies si le serveur en envoie de nouveaux
            updates = {}
            for cookie in jar:
                if cookie.name == "sessionKey" and cookie.value != session_key:
                    updates["session_key"] = cookie.value
                if cookie.name == "cf_clearance" and cookie.value != cf_clearance:
                    updates["cf_clearance"] = cookie.value

            if updates:
                config = load_config()
                config.update(updates)
                save_config(config)

            return data

    except HTTPError as e:
        if e.code in (401, 403):
            body = e.read().decode("utf-8", errors="replace")
            if "cf-" in body.lower() or "cloudflare" in body.lower() or "just a moment" in body.lower():
                raise CloudflareBlocked()
            raise SessionExpired()
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:200]}")
    except URLError as e:
        raise RuntimeError(f"Réseau : {e.reason}")


class SessionExpired(Exception):
    pass

class CloudflareBlocked(Exception):
    pass

# ── Output ────────────────────────────────────────────────────────────────────

def minutes_until(iso: str) -> int | None:
    try:
        dt  = datetime.fromisoformat(iso)
        now = datetime.now(timezone.utc)
        return max(0, int((dt - now).total_seconds() / 60))
    except Exception:
        return None

def build_output(data: dict) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def parse_slot(key: str) -> dict | None:
        entry = data.get(key)
        if not entry:
            return None
        resets_at = entry.get("resets_at")
        return {
            "utilization":        entry.get("utilization") or 0.0,
            "resets_at":          resets_at,
            "resets_in_minutes":  minutes_until(resets_at) if resets_at else None,
        }

    extra = data.get("extra_usage") or {}
    used  = extra.get("used_credits") or 0.0
    limit = extra.get("monthly_limit") or 0

    return {
        "status":       "ok",
        "session_5h":   parse_slot("five_hour"),
        "weekly":       parse_slot("seven_day"),
        "weekly_sonnet":parse_slot("seven_day_sonnet"),
        "weekly_opus":  parse_slot("seven_day_opus"),
        "extra_usage": {
            "enabled":      extra.get("is_enabled", False),
            "used":         used,
            "limit":        limit,
            "utilization":  round(used / limit * 100, 1) if limit else 0.0,
        },
        "last_updated": now,
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def error_json(code: str, message: str) -> dict:
    return {
        "status":  "error",
        "error":   code,
        "message": message,
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

def main():
    global CONFIG_PATH

    parser = argparse.ArgumentParser()
    parser.add_argument("--setup", action="store_true", help="Configuration initiale")
    parser.add_argument("--config", help=f"Chemin config (défaut: {CONFIG_PATH})")
    args = parser.parse_args()

    if args.config:
        CONFIG_PATH = Path(args.config)

    if args.setup:
        setup()
        return

    config      = load_config()
    session_key  = config.get("session_key")  or os.environ.get("CLAUDE_SESSION_KEY", "")
    cf_clearance = config.get("cf_clearance") or os.environ.get("CLAUDE_CF_CLEARANCE", "")
    org_id       = config.get("org_id")       or os.environ.get("CLAUDE_ORG_ID", "")

    if not session_key or not org_id or not cf_clearance:
        print(json.dumps(error_json(
            "not_configured",
            f"Lancer avec --setup. Config attendue dans : {CONFIG_PATH}"
        )))
        sys.exit(1)

    try:
        data   = fetch_usage(session_key, cf_clearance, org_id)
        result = build_output(data)
        print(json.dumps(result, ensure_ascii=False))

    except CloudflareBlocked:
        print(json.dumps(error_json(
            "cloudflare_blocked",
            f"cf_clearance expiré. Relancer --setup et copier un nouveau cf_clearance depuis le navigateur."
        )))
        sys.exit(2)

    except SessionExpired:
        print(json.dumps(error_json(
            "session_expired",
            f"sessionKey expirée. Relancer --setup."
        )))
        sys.exit(2)

    except Exception as e:
        print(json.dumps(error_json("fetch_error", str(e))))
        sys.exit(3)


if __name__ == "__main__":
    main()
