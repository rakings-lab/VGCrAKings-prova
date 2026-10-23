#!/usr/bin/env python3
"""Invio di PROVA di una notifica Firebase (FCM) a UN solo dispositivo.
Solo per la repo di prova. Il segreto FCM_SERVICE_ACCOUNT arriva dai GitHub Secrets:
non viene mai scritto nei file ne' stampato nel log."""
import json
import os
import sys
import urllib.error
import urllib.request

import google.auth.transport.requests
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]


def main():
    raw = os.environ.get("FCM_SERVICE_ACCOUNT", "").strip()
    token = os.environ.get("FCM_TOKEN", "").strip()
    title = os.environ.get("FCM_TITLE", "").strip() or "Prova rAKings"
    body = os.environ.get("FCM_BODY", "").strip()
    link = os.environ.get("FCM_LINK", "").strip()
    if not raw:
        sys.exit("Manca il segreto FCM_SERVICE_ACCOUNT (Settings > Secrets and variables > Actions).")
    if not token:
        sys.exit("Manca il token del dispositivo.")
    try:
        info = json.loads(raw)
    except ValueError:
        sys.exit("Il segreto FCM_SERVICE_ACCOUNT non e' un JSON valido: incolla di nuovo tutto il contenuto del file.")
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(google.auth.transport.requests.Request())

    data = {"title": title, "body": body}
    if link:
        data["link"] = link
    payload = {"message": {"token": token, "data": data}}
    url = "https://fcm.googleapis.com/v1/projects/%s/messages:send" % info["project_id"]
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + creds.token,
                 "Content-Type": "application/json; charset=UTF-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("OK, risposta %s: %s" % (r.status, r.read().decode("utf-8")[:300]))
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:600]
        print("ERRORE %s: %s" % (e.code, msg))
        if "UNREGISTERED" in msg or "NOT_FOUND" in msg:
            print("Il token non e' piu' valido: riattiva le notifiche sul dispositivo e riprova.")
        sys.exit(1)


if __name__ == "__main__":
    main()
