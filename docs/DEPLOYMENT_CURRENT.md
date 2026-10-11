# Current single-host deployment path

Status, 12 October 2026: the five-service Compose configuration parses and its
secret guards pass static checks. This host cannot run the Docker daemon, so
container startup and cross-container extraction have **not** been verified.
The automatic extractor itself remains a supervised pilot: the latest frozen
2,000-source no-model gate released no documents and linked no complete rows.
Do not present this deployment as validated production document extraction.

## Stack and prerequisites

The default [production Compose file](../docker-compose.prod.yml) starts
PostgreSQL with pgvector, Redis, the FastAPI gateway, the private extraction
worker, and the Next.js frontend. Four older research services require the
`research` profile and are outside the product path. Use a Linux host with
Docker Engine, the Compose plugin, Python 3, enough RAM and disk for the
documents you will actually process, and a backup destination. The
configuration has not established a minimum cloud instance size.

## First deployment

From a checkout of the desired revision on the host:

```bash
bash scripts/deploy-vps.sh PUBLIC_DNS_NAME_OR_IPV4
```

The script writes `.env.production` only if absent, with independent random
database, Redis, JWT, and initial admin credentials. It sets mode `0600`,
validates Compose, builds the images, and waits for the five default services
to become healthy. The file is ignored by Git. Store a secure backup of it and
of the PostgreSQL volume. The initial admin password is in that file; the
gateway consumes it only if no admin account exists.

On later runs the script reuses the same credentials. Never regenerate or edit
the database/Redis passwords independently of their existing volumes. A
pre-existing `.env.production` must include
`POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET_KEY`,
`ADMIN_PASSWORD`, `BACKEND_CORS_ORIGINS`, and
`NEXT_PUBLIC_API_URL`; empty secrets fail Compose validation.

The generated URLs use plain HTTP on ports 3000 and 8000 for initial private
host checks. Before exposing the service to untrusted users, configure TLS,
reverse proxy/firewall access, and set `NEXT_PUBLIC_API_URL` and
`BACKEND_CORS_ORIGINS` to the actual public HTTPS origins. Rebuild the frontend
after changing `NEXT_PUBLIC_API_URL`, because Next.js embeds this value into
client assets. Keep PostgreSQL and Redis ports bound to localhost.

For manual inspection without printing interpolated secrets:

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml config --quiet
docker compose --env-file .env.production -f docker-compose.prod.yml ps
docker compose --env-file .env.production -f docker-compose.prod.yml logs --tail=100
```

The Compose commands and variable interpolation follow
[Docker's CLI reference](https://docs.docker.com/reference/cli/docker/compose/),
[configuration validation](https://docs.docker.com/reference/cli/docker/compose/config),
and [environment file rules](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).
Neither a healthy stack nor a 2,000-source run demonstrates extraction accuracy;
consult the [system contract](SYSTEM_CONTRACT.md) and
[latest gate](evaluations/VRDU_2000_NO_MODEL_V7_PDFIUM.md).
