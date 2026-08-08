# Security Review — v0.3.4

## Dashboard

| Control | Status |
|---------|--------|
| Default bind 127.0.0.1 | Yes |
| Non-loopback warning | Yes |
| Auth | Not implemented (local-only assumption) |
| CSRF on POST | N/A — read-only routes in current console |
| Jinja autoescape | Default on |
| Export Markdown | Escaped / plain text, no raw HTML |
| Secrets in templates | Webhooks not rendered |

## Collectors

| Control | Status |
|---------|--------|
| No CAPTCHA bypass | Policy enforced |
| No auth cookie jars | Yes |
| User-Agent identifies Clank | Yes |
| Rate limiting / min_delay | In BaseCollector |
| SSRF | URLs from config/sitemap only; do not fetch user-supplied URLs without allowlist |

## YAML / config

- Load trusted local files only.
- Do not load untrusted remote YAML.

## Logging

- Do not log Discord webhook URLs or tokens.
- Model numbers and public URLs are fine.

## Residual

- LAN bind without auth is unsafe — keep localhost.
- Future POST analyst actions need CSRF tokens + session auth.

## Verdict

Adequate for **localhost single-operator** deployment. Not hardened for multi-user or internet exposure.
