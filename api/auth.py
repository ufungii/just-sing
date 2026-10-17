"""Auth0 access-token verification. The frontend logs in with Auth0 and sends the token as
`Authorization: Bearer ...`; we check signature, issuer, audience and expiry."""
import os
from functools import lru_cache

import jwt

from .errors import ApiError


@lru_cache
def _jwks():
    return jwt.PyJWKClient(f"https://{os.environ['AUTH0_DOMAIN']}/.well-known/jwks.json")


def signing_key(token: str):
    return _jwks().get_signing_key_from_jwt(token).key


def verify_bearer(token: str) -> str:
    """Return the token's Auth0 user id (sub), or raise a 401 error."""
    if not os.getenv("AUTH0_DOMAIN") or not os.getenv("AUTH0_AUDIENCE"):
        raise ApiError(503, "auth_unavailable", "Login is not configured on this server.")
    try:
        claims = jwt.decode(token, signing_key(token), algorithms=["RS256"],
                            audience=os.environ["AUTH0_AUDIENCE"],
                            issuer=f"https://{os.environ['AUTH0_DOMAIN']}/")
    except jwt.PyJWTError:
        raise ApiError(401, "invalid_token", "The login token is invalid or expired.")
    return claims["sub"]
