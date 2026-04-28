# LanguageBridge

A standalone Matrix bot that automatically detects and translates foreign-language messages in group chats, posting translations as threaded replies. Designed for multilingual family chats across WhatsApp, Telegram, Signal, and iMessage via existing Matrix bridges.

**First-class support for romanized Marathi, Hindi, and code-switched Indic/English text** — the use case that existing translation bots handle poorly or not at all.

## Quickstart

```bash
# 1. Clone
git clone https://github.com/moiiiiit/matrix-language-bridge.git
cd matrix-language-bridge

# 2. Create config/config.yaml from template
make setup

# 3. Edit config/config.yaml — fill in your Matrix credentials and LLM API key
#    (see sections below for how to get these)

# 4. Start with Docker
make docker-up
```

That's it. The bot joins your rooms and starts translating.

## Run Commands

```bash
# Build images
make docker-build

# Start background service (uses config/config.yaml)
make run

# Foreground local-like run with config/config-local.yaml and ./data bind mount
make run-local

# Start optional WhatsApp bridge service
make docker-whatsapp-up

# Run tests in Docker
make test

# View logs / stop
make docker-logs
make docker-whatsapp-logs
make docker-down
```

### Generate config from parameters (cloud-friendly)

You can generate `config/config.yaml` entirely from environment variables:

```bash
LB_FAMILY_NAME="Kulkarni Family" \
LB_PROFILE="default" \
LB_TRIGGER_MODE="auto" \
LB_REACTION_TRIGGER="🌐" \
LB_COMMAND_PREFIX="!translate" \
LB_ROOMS="!roomA:matrix.org,!roomB:matrix.org" \
LB_ROOM_PROFILES="!roomA:matrix.org=default,!roomB:matrix.org=charje_english_runes" \
LB_MATRIX_HOMESERVER_URL="https://matrix.org" \
LB_MATRIX_ACCESS_TOKEN="syt_..." \
LB_MATRIX_USER_ID="@languagebridge:matrix.org" \
LB_LLM_PROVIDER="anthropic" \
LB_LLM_API_KEY="sk-ant-..." \
LB_LLM_MODEL="claude-haiku-4-5-20251001" \
make config-from-env
```

