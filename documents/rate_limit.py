import sys
import time

from django.core.cache import cache


def check_rate_limit(key, limit, period):
    cache_key = f"rl:{key}"

    data = cache.get(cache_key)
    now = time.time()

    print(f"[RL] {key}: checking", file=sys.stderr)

    if data is None:
        print(f"[RL] {key}: first request", file=sys.stderr)
        cache.set(cache_key, {"count": 1, "window_start": now}, timeout=period)
        return True, limit - 1, 0

    if now - data["window_start"] > period:
        print(f"[RL] {key}: window expired, resetting", file=sys.stderr)
        cache.set(cache_key, {"count": 1, "window_start": now}, timeout=period)
        return True, limit - 1, 0

    data["count"] += 1
    print(f"[RL] {key}: count={data['count']}, limit={limit}", file=sys.stderr)

    if data["count"] > limit:
        retry_after = int(period - (now - data["window_start"]))
        print(f"[RL] {key}: LIMIT EXCEEDED! retry_after={retry_after}", file=sys.stderr)
        return False, 0, retry_after

    cache.set(cache_key, data, timeout=period)
    remaining = limit - data["count"]

    return True, remaining, 0
