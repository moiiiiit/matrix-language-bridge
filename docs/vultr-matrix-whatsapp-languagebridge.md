# Vultr Setup: Synapse + WhatsApp Bridge + LanguageBridge

This runbook documents an end-to-end setup for:

- Synapse homeserver on Docker
- HTTPS via Caddy + Let's Encrypt
- `mautrix-whatsapp` bridge
- LanguageBridge bot
- Matrix users (`@mohit:...`, `@languagebridge:...`)

It is written for a single VPS (Ubuntu) with domain:
`matrix.mohitbhole.net`.

---

## 0) Prerequisites

- VPS (Ubuntu 24.04+ recommended)
- Domain DNS control
- SSH access as root
- Docker + Compose plugin installed

Check:

```bash
docker --version
docker compose version
```

---

## 1) DNS and firewall

Create DNS record:

- `A matrix.mohitbhole.net -> <your_vps_ipv4>`

Open ports on VPS:

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8448/tcp
ufw status
```

`8448` is required for Matrix federation.

---

## 2) Synapse on Docker

Create Synapse directory:

```bash
mkdir -p /opt/matrix-synapse/data
cd /opt/matrix-synapse
```

Create `docker-compose.yml`:

```yaml
services:
  synapse:
    image: matrixdotorg/synapse:latest
    container_name: synapse
    restart: unless-stopped
    environment:
      - SYNAPSE_CONFIG_PATH=/data/homeserver.yaml
    volumes:
      - ./data:/data
    ports:
      - "127.0.0.1:8008:8008"
```

Generate initial config (first time only):

```bash
docker run --rm -it \
  -v /opt/matrix-synapse/data:/data \
  -e SYNAPSE_SERVER_NAME=matrix.mohitbhole.net \
  -e SYNAPSE_REPORT_STATS=no \
  matrixdotorg/synapse:latest generate
```

Key `homeserver.yaml` values:

- `server_name: "matrix.mohitbhole.net"`
- `public_baseurl: "https://matrix.mohitbhole.net"`
- listener on `8008` with `tls: false`, `x_forwarded: true`
- `app_service_config_files` (added later for WhatsApp bridge)

Start Synapse:

```bash
docker compose up -d
curl http://127.0.0.1:8008/_matrix/client/versions
```

---

## 3) HTTPS with Caddy

Install Caddy, then `/etc/caddy/Caddyfile`:

```caddyfile
matrix.mohitbhole.net {
    encode zstd gzip

    handle /.well-known/matrix/client {
        header Content-Type application/json
        respond `{"m.homeserver":{"base_url":"https://matrix.mohitbhole.net"}}`
    }

    handle /.well-known/matrix/server {
        header Content-Type application/json
        respond `{"m.server":"matrix.mohitbhole.net:8448"}`
    }

    reverse_proxy 127.0.0.1:8008
}

matrix.mohitbhole.net:8448 {
    reverse_proxy 127.0.0.1:8008
}
```

Reload:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

Verify:

```bash
curl https://matrix.mohitbhole.net/_matrix/client/versions
curl https://matrix.mohitbhole.net/_matrix/federation/v1/version
curl https://matrix.mohitbhole.net:8448/_matrix/federation/v1/version
```

---

## 4) Create Matrix users

Use Synapse helper inside container:

```bash
docker exec -it synapse register_new_matrix_user -c /data/homeserver.yaml
```

Create at least:

- `@mohit:matrix.mohitbhole.net` (human user)
- `@languagebridge:matrix.mohitbhole.net` (bot user)

You can also run non-interactively:

```bash
docker exec synapse register_new_matrix_user \
  -c /data/homeserver.yaml \
  -u languagebridge \
  -p '<strong-password>' \
  -a \
  http://localhost:8008
```

---

## 5) Deploy LanguageBridge repo

```bash
cd /opt
git clone https://github.com/moiiiiit/matrix-language-bridge.git matrix-language-bridge
cd /opt/matrix-language-bridge
```

Copy config:

```bash
cp config/config.example.yaml config/config.yaml
```

Fill `config/config.yaml`:

- `matrix.homeserver_url: "https://matrix.mohitbhole.net"`
- `matrix.user_id: "@languagebridge:matrix.mohitbhole.net"`
- set either:
  - `matrix.access_token`, or
  - `matrix.password` / `LB_MATRIX_PASSWORD`
- configure `llm.provider` and `llm.api_key`

Start LanguageBridge:

```bash
docker compose up -d languagebridge
docker compose logs -f --tail=200 languagebridge
```

---

## 6) Configure mautrix-whatsapp

Start from template:

```bash
cp whatsapp-data/config.example.yaml whatsapp-data/config.yaml
```

Set these in `whatsapp-data/config.yaml`:

- `homeserver.address: "http://synapse:8008"` (internal Docker network)
- `homeserver.domain: "matrix.mohitbhole.net"`
- `appservice.address: "http://whatsapp:29318"`
- `bridge.command_prefix: "!wa"`
- `bridge.permissions`:
  - `"matrix.mohitbhole.net": "user"`
  - `"@mohit:matrix.mohitbhole.net": "admin"`

Generate appservice registration:

```bash
docker run --rm \
  -v /opt/matrix-language-bridge/whatsapp-data:/data \
  --entrypoint /usr/bin/mautrix-whatsapp \
  dock.mau.dev/mautrix/whatsapp:latest \
  -g -c /data/config.yaml -r /data/registration.yaml
