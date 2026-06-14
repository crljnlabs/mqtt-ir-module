# Reverse proxy (base path + optional API key injection)

## When do you need a reverse proxy?

Only if you set `API_KEY` and you want to keep the key out of the browser.

If `API_KEY` is not set, you can run without a proxy and everything works in your private LAN.

## What the proxy should do

1) Expose the app under a base path (for example `/mqtt-ir-module/`).  
2) Forward requests to the container while stripping the prefix.  
3) (Optional) Inject `X-API-Key` for write endpoints.

## Container configuration

Set `PUBLIC_BASE_URL` inside the container:

- `PUBLIC_BASE_URL=/mqtt-ir-module/`

The backend injects this into the frontend at runtime so routing + API calls work under the prefix.

## Nginx (concept)

```nginx
# UI + API under /mqtt-ir-module/
location /mqtt-ir-module/ {
  proxy_pass http://mqtt-ir-module:80/;  # trailing slash strips the prefix
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-Proto $scheme;  # lets the hub build https firmware URLs for ESP32 OTA

  # Optional: inject API key server-side (browser never sees the key)
  # proxy_set_header X-API-Key "change-me";
}
```

## Traefik (concept)

Use:
- Router: `PathPrefix(`/mqtt-ir-module`)`
- Middleware: StripPrefix(`/mqtt-ir-module`)
- Optional middleware to add a request header `X-API-Key`.

## HTTPS and ESP32 OTA

ESP32 OTA always downloads firmware over plain HTTP (`force_scheme="http"`
in `build_firmware_url`). The hub derives the hostname from the `hub_public_url`
setting (configured in Settings → Connection) and ignores the request scheme for
OTA URLs. This avoids TLS overhead on memory-constrained devices and eliminates
301 redirect loops (`ota_http_status_invalid`).

**Required nginx configuration when TLS is terminated at the proxy:**

Add a separate port-80 server block that passes `/firmware/` through to the
container while still redirecting everything else to HTTPS:

```nginx
server {
    listen 80;
    server_name <hub-hostname>;

    # OTA firmware download: ESP32 connects here directly over plain HTTP.
    # Integrity is ensured by the SHA-256 check in the firmware client.
    location /firmware/ {
        proxy_pass http://<container-host>:<port>/firmware/;
        proxy_set_header Host $host;
    }
    location / {
        return 301 https://$host$request_uri;
    }
}
```

The browser-based Web Flasher continues to use the `hub_public_url` scheme
(`https://`) and is not affected by this exception.

`X-Forwarded-Proto` (see the Nginx example above) is not required for OTA, but
is still recommended for other hub routes that construct absolute URLs
(e.g. Home Assistant discovery links).

## Security notes

- Do not rely on CORS/Origin/Referer as security. Clients can replicate frontend requests.
- Best practice: do not publish the backend container port directly if you use `API_KEY`.
