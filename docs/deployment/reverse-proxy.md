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

When the proxy terminates TLS, it must forward the original scheme via
`X-Forwarded-Proto` (see the Nginx example). The hub runs uvicorn with
`--proxy-headers`, so it trusts this header and builds firmware download URLs
with the correct `https://` scheme. Without it the hub emits `http://` URLs that
the proxy answers with a 301 redirect, which the ESP32 OTA client cannot follow
(`ota_http_status_invalid`).

## Security notes

- Do not rely on CORS/Origin/Referer as security. Clients can replicate frontend requests.
- Best practice: do not publish the backend container port directly if you use `API_KEY`.
