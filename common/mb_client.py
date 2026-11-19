# ======================================================================
# MetaForge Common: MusicBrainz HTTP client
# Role: The ONE way MetaForge talks to the MusicBrainz web service.
# Physical Location: \common\mb_client.py
# ======================================================================
"""
Shared MusicBrainz client (added 2026-11-13).

Why this exists -- real bug, reported by John: pressing "Search
MusicBrainz" sometimes showed "No matches found" when MusicBrainz had
simply answered 503 "The MusicBrainz web server is currently busy"
(reproduced live 2026-11-13). MusicBrainz allows roughly one request per
second per IP address, counted across EVERYTHING sent from this machine.
Each tool used to keep its own separate delay, so two tools (or two
requests in one tool) could still collide, and nothing retried.

What this client does for every caller:
  1. One shared pace for the whole app: a process-wide lock guarantees at
     least MIN_INTERVAL seconds between any two MusicBrainz requests,
     whichever tool sends them.
  2. Retries on "busy"/temporary failures (HTTP 502/503/504, connection
     errors, timeouts), waiting longer each time and honouring MB's own
     Retry-After header when it sends one.
  3. A timeout on every request, so a stalled connection can't hang a tool.
  4. When every attempt fails, raises MusicBrainzUnavailable with a plain-
     language message the UI can show as-is.

get() returns a normal requests.Response that has already passed
raise_for_status(), so existing callers keep using .json() unchanged.
Other HTTP errors (e.g. 404 for an ID that doesn't exist) are NOT
retried and raise requests.HTTPError exactly as before.
"""
import threading
import time

import requests

from common import config_handler

BASE_URL = "https://musicbrainz.org/ws/2/"
MIN_INTERVAL = 1.1          # seconds between ANY two MusicBrainz requests
TIMEOUT = 20                # seconds before one attempt is abandoned
MAX_ATTEMPTS = 4            # 1 try + 3 retries
RETRY_STATUSES = {502, 503, 504}
MAX_RETRY_WAIT = 10         # cap on any single wait, seconds

_session = requests.Session()
_pace_lock = threading.Lock()
_last_request_at = 0.0


class MusicBrainzUnavailable(requests.exceptions.RequestException):
    """MusicBrainz could not be reached / stayed busy after every retry."""

    def __init__(self, attempts, last_problem):
        self.attempts = attempts
        self.last_problem = last_problem
        super().__init__(
            "MusicBrainz is busy or unreachable right now "
            f"(it limits how often it can be asked). MetaForge tried {attempts} times. "
            "Wait a few seconds and try again."
        )


def _wait_for_turn():
    """Block until MIN_INTERVAL has passed since the last request (any tool)."""
    global _last_request_at
    wait = MIN_INTERVAL - (time.monotonic() - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _retry_wait(attempt, response=None):
    """Seconds to wait before the next attempt: MB's Retry-After if given, else growing."""
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return min(int(retry_after), MAX_RETRY_WAIT)
    return min(1.5 * attempt, MAX_RETRY_WAIT)


def get(endpoint_or_url, params=None, headers=None, timeout=TIMEOUT):
    """
    GET a MusicBrainz web-service resource.

    endpoint_or_url: either a path relative to BASE_URL ("release/<mbid>",
    "recording", ...) or a full https://musicbrainz.org/ws/2/... URL.
    fmt=json is added automatically.
    """
    url = endpoint_or_url if endpoint_or_url.startswith("http") else BASE_URL + endpoint_or_url.lstrip("/")
    params = dict(params or {})
    params.setdefault("fmt", "json")
    # Every MusicBrainz request identifies MetaForge the same way, with the
    # user's email as MusicBrainz asks (config_handler.USER_AGENT).
    hdrs = {"User-Agent": config_handler.USER_AGENT(with_email=True), "Accept": "application/json"}
    if headers:
        hdrs.update(headers)

    last_problem = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = None
        with _pace_lock:
            _wait_for_turn()
            try:
                response = _session.get(url, params=params, headers=hdrs, timeout=timeout)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_problem = f"{type(e).__name__}: {e}"

        if response is not None:
            if response.status_code not in RETRY_STATUSES:
                response.raise_for_status()   # non-retryable errors surface as before
                return response
            last_problem = f"HTTP {response.status_code}"

        if attempt < MAX_ATTEMPTS:
            print(f"[mb_client] MusicBrainz attempt {attempt} failed ({last_problem}); retrying")
            time.sleep(_retry_wait(attempt, response))

    raise MusicBrainzUnavailable(MAX_ATTEMPTS, last_problem)
