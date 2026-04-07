# LanguageBridge

A standalone Matrix bot that automatically detects and translates foreign-language messages in group chats, posting translations as threaded replies. Designed for multilingual family chats across WhatsApp, Telegram, Signal, and iMessage via existing Matrix bridges.

**First-class support for romanized Marathi, Hindi, and code-switched Indic/English text** — the use case that existing translation bots handle poorly or not at all.

## Quickstart

```bash
# 1. Clone
git clone https://github.com/youruser/languagebridge.git
cd languagebridge

# 2. Copy the example config
cp config/config.example.yaml config/config.yaml

# 3. Edit config/config.yaml — fill in your Matrix credentials and LLM API key
#    (see sections below for how to get these)

# 4. Start with Docker
make docker-up
```

That's it. The bot joins your rooms and starts translating.

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

### `family`

| Field              | Type       | Default        | Description                                              |
| ------------------ | ---------- | -------------- | -------------------------------------------------------- |
| `name`             | string     | *required*     | Family name, used in logs and LLM prompts                |
| `target_language`  | string     | `"en"`         | ISO 639-1 code of the language to translate INTO         |
| `dialect`          | string     | `null`         | Regional dialect hint (e.g. `"Pune Marathi"`)            |
| `preserve_terms`   | list[str]  | `[]`           | Words to never translate (e.g. `kaka`, `aai`, `baba`)    |
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

### `llm`

| Field        | Type   | Default                          | Description                           |
| ------------ | ------ | -------------------------------- | ------------------------------------- |
| `provider`   | string | *required*                       | `anthropic`, `openai`, `gemini`, `ollama` |
| `api_key`    | string | `null`                           | API key (not needed for ollama)       |
| `model`      | string | provider default                 | Model override                        |
| `ollama_url` | string | `"http://localhost:11434"`       | Ollama server URL                     |

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

## Local Development (Poetry)

```bash
# Install dependencies and create project virtualenv
make install

# Run the bot locally
make run
```

Useful commands:
- `make shell` to open a Poetry shell
- `make lock` to refresh `poetry.lock`
- `make docker-build`, `make docker-up`, `make docker-down`, `make docker-logs`

## How It Works

1. LanguageBridge connects to your Matrix homeserver and monitors configured rooms
2. When a new text message arrives, lingua-py detects its language
3. If the message isn't in the target language, it's sent to your configured LLM with a carefully crafted prompt that:
   - Handles romanized Indic text and code-switching
   - Preserves family terms (kaka, aai, baba, etc.)
   - Maintains casual tone
   - Skips messages that don't need translation (already in target language, emojis, "ok", etc.)
4. The translation is posted as a threaded reply: `🌐 [mr → en] How are you, kaka?`

## Contributing

Contributions welcome! This is an early-stage project. Areas where help is especially appreciated:

- Additional LLM provider implementations
- Improved romanized Indic language detection
- Testing with different Matrix homeservers and bridge configurations
- Documentation and setup guides for specific bridge combinations

## License

MIT
