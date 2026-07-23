# Claudio 🎤 — voice assistant for Claude Code

*Leé esto en español: [README.es.md](README.es.md)*

Claudio keeps your microphone listening in the background. When you say the
wake word (**"claudio"** by default), it transcribes the command that follows
and sends it to [Claude Code](https://claude.com/claude-code) — typed straight
into your terminal. And Claude can **speak its replies back** out loud.

Speech recognition runs **100% offline** with [Vosk](https://alphacephei.com/vosk/)
small models (~40–50 MB, CPU-friendly, no audio ever leaves your machine), and
speech output with [Kokoro](https://github.com/thewh1teagle/kokoro-onnx) or
[Piper](https://github.com/OHF-Voice/piper1-gpl) (also offline).
**12 languages supported**: es, en, pt, fr, de, it, ca, nl, ru, hi, zh, ja —
all of them listen and speak.

## Requirements

- Linux with ALSA (`arecord`) — most desktop distros have it out of the box
- Python 3.9+
- [Claude Code CLI](https://claude.com/claude-code) installed and logged in
- Optional but recommended: `tmux` (interactive mode), `notify-send` (desktop
  notifications), `aplay` (beep feedback)

## Install

```bash
git clone https://github.com/caesar119/claudio-claude.git
cd claudio-claude
bash setup.sh
```

The setup detects your system language and suggests it, lets you pick any
supported language and wake word, downloads the matching Vosk model, and
installs a global `claudio` command in `~/.local/bin`. Non-interactive:
`bash setup.sh en jarvis` (language + wake word).

The venv, model and config live in `~/.local/share/claudio/`.

## Usage

```bash
claudio start        # start the voice daemon in the background
claudio code         # open Claude Code inside tmux in the current project
```

Then just say:

> **"Claudio, run the tests"**

Want one assistant per project, each with their own name and voice? See
[A team of workers](#a-team-of-workers-).

- A short *beep* confirms the wake word was heard.
- Say the wake word alone and it beeps and waits up to 10 s for your command.
- `claudio log` follows what it hears; `claudio stop` shuts it down.

## Where do commands go?

Claudio tries two routes, in order:

1. **tmux mode (recommended)** — if Claude Code is running inside tmux
   (`claudio code` sets that up), the command is **typed into that terminal**
   with `tmux send-keys`, as if you wrote it. You see the command and the
   reply live, and Claude can ask for permissions normally.
2. **Headless fallback** — otherwise it runs `claude --continue -p "<command>"`
   in the configured workdir, continuing that directory's latest conversation.
   The reply arrives as a desktop notification and in the log.
   ⚠️ Headless Claude can't ask for interactive permissions; to let it edit
   files unattended: `export CLAUDIO_CLAUDE_ARGS="--permission-mode acceptEdits"`.

## Give Claude a voice 🔊

`setup.sh` offers two offline TTS engines:

- **kokoro** (default where available) — [Kokoro-82M](https://github.com/thewh1teagle/kokoro-onnx),
  by far the most natural voice; one ~340 MB model covers en, es, fr, it, pt,
  hi, ja, zh. Runs faster than real time on a normal CPU.
- **piper** — lightweight (~60 MB per language), flatter/more robotic voice;
  covers everything except hi/ja. Used automatically where Kokoro has no voice
  (de, ca, nl, ru) and as fallback if Kokoro breaks.

Turn it on with:

```bash
claudio voz on       # Claude reads every reply out loud
claudio voz test     # hear the voice without involving Claude
claudio voz off      # back to silence
```

`voz on` registers a [Stop hook](https://docs.anthropic.com/en/docs/claude-code/hooks)
in `~/.claude/settings.json`: whenever Claude Code finishes a reply — in any
project, voice-triggered or typed — the reply is spoken with Piper. Restart
your Claude Code session (or run `/hooks`) after toggling so it takes effect.

Details worth knowing:

- Code blocks, tables and markdown are stripped before speaking, and the text
  is capped at `CLAUDIO_VOICE_MAX_CHARS` (500) so long answers don't monologue.
- While Claude talks, Claudio **mutes the mic** (flag file `speaking`) so it
  doesn't wake itself up hearing its own voice.
- A new reply interrupts the previous one — the latest answer wins.
- Speech is synthesized locally; nothing is sent anywhere.

## A team of workers 👥

Hire a **named worker for each project** — like employees you call by name:

```bash
claudio hire marcela ~/projects/backend ef_dora   # name, project, voice
claudio hire bruno ~/projects/webapp em_santa
claudio team          # who works where (and who's present in tmux)
claudio fire bruno    # remove a worker
```

Then just talk to them:

> **"Marcela, run the tests"** — typed into Marcela's terminal (open it with
> `claudio code marcela`), or run headless **in her project** if it's closed.
> **"Claudio, commit everything"** — goes to Claudio's project. Same mic,
> different workers, at the same time.

- Each worker owns a project directory and a tmux session (`claudio-<name>`).
- Each worker **answers with their own voice** (pick any Kokoro voice).
- The daemon reloads the team on the fly — no restart after hire/fire.
- Your first `hire` automatically keeps the original wake word as a worker,
  so nothing breaks.
- The team lives in `~/.local/share/claudio/team` (one `name  dir  voice`
  line per worker). Pick names the speech model recognizes well — common
  first names of your language work best.

### Without a team (single wake word)

If you never hire anyone, v1 behavior applies: `claudio code ~/some/project`
opens each project in its own tmux session and voice commands go to the pane
**you are looking at** (attached session, active pane); if none is visible,
to the first `claudio-*` session found.

## Configuration

Written by `setup.sh` to `~/.local/share/claudio/config`; environment
variables override it.

| Variable | Default | Purpose |
|---|---|---|
| `CLAUDIO_LANG` | system locale | Recognition model + UI language |
| `CLAUDIO_WAKE` | per-language | Wake word (one word) |
| `CLAUDIO_WORKDIR` | repo dir | Where headless `claude` runs |
| `CLAUDIO_CLAUDE_ARGS` | *(empty)* | Extra flags for `claude` |
| `CLAUDIO_COMMAND_TIMEOUT` | `10` | Seconds to wait after the beep |
| `CLAUDIO_DEVICE` | system default | ALSA capture device (`arecord -l`) |
| `CLAUDIO_MODEL` | `~/.local/share/claudio/model-<lang>` | Vosk model path |
| `CLAUDIO_TMUX_TARGET` | autodetect | tmux pane to type into |
| `CLAUDIO_TTS` | `auto` | Voice engine: `kokoro`, `piper` or `auto` |
| `CLAUDIO_KOKORO_VOICE` | per-language | Kokoro voice (es: `ef_dora`/`em_alex`/`em_santa`) |
| `CLAUDIO_VOICE` | per-language | Piper voice name (e.g. `es_MX-claude-high`) |
| `CLAUDIO_VOICE_MAX_CHARS` | `500` | Cap on spoken reply length |

Tip: if the small model struggles with your wake word, pick a common word of
your language, or download a full-size Vosk model and point `CLAUDIO_MODEL`
at it.

## Autostart on login

`setup.sh` generates a systemd user unit:

```bash
cp ~/.local/share/claudio/claudio.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claudio
```

## Support ☕

If Claudio saves you keystrokes, you can buy me a coffee — even 1–5 USD is
appreciated:

- **BTC**
  ```
  bc1qw9z92xawkqcdu2vztqf0ken3a3ke4ewvrxrnl2
  ```
- **ETH**
  ```
  0xEc2ffc781F49E3e8C75714EBCff05bF76928c8FD
  ```
- **USDT** (TRON / TRC-20)
  ```
  THLAyVrmZtfCAYeoyQVJ4baNJJvK1HkFgi
  ```
- **Monero (XMR)**
  ```
  41z7HCz7EzUNHEy5KFADyXSP9K6phucg1bsd8h5HXgQrfT6mZzJkUJQMqvEtKAx16FBMu5DDxRJfW4jU4icUHmUbHs77wz4
  ```

## License

MIT
