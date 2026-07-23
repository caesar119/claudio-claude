#!/usr/bin/env python3
"""Claudio — voice assistant for Claude Code / asistente de voz para Claude Code.

Keeps the microphone listening in the background. When it hears the wake
word ("claudio" by default) it transcribes the command that follows and
sends it to Claude Code — typed into a tmux pane running `claude`, or via
`claude -p` headless as fallback. Speech recognition is 100% offline (Vosk).

Configuration is read from ~/.local/share/claudio/config (written by
setup.sh) and can be overridden with environment variables:

  CLAUDIO_LANG             UI/model language code, e.g. "es", "en" (default: es)
  CLAUDIO_WAKE             wake word (default: "claudio")
  CLAUDIO_WORKDIR          directory where headless `claude` runs (default: cwd)
  CLAUDIO_CLAUDE_BIN       path to the claude binary
  CLAUDIO_CLAUDE_ARGS      extra flags, e.g. "--permission-mode acceptEdits"
  CLAUDIO_COMMAND_TIMEOUT  seconds to wait for a command after the beep (default: 10)
  CLAUDIO_MODEL            path to the Vosk model (default: ~/.local/share/claudio/model-<lang>)
  CLAUDIO_DEVICE           ALSA capture device for arecord, e.g. "hw:1,0"
  CLAUDIO_TMUX_TARGET      tmux pane to type commands into (default: autodetect)
"""
import json
import math
import os
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path

DATA_DIR = Path.home() / ".local/share/claudio"
CONFIG_FILE = DATA_DIR / "config"


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
WAKE = os.environ.get("CLAUDIO_WAKE", "claudio").lower()
WORKDIR = os.environ.get("CLAUDIO_WORKDIR", os.getcwd())
CLAUDE_BIN = os.environ.get(
    "CLAUDIO_CLAUDE_BIN",
    shutil.which("claude") or str(Path.home() / ".local/bin/claude"),
)
EXTRA_ARGS = shlex.split(os.environ.get("CLAUDIO_CLAUDE_ARGS", ""))
COMMAND_TIMEOUT = float(os.environ.get("CLAUDIO_COMMAND_TIMEOUT", "10"))
DEVICE = os.environ.get("CLAUDIO_DEVICE", "")

MODEL_DIR = Path(os.environ.get("CLAUDIO_MODEL", DATA_DIR / f"model-{LANG}"))
if not MODEL_DIR.exists() and (DATA_DIR / "model").exists():
    MODEL_DIR = DATA_DIR / "model"  # layout de versiones viejas

RATE = 16000
CHUNK = 4000  # bytes of S16LE mono audio -> 0.125 s

LOG_FILE = DATA_DIR / "claudio.log"
BEEP_WAV = DATA_DIR / "beep.wav"
SPEAK_FLAG = DATA_DIR / "speaking"  # written by voz.py while Claude talks
TEAM_FILE = DATA_DIR / "team"      # one worker per line: name<TAB>dir<TAB>voice

MESSAGES = {
    "en": {
        "loading": "Loading model ({model})…",
        "listening_log": 'Listening. Say "{wake}" followed by your command. Workdir: {dir}',
        "listening_notify": 'Listening. Say "{wake}" and your command.',
        "order": "Command: {text}",
        "sent_tmux": "Typed into your terminal: {text}",
        "prompt": "Listening…",
        "timeout": "Didn't hear a command; back to waiting.",
        "reply": "Reply: {text}",
        "shutdown": "Shutting down.",
        "no_model": "Vosk model not found at {model}. Run setup.sh first.",
        "no_reply": "(no reply)",
        "claude_error": "(claude error: {err})",
        "claude_timeout": "(claude took more than 10 minutes, command aborted)",
        "arecord_lost": "arecord died; restarting capture in 2 s…",
    },
    "es": {
        "loading": "Cargando modelo ({model})…",
        "listening_log": 'Escuchando. Decí "{wake}" seguido de tu orden. Workdir: {dir}',
        "listening_notify": 'Escuchando. Decí "{wake}" y tu orden.',
        "order": "Orden: {text}",
        "sent_tmux": "Enviado a tu terminal: {text}",
        "prompt": "Te escucho…",
        "timeout": "No escuché ninguna orden; vuelvo a esperar.",
        "reply": "Respuesta: {text}",
        "shutdown": "Apagando.",
        "no_model": "No encuentro el modelo Vosk en {model}. Corré setup.sh primero.",
        "no_reply": "(sin respuesta)",
        "claude_error": "(error de claude: {err})",
        "claude_timeout": "(claude tardó más de 10 minutos, orden abortada)",
        "arecord_lost": "arecord se cortó; reinicio la captura en 2 s…",
    },
}