```

Install registration into Synapse:

```bash
cp /opt/matrix-language-bridge/whatsapp-data/registration.yaml \
   /opt/matrix-synapse/data/whatsapp-registration.yaml
chown 991:991 /opt/matrix-synapse/data/whatsapp-registration.yaml
chmod 644 /opt/matrix-synapse/data/whatsapp-registration.yaml
```

In `/opt/matrix-synapse/data/homeserver.yaml`:

```yaml
app_service_config_files:
  - /data/whatsapp-registration.yaml
```

Restart Synapse:

```bash
cd /opt/matrix-synapse
docker compose restart synapse
```

Start WhatsApp bridge:

```bash
cd /opt/matrix-language-bridge
docker compose --profile whatsapp up -d whatsapp
docker compose logs -f --tail=200 whatsapp
```

---

## 7) WhatsApp QR login flow

1. In Element, open DM with:
   - `@whatsappbot:matrix.mohitbhole.net`
2. Send:
   - `help` (or `!wa help`)
3. Start login command (see bridge help output; version may differ).
4. Scan QR code from WhatsApp mobile app:
   - WhatsApp -> Linked devices -> Link a device
5. Wait for connected confirmation in bot DM.

If you see "no usable logins found", the WhatsApp session is missing/expired.
Repeat QR login.

---

## 8) Connect LanguageBridge to bridged rooms

Invite `@languagebridge:matrix.mohitbhole.net` to target rooms.

Set explicit room policy in `config/config.yaml`:

```yaml
family:
  rooms:
    - "!roomA:matrix.mohitbhole.net"
    - "!roomB:matrix.mohitbhole.net"
  room_profiles:
    "!roomA:matrix.mohitbhole.net": marathi
    "!roomB:matrix.mohitbhole.net": charje_english_runes
  room_trigger_modes:
    "!roomA:matrix.mohitbhole.net": reaction
  reaction_trigger: "🌐"
```

Restart:

```bash
cd /opt/matrix-language-bridge
docker compose up -d languagebridge --force-recreate
```

---

## 9) Validate end-to-end

Checks:

```bash
# Synapse client API
curl -sS https://matrix.mohitbhole.net/_matrix/client/versions

# Federation
curl -sS https://matrix.mohitbhole.net/_matrix/federation/v1/version
curl -sS https://matrix.mohitbhole.net:8448/_matrix/federation/v1/version

# Services
cd /opt/matrix-synapse && docker compose ps
cd /opt/matrix-language-bridge && docker compose ps
```

Log tails:

```bash
cd /opt/matrix-synapse && docker compose logs -f --tail=200 synapse
cd /opt/matrix-language-bridge && docker compose logs -f --tail=200 languagebridge
cd /opt/matrix-language-bridge && docker compose logs -f --tail=200 whatsapp
```

---

## 10) Common issues

- **Element invite/profile shows 502**
  - Federation issue between your server and remote HS.
  - Ensure `8448` open and Caddy serving federation on `:8448`.

- **`PermissionError` under `/data/media_store/...`**
  - Fix owner:
    ```bash
    chown -R 991:991 /opt/matrix-synapse/data/media_store
    docker restart synapse
    ```

- **Bridge says not logged in**
  - Re-run WhatsApp QR login in `@whatsappbot` DM.

- **Reaction translations not triggering**
  - Ensure room has `room_trigger_modes[room]: reaction`
  - Ensure reaction emoji matches `reaction_trigger` (default 🌐)
  - React on the original message, not on bot replies

- **`git pull --ff-only` deploy fails on server**
  - Server repo has local edits. Clean/stash/commit server state first, or use immutable deploy artifact flow.

---

## 11) Important note: changing Synapse `server_name`

Changing `server_name` (e.g., IP -> domain) is effectively a new homeserver identity.
Plan for migration with backups and re-linking bridges.

Synapse reference: [Admin FAQ](https://element-hq.github.io/synapse/latest/usage/administration/admin_faq.html).
