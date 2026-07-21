#!/usr/bin/env bash
# Claudio — control del daemon de voz.
# Uso: ./claudio.sh {start|stop|status|log|fg|tmux|voz}
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="$HOME/.local/share/claudio"
PY="$DATA/venv/bin/python"
PIDFILE="$DATA/claudio.pid"
OUT="$DATA/daemon.out"

running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

case "${1:-}" in
    start)
        if running; then
            echo "Claudio ya está corriendo (pid $(cat "$PIDFILE"))."
            exit 0
        fi
        CLAUDIO_WORKDIR="${CLAUDIO_WORKDIR:-$DIR}" nohup "$PY" "$DIR/claudio.py" >>"$OUT" 2>&1 &
        echo $! > "$PIDFILE"
        echo "Claudio arrancó (pid $!). Log: $DATA/claudio.log"
        ;;
    stop)
        if running; then
            kill "$(cat "$PIDFILE")" && rm -f "$PIDFILE"
            echo "Claudio detenido."
        else
            echo "Claudio no está corriendo."
            rm -f "$PIDFILE"
        fi
        ;;
    status)
        if running; then
            echo "Corriendo (pid $(cat "$PIDFILE"))."
        else
            echo "Detenido."
        fi
        ;;
    log)
        tail -n 50 -f "$DATA/claudio.log"
        ;;
    fg)
        CLAUDIO_WORKDIR="${CLAUDIO_WORKDIR:-$DIR}" exec "$PY" "$DIR/claudio.py"
        ;;
    tmux)
        # Abre (o reataca a) una sesión tmux "claudio" con Claude Code adentro.
        # El daemon detecta este pane y tipea las órdenes de voz acá.
        exec tmux new-session -A -s claudio -c "$DIR" claude
        ;;
    voz|voice)
        # Claude habla sus respuestas en voz alta (hook Stop + Piper TTS).
        sub="${2:-status}"
        case "$sub" in
            on)     exec "$PY" "$DIR/voz.py" --enable ;;
            off)    exec "$PY" "$DIR/voz.py" --disable ;;
            status) exec "$PY" "$DIR/voz.py" --status ;;
            test)   shift 2; exec "$PY" "$DIR/voz.py" --say "$@" ;;
            *)      echo "Uso: $0 voz {on|off|status|test [texto]}"; exit 1 ;;
        esac
        ;;
    *)
        echo "Uso: $0 {start|stop|status|log|fg|tmux|voz}"
        exit 1
        ;;
esac
