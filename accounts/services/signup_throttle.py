"""IP-based rate limit on the signup view (OPS_RUNBOOK §10.16).

Sliding window of POST-attempt timestamps kept in the default Django cache,
keyed by client IP (X-Forwarded-For first, same extraction as
management.utils.log_action). Soft gate: the view shows a warning message and
re-renders the form — never a 500. Defense-in-depth alongside the honeypot in
SignUpForm and the email-verification step, not a hard gate.

Known limit: with the default LocMemCache the counter is per-process, so with
N gunicorn workers the effective cap is up to N * MAX_ATTEMPTS. Accepted as
best-effort until a shared cache backend exists (no new infra for this).
"""
from django.core.cache import cache
from django.utils import timezone

SIGNUP_THROTTLE_MAX_ATTEMPTS = 5
SIGNUP_THROTTLE_WINDOW_SECONDS = 600
SIGNUP_THROTTLE_CACHE_PREFIX = 'signup_throttle'


def _client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or 'unknown'


def throttle_cache_key(request) -> str:
    return f'{SIGNUP_THROTTLE_CACHE_PREFIX}:{_client_ip(request)}'


def _recent_attempts(request) -> list:
    now_ts = timezone.now().timestamp()
    attempts = cache.get(throttle_cache_key(request), [])
    return [ts for ts in attempts if now_ts - ts < SIGNUP_THROTTLE_WINDOW_SECONDS]


def is_throttled(request) -> bool:
    """True if this IP has exhausted its attempts in the current window."""
    return len(_recent_attempts(request)) >= SIGNUP_THROTTLE_MAX_ATTEMPTS


def record_attempt(request) -> None:
    """Record one signup POST for this IP; the window slides per-attempt."""
    attempts = _recent_attempts(request)
    attempts.append(timezone.now().timestamp())
    cache.set(throttle_cache_key(request), attempts,
              timeout=SIGNUP_THROTTLE_WINDOW_SECONDS)
