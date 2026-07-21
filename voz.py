#!/usr/bin/env python3
"""Claudio voz — Claude speaks its replies out loud (Piper TTS, 100% offline).

Runs as a Claude Code `Stop` hook: when Claude finishes a reply, the hook
reads it from the transcript, strips code/markdown and speaks it with Piper.
Playback happens in a detached process so Claude Code is never blocked.

Usage:
  voz.py --hook          Claude Code Stop hook (reads hook JSON from stdin)
  voz.py --say [text]    speak arbitrary text (default: a test phrase)
  voz.py --enable        register the Stop hook in ~/.claude/settings.json
  voz.py --disable       remove the hook
  voz.py --status        show whether the hook is active and which voice is set

Configuration (~/.local/share/claudio/config or environment):
  CLAUDIO_VOICE             Piper voice name, e.g. es_MX-claude-high
  CLAUDIO_VOICE_MAX_CHARS   cap on spoken text length (default: 500)

While speaking, the flag file ~/.local/share/claudio/speaking exists;
claudio.py mutes the microphone so Claudio doesn't hear itself.
"""
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

DATA_DIR = Path.home() / ".local/share/claudio"
CONFIG_FILE = DATA_DIR / "config"
VOICES_DIR = DATA_DIR / "voices"
SPEAK_FLAG = DATA_DIR / "speaking"
SETTINGS = Path.home() / ".claude/settings.json"


def _load_config():
    """KEY=VALUE lines; environment variables take precedence."""
    if not CONFIG_FILE.exists():
        return
    for line in CONFIG_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        os.environ.setdefault(key.strip(), val.strip())


_load_config()

LANG = os.environ.get("CLAUDIO_LANG", "es").lower()
VOICE = os.environ.get("CLAUDIO_VOICE", "")
MAX_CHARS = int(os.environ.get("CLAUDIO_VOICE_MAX_CHARS", "500"))

MESSAGES = {
    "en": {
        "test": "Hi, I'm Claude. Now I can talk to you.",
        "on": "Voice enabled. Restart your Claude Code session (or run /hooks) to pick it up.",
        "off": "Voice disabled.",
        "status_on": "Voice: ON — {voice}",
        "status_off": "Voice: OFF — {voice}",
        "no_voice": "No voice installed. Run setup.sh and accept the voice install.",
    },
    "es": {
        "test": "Hola, soy Claude. Ahora puedo hablarte.",
        "on": "Voz activada. Reiniciá tu sesión de Claude Code (o corré /hooks) para que la tome.",
        "off": "Voz desactivada.",
        "status_on": "Voz: ACTIVADA — {voice}",
        "status_off": "Voz: DESACTIVADA — {voice}",
        "no_voice": "No hay ninguna voz instalada. Corré setup.sh y aceptá instalar la voz.",
    },
}


def t(key, **kw):
    msgs = MESSAGES.get(LANG, MESSAGES["en"])
    return msgs.get(key, MESSAGES["en"][key]).format(**kw)


def clean(text):
    """Markdown → plain speakable prose."""
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*\|.*\|\s*$", " ", text, flags=re.M)  # table rows
    text = re.sub(r"[*_~#>|]", "", text)
    text = re.sub(r"[-=]{3,}", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_CHARS]


def last_reply(transcript_path):
    """Last assistant text message in a Claude Code transcript (JSONL)."""
    text = None
    try:
        with open(transcript_path) as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                content = obj.get("message", {}).get("content", [])
                parts = [
                    c.get("text", "")
                    for c in content
                    if isinstance(c, dict) and c.get("type") == "text"
                ]
                if any(p.strip() for p in parts):
                    text = "\n".join(parts)
    except OSError:
        return None
    return text


def voice_onnx():
    return VOICES_DIR / f"{VOICE}.onnx" if VOICE else None


def speak_detached(text):
    """Re-launch as an independent session so the caller (hook/CLI) returns
    right away and, being a process-group leader, can be silenced safely."""
    subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), "--speak", text],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def speak(text):
    onnx = voice_onnx()
    if not onnx or not onnx.exists():
        return
    rate = 22050
    try:
        rate = json.loads(Path(f"{onnx}.json").read_text())["audio"]["sample_rate"]
    except (OSError, ValueError, KeyError):
        pass
    # latest reply wins: silence whatever is still being spoken
    try:
        os.killpg(int(SPEAK_FLAG.read_text()), signal.SIGTERM)
    except (OSError, ValueError):
        pass
    SPEAK_FLAG.write_text(str(os.getpid()))
    try:
        piper = subprocess.Popen(
            [sys.executable, "-m", "piper", "-m", VOICE,
             "--data-dir", str(VOICES_DIR), "--output-raw", "--", text],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["aplay", "-q", "-r", str(rate), "-f", "S16_LE", "-t", "raw", "-c", "1"],
            stdin=piper.stdout,
            stderr=subprocess.DEVNULL,
        )
        piper.wait()
    finally:
        time.sleep(0.4)  # let the room echo die out before unmuting the mic
        try:
            if SPEAK_FLAG.read_text() == str(os.getpid()):
                SPEAK_FLAG.unlink()
        except OSError:
            pass


# --- Stop-hook registration in ~/.claude/settings.json -----------------------

def _hook_entry():
    return {
        "type": "command",
        "command": f'"{sys.executable}" "{os.path.abspath(__file__)}" --hook',
    }


def _read_settings():
    try:
        return json.loads(SETTINGS.read_text() or "{}")
    except (OSError, ValueError):
        return {}


def _is_ours(hook):
    return "voz.py" in hook.get("command", "")


def hook_enabled():
    for group in _read_settings().get("hooks", {}).get("Stop", []):
        if any(_is_ours(h) for h in group.get("hooks", [])):
            return True
    return False


def enable():
    if not (voice_onnx() and voice_onnx().exists()):
        print(t("no_voice"))
        sys.exit(1)
    data = _read_settings()
    groups = data.setdefault("hooks", {}).setdefault("Stop", [])
    if not hook_enabled():
        groups.append({"hooks": [_hook_entry()]})
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(t("on"))


def disable():
    data = _read_settings()
    stop = data.get("hooks", {}).get("Stop", [])
    for group in stop:
        group["hooks"] = [h for h in group.get("hooks", []) if not _is_ours(h)]
    data.get("hooks", {})["Stop"] = [g for g in stop if g.get("hooks")]
    if not data.get("hooks", {}).get("Stop"):
        data.get("hooks", {}).pop("Stop", None)
    if SETTINGS.exists():
        SETTINGS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(t("off"))


def status():
    voice = VOICE or "—"
    print(t("status_on" if hook_enabled() else "status_off", voice=voice))


def main():
    args = sys.argv[1:]
    mode = args[0] if args else ""

    if mode == "--hook":
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            sys.exit(0)
        text = clean(last_reply(payload.get("transcript_path", "")) or "")
        if text:
            speak_detached(text)
        sys.exit(0)

    if mode == "--say":
        text = clean(" ".join(args[1:])) or t("test")
        speak_detached(text)
        sys.exit(0)

    if mode == "--speak":  # internal: the detached player
        speak(" ".join(args[1:]))
        sys.exit(0)

    if mode == "--enable":
        enable()
    elif mode == "--disable":
        disable()
    elif mode == "--status":
        status()
    else:
        print(__doc__.strip())
        sys.exit(1)


if __name__ == "__main__":
    main()
