"""
Bypass Garmin SSO rate limit by using existing browser session cookies.

Steps:
1. Log into connect.garmin.com in your browser (already done)
2. Open DevTools (F12) -> Application -> Cookies -> https://sso.garmin.com
3. Copy ALL cookies as a single string (name=value; name=value; ...)
4. Run: uv run python browser_auth.py
"""

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs

import requests
from requests_oauthlib import OAuth1Session

DOMAIN = "garmin.com"
TOKEN_DIR = Path.home() / ".config" / "garmin-connect-cli" / "tokens"
SSO = f"https://sso.{DOMAIN}/sso"
SSO_EMBED = f"{SSO}/embed"
SSO_LOGIN = f"{SSO}/login"
SSO_EMBED_PARAMS = {
    "clientId": "GarminConnect",
    "locale": "en",
    "gauthHost": SSO,
    "service": SSO_EMBED,
    "source": SSO_EMBED,
    "redirectAfterAccountLoginUrl": SSO_EMBED,
    "redirectAfterAccountCreationUrl": SSO_EMBED,
}
OAUTH_CONSUMER_URL = "https://thegarth.s3.amazonaws.com/oauth_consumer.json"
MOBILE_UA = {"User-Agent": "com.garmin.android.apps.connectmobile"}


def get_consumer():
    resp = requests.get(OAUTH_CONSUMER_URL)
    resp.raise_for_status()
    return resp.json()


def parse_cookies(cookie_str: str) -> dict:
    cookies = {}
    for pair in cookie_str.split(";"):
        pair = pair.strip()
        if "=" in pair:
            name, value = pair.split("=", 1)
            cookies[name.strip()] = value.strip()
    return cookies


def get_ticket(sess: requests.Session) -> str:
    # Strategy 1: CAS standard flow — GET /sso/login?service=... with CASTGC cookie
    # The CAS server validates the TGT and redirects to service?ticket=ST-xxx
    print("Trying CAS ticket grant (GET /sso/login with CASTGC)...")
    resp = sess.get(
        SSO_LOGIN,
        params={"service": SSO_EMBED, "clientId": "GarminConnect"},
        timeout=15,
        allow_redirects=False,
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code in (301, 302, 303):
        location = resp.headers.get("Location", "")
        print(f"  Redirect: {location[:100]}")
        m = re.search(r'ticket=(ST-[^"&\s]+)', location)
        if m:
            return m.group(1)

    # Strategy 2: Follow the redirect and look in the final URL or body
    print("Trying SSO embed with clientId=GarminConnect...")
    resp = sess.get(SSO_EMBED, params=SSO_EMBED_PARAMS, timeout=15)
    print(f"  Status: {resp.status_code}, Final URL: {resp.url[:100]}")

    m = re.search(r'ticket=(ST-[^"&\s]+)', resp.url)
    if m:
        return m.group(1)

    m = re.search(r'embed\?ticket=([^"&\s]+)', resp.text)
    if m:
        return m.group(1)

    # Show response snippet to help debug
    print("\n--- Response snippet (no ticket found) ---")
    print(resp.text[:800])
    print("------------------------------------------")
    return ""


def exchange_ticket_for_tokens(ticket: str, consumer: dict) -> tuple[dict, dict]:
    preauth_url = (
        f"https://connectapi.{DOMAIN}/oauth-service/oauth/"
        f"preauthorized?ticket={ticket}"
        f"&login-url={SSO_EMBED}&accepts-mfa-tokens=true"
    )
    oauth1_sess = OAuth1Session(consumer["consumer_key"], consumer["consumer_secret"])
    resp = oauth1_sess.get(preauth_url, headers=MOBILE_UA, timeout=15)
    resp.raise_for_status()

    parsed = parse_qs(resp.text)
    oauth1 = {k: v[0] for k, v in parsed.items()}
    oauth1["domain"] = DOMAIN

    oauth1_sess2 = OAuth1Session(
        consumer["consumer_key"],
        consumer["consumer_secret"],
        resource_owner_key=oauth1["oauth_token"],
        resource_owner_secret=oauth1["oauth_token_secret"],
    )
    headers = {**MOBILE_UA, "Content-Type": "application/x-www-form-urlencoded"}
    data = {"mfa_token": oauth1["mfa_token"]} if "mfa_token" in oauth1 else {}

    resp = oauth1_sess2.post(
        f"https://connectapi.{DOMAIN}/oauth-service/oauth/exchange/user/2.0",
        headers=headers,
        data=data,
        timeout=15,
    )
    resp.raise_for_status()
    oauth2 = resp.json()
    now = int(time.time())
    oauth2["expires_at"] = now + oauth2["expires_in"]
    oauth2["refresh_token_expires_at"] = now + oauth2["refresh_token_expires_in"]

    return oauth1, oauth2


def save_tokens(oauth1: dict, oauth2: dict):
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    (TOKEN_DIR / "oauth1_token.json").write_text(json.dumps(oauth1, indent=2))
    (TOKEN_DIR / "oauth2_token.json").write_text(json.dumps(oauth2, indent=2))
    print(f"\nTokens saved to {TOKEN_DIR}")


def main():
    print("Paste cookies from DevTools -> Application -> Cookies -> sso.garmin.com")
    print("Format: name=value; name=value; ...")
    print()
    cookie_str = input("Cookies: ").strip()
    if not cookie_str:
        sys.exit("No cookies provided.")

    cookies = parse_cookies(cookie_str)
    print(f"Parsed {len(cookies)} cookies: {', '.join(cookies.keys())}")

    sess = requests.Session()
    sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for name, value in cookies.items():
        sess.cookies.set(name, value, domain=".garmin.com")

    print("\nRequesting SSO ticket using browser session...")
    ticket = get_ticket(sess)

    if not ticket:
        print("\nCould not extract ticket. Try copying cookies from sso.garmin.com")
        print("Make sure you include CASTGC or GARMIN-SSO if present.")
        sys.exit(1)

    print(f"Got ticket: {ticket[:30]}...")

    print("Fetching OAuth consumer credentials...")
    consumer = get_consumer()

    print("Exchanging ticket for OAuth tokens...")
    oauth1, oauth2 = exchange_ticket_for_tokens(ticket, consumer)

    save_tokens(oauth1, oauth2)
    print("\nDone! Test with: uv run garmin-connect context")


if __name__ == "__main__":
    main()
