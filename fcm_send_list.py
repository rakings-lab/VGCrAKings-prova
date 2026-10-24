#!/usr/bin/env python3
"""PROVA: legge l'archivio iscritti (worker Cloudflare di prova), sceglie chi ha attivato il canale
e manda la notifica a ognuno con Firebase. Toglie dall'archivio i token morti.
Segreti e token non vengono mai stampati nel log (dei token si vedono solo gli ultimi 6 caratteri)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import google.auth.transport.requests
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]
UA = "rAKings-VGC-bot/1.0"


def http(url, data=None, headers=None, timeout=30):
    h = {"User-Agent": UA}
    h.update(headers or {})
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=timeout)


def pick(subs, topic):
    """Stessa logica di subs_for() del sito vero."""
    if topic.upper() == "TUTTI":
        return list(subs)
    if topic.startswith("t-"):
        return [s for s in subs if topic[2:] in (s.get("f") or [])]
    one = topic.endswith("-1h")
    cat = topic[:-3] if one else topic
    base = "money" if cat in ("money", "money33") else cat
    want = "money=all" if cat == "money" else "money=33" if cat == "money33" else cat
    return [s for s in subs if want in (s.get("c") or []) and (not one or base in (s.get("h") or []))]


def main():
    sa = os.environ.get("FCM_SERVICE_ACCOUNT", "").strip()
    base = os.environ.get("SUBS_URL", "").strip().rstrip("/")
    adm = os.environ.get("SUBS_TOKEN", "").strip()
    topic = os.environ.get("FCM_TOPIC", "").strip() or "gc"
    title = os.environ.get("FCM_TITLE", "").strip() or "Prova rAKings"
    body = os.environ.get("FCM_BODY", "").strip()
    link = os.environ.get("FCM_LINK", "").strip()
    dry = os.environ.get("DRY_RUN", "si").strip().lower() != "no"
    if not (sa and base and adm):
        sys.exit("Mancano FCM_SERVICE_ACCOUNT, SUBS_URL o SUBS_TOKEN (Settings > Secrets and variables > Actions).")
    try:
        info = json.loads(sa)
    except ValueError:
        sys.exit("FCM_SERVICE_ACCOUNT non e' un JSON valido.")

    try:
        r = http(base + "/list?kind=fcm", headers={"Authorization": "Bearer " + adm})
        subs = json.loads(r.read().decode("utf-8")).get("subs") or []
    except urllib.error.HTTPError as e:
        sys.exit("Archivio iscritti: HTTP %s%s" % (e.code, " (SUBS_TOKEN diverso da ADMIN_TOKEN del worker?)" if e.code == 401 else ""))
    chosen = pick(subs, topic)
    print("Archivio: %d token Firebase. Canale '%s': %d corrispondenti." % (len(subs), topic, len(chosen)))
    for s in chosen:
        print("  - ...%s  scelte=%s" % (s["id"][-6:], ",".join(s.get("c") or [])))
    if dry:
        print("PROVA A SECCO: nessuna notifica inviata. Rilancia con dry_run = no per inviare.")
        return
    if not chosen:
        print("Nessuno da avvisare.")
        return

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(google.auth.transport.requests.Request())
    access = creds.token
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % info["project_id"]
    data = {"title": title, "body": body}
    if link:
        data["link"] = link

    def send_one(tok):
        payload = json.dumps({"message": {"token": tok, "notification": {"title": title, "body": body}, "data": data}}).encode("utf-8")
        hdr = {"Authorization": "Bearer " + access, "Content-Type": "application/json; charset=UTF-8"}
        for attempt in range(4):
            try:
                http(url, payload, hdr).read()
                return "ok", ""
            except urllib.error.HTTPError as e:
                msg = e.read().decode("utf-8", "replace")
                if e.code == 404 or "UNREGISTERED" in msg or "not a valid FCM registration token" in msg:
                    return "dead", ""
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                return "err", "%s %s" % (e.code, msg[:150].replace("\n", " "))
            except Exception as e:  # rete
                if attempt < 3:
                    time.sleep(2 * (attempt + 1))
                    continue
                return "err", str(e)[:150]

    ids = [s["id"] for s in chosen]
    with ThreadPoolExecutor(max_workers=10) as ex:
        res = list(ex.map(send_one, ids))
    ok = sum(1 for r_ in res if r_[0] == "ok")
    dead = [t for t, r_ in zip(ids, res) if r_[0] == "dead"]
    errs = [(t, r_[1]) for t, r_ in zip(ids, res) if r_[0] == "err"]
    print("Inviate: %d. Token morti: %d. Errori: %d." % (ok, len(dead), len(errs)))
    for t, m in errs[:5]:
        print("  errore ...%s: %s" % (t[-6:], m))
    for k in range(0, len(dead), 200):
        try:
            http(base + "/remove", json.dumps({"ids": dead[k:k + 200]}).encode("utf-8"),
                 {"Authorization": "Bearer " + adm, "Content-Type": "text/plain"}).read()
        except Exception as e:
            print("Pulizia token morti non riuscita:", str(e)[:100])
    if dead:
        print("Token morti tolti dall'archivio: %d." % len(dead))
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    main()