def t(key, **kw):
    msgs = MESSAGES.get(LANG, MESSAGES["en"])
    return msgs.get(key, MESSAGES["en"][key]).format(**kw)


def log(msg):
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except OSError:
        pass


def notify(title, body):
    if shutil.which("notify-send"):
        subprocess.Popen(
            ["notify-send", "-a", "Claudio", title, body],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def make_beep():
    """880 Hz, 0.15 s."""
    if BEEP_WAV.exists():
        return
    frames = int(RATE * 0.15)
    with wave.open(str(BEEP_WAV), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        for i in range(frames):
            fade = min(1.0, (frames - i) / (frames * 0.3))
            val = int(12000 * fade * math.sin(2 * math.pi * 880 * i / RATE))
            w.writeframes(struct.pack("<h", val))


def beep():
    if shutil.which("aplay"):
        subprocess.Popen(
            ["aplay", "-q", str(BEEP_WAV)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def normalize(text):
    """lowercase, no diacritics — accent-insensitive wake word matching"""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfd if not unicodedata.combining(c))


def load_team():
    """Workers hired with `claudio hire`. Without a team file, a single
    legacy worker keeps the v1 behavior (CLAUDIO_WAKE + visible-pane routing)."""
    workers = []
    try:
        for line in TEAM_FILE.read_text().splitlines():
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2 and parts[0].strip():
                workers.append({
                    "name": parts[0].strip(),
                    "dir": parts[1].strip(),
                    "voice": parts[2].strip() if len(parts) > 2 else "",
                })
    except OSError:
        pass
    if not workers:
        workers = [{"name": WAKE, "dir": WORKDIR, "voice": "", "legacy": True}]
    return workers


def match_worker(text, workers):
    """If the text contains a worker's name, return (worker, what follows)."""
    words = text.split()
    norm = [normalize(w) for w in words]
    for worker in workers:
        wake = normalize(worker["name"])
        if wake in norm:
            idx = norm.index(wake)
            return worker, " ".join(words[idx + 1:])
    return None, None


def start_arecord():
    cmd = ["arecord", "-f", "S16_LE", "-r", str(RATE), "-c", "1", "-t", "raw", "-q"]
    if DEVICE:
        cmd += ["-D", DEVICE]
    return subprocess.Popen(cmd, stdout=subprocess.PIPE)


def find_tmux_target():
    """Pick the tmux pane to type into, or None (→ headless mode).

    Priority: explicit CLAUDIO_TMUX_TARGET > the visible pane you're looking
    at > sessions named claudio* > any pane whose foreground process is claude.
    """
    explicit = os.environ.get("CLAUDIO_TMUX_TARGET")
    if explicit:
        return explicit
    if not shutil.which("tmux"):
        return None

    def tmux(*args):
        try:
            r = subprocess.run(["tmux", *args], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return r.stdout if r.returncode == 0 else None

    out = tmux(
        "list-panes", "-a", "-F",
        "#{pane_id}\t#{session_attached}\t#{window_active}\t#{pane_active}"
        "\t#{session_name}\t#{pane_current_command}",
    )
    best, best_score = None, -1
    for line in (out or "").splitlines():
        parts = line.split("\t")
        if len(parts) != 6:
            continue
        pane_id, attached, win_act, pane_act, session, cmd = parts
        in_claudio_session = session.startswith("claudio")
        # pane_current_command may not be "claude" while claude runs a
        # subprocess; that's why claudio* sessions always qualify
        if not in_claudio_session and not cmd.strip().startswith("claude"):
            continue
        visible = attached != "0" and win_act == "1" and pane_act == "1"
        score = (2 if visible else 0) + (1 if in_claudio_session else 0)
        if score > best_score:
            best, best_score = pane_id, score
    return best


def find_worker_pane(name):
    """Active pane of the worker's own tmux session (claudio-<name>), or None."""
    if not shutil.which("tmux"):
        return None
    try:
        r = subprocess.run(
            ["tmux", "list-panes", "-s", "-t", f"=claudio-{name}", "-F",
             "#{pane_id}\t#{window_active}\t#{pane_active}"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[1] == "1" and parts[2] == "1":
            return parts[0]
    return None


def send_tmux(target, text):
    """Type the command into the tmux pane, as if you wrote it yourself."""
    r = subprocess.run(
        ["tmux", "send-keys", "-t", target, "-l", "--", text],
        capture_output=True, timeout=5,
    )
    if r.returncode != 0:
        return False
    time.sleep(0.3)  # let the TUI register the text before Enter
    r = subprocess.run(
        ["tmux", "send-keys", "-t", target, "Enter"],
        capture_output=True, timeout=5,
    )
    return r.returncode == 0


def run_claude(text, workdir):
    """Headless mode: try to continue the latest conversation in workdir;
    if there is none, start a new one."""
    base = [CLAUDE_BIN, *EXTRA_ARGS, "-p", text]
    for args in ([CLAUDE_BIN, "--continue", *EXTRA_ARGS, "-p", text], base):
        try:
            r = subprocess.run(
                args, cwd=workdir, capture_output=True, text=True, timeout=600
            )
        except subprocess.TimeoutExpired:
            return t("claude_timeout")
        if r.returncode == 0:
            return r.stdout.strip() or t("no_reply")
        err = (r.stderr or r.stdout).strip()
        if "--continue" not in args:
            return t("claude_error", err=err[:200])
    return t("claude_error", err="?")


def dispatch(worker, text, state):
    title = worker["name"].capitalize()
    log(f"[{worker['name']}] " + t("order", text=text))
    # 1) claude running interactively in tmux → type the command there
    if worker.get("legacy"):
        target = find_tmux_target()
    else:
        target = find_worker_pane(worker["name"])
    if target:
        if send_tmux(target, text):
            log(f"tmux {target} ← {text}")
            notify(f"{title} ▶️", t("sent_tmux", text=text))
            state["rec"].Reset()
            return
        log(f"tmux send failed ({target}); falling back to headless.")
    # 2) headless claude in the worker's own project
    notify(f"{title} 🎤", t("order", text=text))
    # pause capture while claude works, so stale audio doesn't pile up
    state["arecord"].terminate()
    reply = run_claude(text, worker["dir"])
    log(t("reply", text=reply[:500]))
    notify(f"{title} ✅", reply[:300])
    state["arecord"] = start_arecord()
    state["rec"].Reset()


def main():
    from vosk import Model, KaldiRecognizer, SetLogLevel

    SetLogLevel(-1)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    make_beep()

    if not MODEL_DIR.exists():
        log(t("no_model", model=MODEL_DIR))
        sys.exit(1)

    log(t("loading", model=MODEL_DIR))
    model = Model(str(MODEL_DIR))
    rec = KaldiRecognizer(model, RATE)
    team = load_team()
    state = {"arecord": start_arecord(), "rec": rec, "team": team, "team_mtime": None}
    names = ", ".join(w["name"] for w in team)
    log(t("listening_log", wake=names, dir=WORKDIR))
    notify("Claudio 🎤", t("listening_notify", wake=names))

    def stop(signum, frame):
        log(t("shutdown"))
        state["arecord"].terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    mode = "wake"      # "wake": waiting for a name; "cmd": waiting for the command
    pending = None     # worker that was called and is waiting for its command
    deadline = 0.0
    beeped = False     # already gave feedback for this utterance

    while True:
        # hot reload: `claudio hire/fire` edits the team file while we run
        try:
            mtime = TEAM_FILE.stat().st_mtime
        except OSError:
            mtime = None
        if mtime != state["team_mtime"]:
            state["team_mtime"] = mtime
            state["team"] = load_team()
            log("team: " + ", ".join(w["name"] for w in state["team"]))

        data = state["arecord"].stdout.read(CHUNK)
        if not data:
            log(t("arecord_lost"))
            time.sleep(2)
            state["arecord"] = start_arecord()
            continue

        try:
            # Claude is speaking (voz.py): mute so it doesn't hear itself.
            # A stale flag (crashed speaker) is discarded after 3 minutes.
            if time.time() - SPEAK_FLAG.stat().st_mtime < 180:
                rec.Reset()
                beeped = False
                continue
            SPEAK_FLAG.unlink(missing_ok=True)
        except OSError:
            pass  # no flag — nobody is speaking

        if rec.AcceptWaveform(data):
            text = json.loads(rec.Result()).get("text", "").strip()
            if mode == "wake":
                worker, cmd = match_worker(text, state["team"]) if text else (None, None)
                if worker is not None:
                    if cmd.strip():
                        dispatch(worker, cmd, state)
                    else:
                        beep()
                        notify(f"{worker['name'].capitalize()} 🎤", t("prompt"))
                        mode = "cmd"
                        pending = worker
                        deadline = time.time() + COMMAND_TIMEOUT
            else:
                if text:
                    dispatch(pending, text, state)
                    mode = "wake"
            beeped = False
        else:
            partial = json.loads(rec.PartialResult()).get("partial", "")
            if mode == "wake" and not beeped:
                norm_partial = normalize(partial)
                if any(normalize(w["name"]) in norm_partial for w in state["team"]):
                    beep()  # instant feedback on name detection
                    beeped = True

        if mode == "cmd" and time.time() > deadline:
            mode = "wake"
            notify("Claudio 💤", t("timeout"))


if __name__ == "__main__":
    main()
