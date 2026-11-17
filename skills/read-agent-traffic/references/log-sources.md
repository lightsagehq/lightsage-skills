# Getting logs out of each platform

Read when the user needs to export logs, or a file does not parse. Platform menus and plan limits change; when a step does not match what the user sees, ask them to check the platform's current docs.

The analyzer needs, per request: user agent, path (or full URL), status, time. Referrer, client IP and host make the report better. Any format below works; so does any CSV or JSON with those fields (`--map` for odd column names).

Contents
1. nginx and Apache
2. Vercel
3. Cloudflare
4. Netlify
5. AWS CloudFront
6. Other sources
7. Coverage traps

## 1. nginx and Apache

- Default files: `/var/log/nginx/access.log*`, `/var/log/apache2/access.log*` or `/var/log/httpd/access_log*`. Rotated files are often `.gz`; pass them all.
- Needs the combined format (`$http_referer` and `$http_user_agent`). The plain common format has no user agent and is useless here. vhost-prefixed combined works.
- Behind a CDN, `$remote_addr` is the CDN's IP; log the real client IP (`$http_cf_connecting_ip`, `X-Forwarded-For`) if you want `--verify-ips`.

## 2. Vercel

- Log drains (JSON or NDJSON to an HTTP endpoint, or an integration) carry every request, including cached and static responses, with `proxy.userAgent`, `proxy.path`, `proxy.statusCode`, `proxy.clientIp`, `proxy.referer`. Save a day of drain payloads and pass the files.
- Dashboard Logs and `vercel logs` show recent runtime logs only (retention depends on plan) and may omit cached hits; fine for a quick look, not for a week of agent traffic.
- Middleware-based tracking misses cached pages served without running middleware.

## 3. Cloudflare

- Logpush (Enterprise): the HTTP requests dataset as NDJSON to R2, S3 or similar. Include at least `ClientRequestUserAgent`, `ClientRequestURI` (or `ClientRequestPath`), `ClientRequestHost`, `EdgeResponseStatus`, `EdgeStartTimestamp`, `ClientIP`, `ClientRequestReferer`. Add `VerifiedBotCategory` if available; it is Cloudflare's own verified-bot label.
- GraphQL Analytics API (other plans; sampled, limited retention): save the response and pass it as is.
  ```bash
  cat > q.json <<'EOF'
  {"query": "query { viewer { zones(filter: {zoneTag: \"ZONE_ID\"}) { httpRequestsAdaptiveGroups(limit: 10000, filter: {date_geq: \"2026-11-01\", date_leq: \"2026-11-07\"}, orderBy: [count_DESC]) { count dimensions { date clientRequestHTTPHost clientRequestPath userAgent edgeResponseStatus clientRequestReferer } } } } }"}
  EOF
  curl -s https://api.cloudflare.com/client/v4/graphql -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H 'Content-Type: application/json' -d @q.json > cf.json
  ```
  The token needs Analytics read for the zone. Counts are estimates; there is no client IP, so no `--verify-ips`. If the result hits the limit, query a day at a time.
- Quick cross-check without exports: the dashboard's AI crawler and bot analytics (AI Crawl Control, Security > Bots) show per-crawler requests and what was blocked.

## 4. Netlify

- Log drains (higher plans) send traffic logs as JSON with `user_agent`, `url`, `status_code`, `client_ip`, `referrer`, `timestamp`. Export from the destination (S3, Datadog, HTTP endpoint).
- Without drains, Netlify's observability views are aggregated; they do not list user agents per request.

## 5. AWS CloudFront

- Standard logs (to S3) are W3C tab-separated files with a `#Fields:` header and URL-encoded user agents; the analyzer reads them directly (`.gz` too). Real-time logs via Kinesis can be exported as CSV or JSON.

## 6. Other sources

- Fastly, Akamai, Azure Front Door, Google Cloud CDN, Kubernetes ingress: export JSON or CSV with the fields above.
- Warehouse tables (BigQuery, Snowflake, Datadog): `SELECT timestamp, host, path, status, user_agent, referer, client_ip` for the period to CSV.
- GA4 and most product analytics: not usable for agents (they need JavaScript). Usable only for the human AI-referral section, and only if the user exports sessions with referrer and landing page.

## 7. Coverage traps

- CDN logs see everything; origin logs behind a CDN miss cached hits, which is most crawler traffic to static pages.
- Docs are often on another host or a hosted docs platform with its own logs. Ask.
- Sampled logs (GraphQL adaptive, some CDN tiers) undercount rare agents.
- Time zones: exports are usually UTC; say so when the user compares with their own dashboards.
