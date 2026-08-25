from slowapi import Limiter
from slowapi.util import get_remote_address

# Keyed by request.client.host (slowapi's default). If a reverse proxy sits in
# front of the API, uvicorn must be run with --proxy-headers and a
# --forwarded-allow-ips restricted to that proxy's address for this to key by
# the real client IP instead of the proxy's; otherwise every request shares
# one bucket, which still bounds abusive volume but limits all clients
# together.
limiter = Limiter(key_func=get_remote_address)
