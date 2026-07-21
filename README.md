# Claudio 🎤 — voice assistant for Claude Code

*Leé esto en español: [README.es.md](README.es.md)*

Claudio keeps your microphone listening in the background. When you say the
wake word (**"claudio"** by default), it transcribes the command that follows
and sends it to [Claude Code](https://claude.com/claude-code) — typed straight
into your terminal.

Speech recognition runs **100% offline** with [Vosk](https://alphacephei.com/vosk/)
small models (~40–50 MB, CPU-friendly, no audio ever leaves your machine).
**12 languages supported**: es, en, pt, fr, de, it, ca, nl, ru, hi, zh, ja.

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

### Multiple projects

`claudio code ~/some/project` opens each project in its own tmux session
(`claudio-<name>`). With several open at once, voice commands go to the pane
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

## License

MIT