Notes:
- Use `LB_ROOMS="*"` to watch all joined rooms.
- Use `LB_ROOM_PROFILES="!roomA:matrix.org=default,!roomB:matrix.org=charje_english_runes"` for per-room profile overrides.
- For Ollama, set `LB_LLM_PROVIDER="ollama"` and optionally `LB_LLM_OLLAMA_URL`.
- For [Charje phonetic runes](http://charje.net/phonetic-table-of-english.html), set `LB_PROFILE=charje_english_runes`.
- You can also run `python -m languagebridge.config_gen --help` for flag-based usage.

## Getting a Matrix Access Token

### Element (web/desktop)

1. Open Element and sign in with the account you want the bot to use
2. Go to **Settings** (gear icon) > **Help & About**
3. Scroll down to **Advanced** > click **Access Token** (it may be hidden — click to reveal)
4. Copy the token starting with `syt_...`

### Beeper

1. Open Beeper settings
2. Navigate to **Account** > **Advanced**
3. Copy the access token

> **Tip:** Create a dedicated Matrix account for the bot (e.g. `@languagebridge:matrix.org`) rather than using your personal account.

## Connecting Messaging Apps

LanguageBridge works with any messages that appear in your Matrix rooms. To bring in messages from other platforms, use the mautrix bridge ecosystem:

| Platform   | Bridge                                                                      |
| ---------- | --------------------------------------------------------------------------- |
| WhatsApp   | [mautrix-whatsapp](https://docs.mau.fi/bridges/go/whatsapp/index.html)     |
| Telegram   | [mautrix-telegram](https://docs.mau.fi/bridges/python/telegram/index.html) |
| Signal     | [mautrix-signal](https://docs.mau.fi/bridges/go/signal/index.html)         |
| iMessage   | [mautrix-imessage](https://docs.mau.fi/bridges/go/imessage/index.html)     |
| Instagram  | [mautrix-meta](https://docs.mau.fi/bridges/go/meta/index.html)             |
| Google Chat | [mautrix-googlechat](https://docs.mau.fi/bridges/python/googlechat/index.html) |

Each bridge runs as a separate service and creates Matrix rooms that mirror your chats. LanguageBridge then monitors those rooms for messages to translate.

### WhatsApp bridge (mautrix-whatsapp) quickstart

This repository now includes an optional `whatsapp` Docker Compose profile.

1. Start the bridge container:

   ```bash
   make docker-whatsapp-up
   ```

2. Follow bridge setup logs:

   ```bash
   make docker-whatsapp-logs
   ```

3. Complete the official mautrix-whatsapp appservice + QR-link flow:
   - [mautrix-whatsapp docs](https://docs.mau.fi/bridges/go/whatsapp/index.html)
4. Once linked, WhatsApp chats appear as Matrix rooms; add those room IDs to `family.rooms` or `family.room_profiles` in LanguageBridge config.
5. Start from templates:
   - `whatsapp-data/config.example.yaml` -> `whatsapp-data/config.yaml`
   - `config/config-local-whatsapp.example.yaml` -> `config/config-local.yaml` (or another config path)

Notes:
- Bridge data persists under `./whatsapp-data` (gitignored).
- You can stop only the bridge with:
  ```bash
  make docker-whatsapp-down
  ```

## LLM Provider Setup

LanguageBridge supports four LLM providers. Set the `llm.provider` field in your config.

### Anthropic (recommended)

```yaml
llm:
  provider: anthropic
  api_key: "sk-ant-..."
```

Get an API key at [console.anthropic.com](https://console.anthropic.com). Default model: `claude-haiku-4-5-20251001` (fast, cheap, excellent at Indic languages).

### OpenAI

```yaml
llm:
  provider: openai
  api_key: "sk-..."
```

Get an API key at [platform.openai.com](https://platform.openai.com). Default model: `gpt-4o-mini`.

### Google Gemini

```yaml
llm:
  provider: gemini
  api_key: "AI..."
```

Get an API key at [aistudio.google.com](https://aistudio.google.com). Default model: `gemini-2.0-flash`.

### Ollama (free, local, private)

```yaml
llm:
  provider: ollama
  ollama_url: "http://ollama:11434"  # or http://localhost:11434 if running outside Docker
```

No API key needed. Runs entirely on your hardware.

**Setup:**

1. Uncomment the `ollama` service in `docker-compose.yml`
2. Start the stack: `make docker-up`
3. Pull a model: `docker compose exec ollama ollama pull llama3`

Default model: `llama3`. For better Indic language support, try `llama3:70b` if your hardware can handle it.

## Configuration Reference

All configuration goes in `config/config.yaml`. See `config/config.example.yaml` for a fully commented template.

Profiles live in `languagebridge/profiles/` as YAML files. Add a new profile file
and set `family.profile` to its name/path to introduce custom output behavior
without changing backend logic.
You can also override by room with `family.room_profiles` (`room_id -> profile`).

### `family`

| Field              | Type       | Default        | Description                                              |
| ------------------ | ---------- | -------------- | -------------------------------------------------------- |
| `name`             | string     | *required*     | Family name, used in logs and LLM prompts                |
| `profile`          | string     | `"default"`    | Translation profile name/path (e.g. `default`, `charje_english_runes`) |
| `room_profiles`    | map        | `{}`           | Per-room profile overrides: `room_id -> profile`         |
| `trigger_mode`     | string     | `"auto"`       | `auto`, `reaction`, or `command`                         |
| `reaction_trigger` | string     | `"🌐"`         | Emoji that triggers translation (reaction mode only)     |
| `command_prefix`   | string     | `"!translate"` | Command prefix (command mode only)                       |
| `rooms`            | list[str]  | `["*"]`        | Room IDs to monitor, or `["*"]` for all joined rooms     |

### `matrix`

| Field             | Type   | Description                                      |
| ----------------- | ------ | ------------------------------------------------ |
| `homeserver_url`  | string | Your Matrix homeserver URL                       |
| `access_token`    | string | Bot account access token                         |
| `user_id`         | string | Bot's full MXID (e.g. `@languagebridge:matrix.org`) |

### Profile fields (`languagebridge/profiles/*.yaml`)

| Field             | Type      | Default | Description                                            |
| ----------------- | --------- | ------- | ------------------------------------------------------ |
| `target_language` | string    | required| Target language code for this profile (e.g. `en`)     |
| `reply_target_label` | string | required| Label shown in replies (`[mr → en]`)                  |
| `bidirectional_with` | string | `null`  | Optional reverse language code for two-way profiles    |
| `dialect`         | string    | `null`  | Optional dialect hint used in translation prompting    |
| `preserve_terms`  | list[str] | `[]`    | Terms that should never be translated                  |
| `prompt_appendix` | string    | `""`    | Profile-specific prompting instructions                |
| `preprocess`      | object    | `null`  | Optional deterministic preprocessing before LLM        |

`preprocess` supports:

- `kind: runes_to_phonetic` — runic input to phonetic text conversion
- `twin_map` / `lone_map` — JSON map paths used by the preprocessor
- `rune_threshold` — fraction of runic chars required to activate preprocessing
- `word_separator` — rune char that should map to spaces (default `᛫`)

### `llm`

| Field        | Type   | Default                          | Description                           |
| ------------ | ------ | -------------------------------- | ------------------------------------- |
| `provider`   | string | *required*                       | `anthropic`, `openai`, `gemini`, `ollama` |
| `api_key`    | string | `null`                           | API key (not needed for ollama)       |
| `model`      | string | provider default                 | Model override                        |
| `ollama_url` | string | `"http://localhost:11434"`       | Ollama server URL                     |

### `ui` (optional)

How translation replies and startup notices look in Matrix clients. There is no real opacity or arbitrary CSS in the spec; **subtle** uses [`data-mx-color`](https://spec.matrix.org/latest/client-server-api/#mroommessage-msgtypes)–style coloring and `<small>` where the client allows it.

| Field               | Type   | Default     | Description                                      |
| ------------------- | ------ | ----------- | ------------------------------------------------ |
| `message_style`     | string | `"subtle"`  | `normal` or `subtle`                             |
| `subtle_text_color` | string | `"#8E9597"` | `#RRGGBB` foreground tint for subtle style       |
| `subtle_use_small`  | bool   | `true`      | Wrap text in `<small>` (ignored if unsupported)  |

Cloud env (with `make config-from-env`): `LB_UI_MESSAGE_STYLE`, `LB_UI_SUBTLE_COLOR`, `LB_UI_SUBTLE_USE_SMALL`.

### Trigger Modes

- **`auto`** (default) — Every non-English message is automatically translated. Best for family chats where most foreign messages need translation.
- **`reaction`** — Translation happens only when someone reacts with the 🌐 emoji. Less noisy; good for rooms with mixed multilingual members.
- **`command`** — Translation happens when someone sends `!translate` (as a reply to the message to translate, or with text inline). Most explicit control.

## Supported Languages

LanguageBridge detects and translates 25 languages:

**Indic languages (first-class support):** Hindi, Marathi, Punjabi, Gujarati, Tamil, Telugu, Kannada, Bengali — including **romanized/transliterated** text (e.g. "kasa aahes" for Marathi, "kya hal hai" for Hindi) and **code-switched** messages mixing Indic languages with English.

**Other languages:** English, Spanish, French, German, Portuguese, Italian, Arabic, Chinese, Japanese, Korean, Russian, Turkish, Dutch, Polish, Vietnamese, Thai, Indonesian.

The LLM handles romanized text that the language detector cannot confidently identify — even when lingua-py marks text as "unknown," the LLM can usually detect and translate it correctly.

## Deployment

### Hetzner VPS (recommended for self-hosting)

A CAX11 ARM instance (2 vCPU, 4 GB RAM, ~€4/month) is more than enough. Install Docker, clone the repo, configure, and run `make docker-up`. Add Ollama on a CAX21 if you want free local translation.

### Railway

Push to a GitHub repo and connect it to Railway. Set `CONFIG_PATH` as an environment variable pointing to your mounted config. Railway's free tier is sufficient for a family chat bot.

### Fly.io

Create a `fly.toml` with a single machine, mount a volume for `/app/data`, and use secrets for the config file. The free tier includes enough compute for this use case.

### Raspberry Pi

Works on a Pi 4 or newer. Install Docker with `curl -fsSL https://get.docker.com | sh`, clone, configure, and run `make docker-up`. Lingua-py compilation takes longer on ARM but works fine. Not recommended for Ollama (too slow for large models), but works well with cloud LLM providers.

## Development Workflow

Use Docker targets for runtime and tests:

- `make run` starts the service in Docker (`docker compose up`, foreground; use `docker compose up -d` for detached).
- `make run-local` runs foreground with `config/config-local.yaml` and `./data`.
- `make test` runs tests in Docker.
- `make config-from-env` writes `config/config.yaml` from `LB_*` variables.
- `make docker-build`, `make docker-up`, `make docker-down`, `make docker-logs`.

## How It Works

### Runtime pipeline

1. LanguageBridge connects to your Matrix homeserver and monitors configured rooms.
2. Incoming messages are filtered (own messages, duplicates, room scope, empty text).
3. The selected room/profile can optionally run deterministic preprocessing first (e.g. Charje runes -> phonetic text).
4. Language detection runs on the preprocessed text (or original text when no preprocess is enabled).
5. Skip heuristics run (target-language high confidence, low-signal short text, etc.), with preprocess-aware behavior.
6. A profile-aware translation cache is checked before any LLM call.
7. On cache miss, the LLM is called with profile prompt context and translation direction.
8. The final translation is sent as a threaded reply: `🌐 [mr → en] How are you, kaka?`
9. Event IDs are marked processed; translation results are cached for future identical inputs.

### Architecture notes

- **Profile-driven behavior**: Profile YAML controls direction, prompting, dialect hints, preserved terms, and optional preprocessing.
- **Preprocess layer**: Deterministic transforms can normalize special scripts before LLM usage (Charje maps in `languagebridge/profiles/charje_maps/`).
- **Cache layer**: Exact translation cache is persisted in SQLite (`translation_cache` table) to avoid repeated token spend.
  - Cache key includes profile, translation direction, prompt hash, and normalized input text.
- **Storage layer**: SQLite stores both processed event IDs and cached translation outputs.

## Contributing

Contributions welcome! This is an early-stage project. Areas where help is especially appreciated:

- Additional LLM provider implementations
- Improved romanized Indic language detection
- Testing with different Matrix homeservers and bridge configurations
- Documentation and setup guides for specific bridge combinations

## License

MIT
