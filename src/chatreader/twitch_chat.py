"""Sends chat messages as the streamer's own Twitch account (device-code login, no password or token typed in)."""
import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

SCOPE = "user:write:chat"
DEVICE_URL = "https://id.twitch.tv/oauth2/device"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
VALIDATE_URL = "https://id.twitch.tv/oauth2/validate"
HELIX = "https://api.twitch.tv/helix"
MAX_MESSAGE = 500  # Twitch's chat message limit
TIMEOUT = 10


class TwitchError(Exception):
    pass


def _http(method: str, url: str, headers=None, form=None, body=None) -> tuple[int, dict]:
    data, headers = None, dict(headers or {})
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


class TwitchChat:
    def __init__(self, token_path: Path, http: Callable = _http, sleep: Callable[[float], None] = time.sleep):
        self._path = token_path
        self._http = http
        self._sleep = sleep
        self._lock = threading.Lock()
        self._channels: dict[str, str] = {}  # channel login -> user id
        self._tok = self._load()
        self._state = "connected" if self._tok.get("access_token") else "off"

    def status(self) -> str:
        """off, waiting (for the person to approve), connected or error."""
        return self._state

    def start_auth(self, client_id: str, wait: bool = True) -> dict:
        """Ask Twitch for a code; the person approves it in a browser while we poll in the background."""
        status, body = self._http("POST", DEVICE_URL, form={"client_id": client_id, "scopes": SCOPE})
        if status != 200 or "device_code" not in body:
            raise TwitchError(str(body.get("message") or f"Twitch answered {status}"))
        self._state = "waiting"
        if wait:
            args = (client_id, body["device_code"], int(body.get("interval", 5)), int(body.get("expires_in", 600)))
            threading.Thread(target=self.wait_for_approval, args=args, name="chatreader-twitch-auth", daemon=True).start()
        return {"user_code": body["user_code"], "verification_uri": body["verification_uri"]}

    def wait_for_approval(self, client_id: str, device_code: str, interval: int, expires_in: int) -> None:
        form = {"client_id": client_id, "scopes": SCOPE, "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}
        waited = 0
        try:
            while waited < expires_in:
                self._sleep(interval)
                waited += interval
                status, body = self._http("POST", TOKEN_URL, form=form)
                if status == 200:
                    self._finish_login(client_id, body)
                    return
                if body.get("message") != "authorization_pending":
                    break
        except Exception:
            log.exception("twitch login failed")
        self._state = "error"

    def _finish_login(self, client_id: str, body: dict) -> None:
        status, who = self._http("GET", VALIDATE_URL, headers={"Authorization": f"OAuth {body['access_token']}"})
        if status != 200 or "user_id" not in who:
            raise TwitchError("could not check the new login")
        self._store({"client_id": client_id, "access_token": body["access_token"],
                     "refresh_token": body.get("refresh_token", ""), "user_id": who["user_id"], "login": who.get("login", "")})
        self._state = "connected"

    def send(self, client_id: str, channel: str, text: str) -> bool:
        """Post one message in the channel's chat. Never raises; False means it was not sent."""
        try:
            with self._lock:
                if not self._tok.get("access_token") or self._tok.get("client_id") != client_id:
                    return False
                channel = channel.lower()
                if channel not in self._channels:
                    status, body = self._helix("GET", f"/users?login={urllib.parse.quote(channel)}", client_id)
                    if status != 200 or not body.get("data"):
                        log.warning("twitch: channel %s not found (%s)", channel, status)
                        return False
                    self._channels[channel] = body["data"][0]["id"]
                message = {"broadcaster_id": self._channels[channel], "sender_id": self._tok["user_id"], "message": text[:MAX_MESSAGE]}
                status, body = self._helix("POST", "/chat/messages", client_id, body=message)
                if status != 200:
                    log.warning("twitch: message not sent (%s: %s)", status, body.get("message", ""))
                return status == 200
        except Exception:
            log.exception("twitch: message not sent")
            return False

    def _helix(self, method: str, path: str, client_id: str, body=None) -> tuple[int, dict]:
        for attempt in (0, 1):
            headers = {"Authorization": f"Bearer {self._tok['access_token']}", "Client-Id": client_id}
            status, answer = self._http(method, HELIX + path, headers=headers, body=body)
            if status != 401 or attempt or not self._refresh(client_id):
                return status, answer
        return status, answer

    def _refresh(self, client_id: str) -> bool:
        status, body = self._http("POST", TOKEN_URL, form={"client_id": client_id, "grant_type": "refresh_token",
                                                           "refresh_token": self._tok.get("refresh_token", "")})
        if status != 200 or "access_token" not in body:
            self._state = "error"
            return False
        self._store({**self._tok, "access_token": body["access_token"], "refresh_token": body.get("refresh_token", self._tok.get("refresh_token", ""))})
        return True

    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, ValueError):
            log.warning("%s is unreadable, log in to Twitch again", self._path)
            return {}

    def _store(self, tok: dict) -> None:
        self._tok = tok
        try:
            self._path.write_text(json.dumps(tok), encoding="utf-8")
        except OSError:
            log.exception("could not save %s", self._path)
