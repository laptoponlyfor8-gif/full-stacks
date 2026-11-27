import hashlib

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

_INCREMENT_WITH_EXPIRY = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def _opaque_key_part(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def enforce_rate_limit(
    request: Request,
    *,
    action: str,
    limit: int,
    identity: str | None = None,
) -> None:
    settings = request.app.state.settings
    redis_client = request.app.state.redis_client
    peer = request.client.host if request.client else "unknown"
    keys = [f"auth-rate:{action}:ip:{_opaque_key_part(peer)}"]
    if identity:
        keys.append(f"auth-rate:{action}:identity:{_opaque_key_part(identity.lower())}")

    try:
        for key in keys:
            count = await redis_client.eval(
                _INCREMENT_WITH_EXPIRY,
                1,
                key,
                settings.auth_rate_limit_window_seconds,
            )
            if int(count) > limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many attempts. Please wait and try again.",
                    headers={"Retry-After": str(settings.auth_rate_limit_window_seconds)},
                )
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable.",
        ) from exc
