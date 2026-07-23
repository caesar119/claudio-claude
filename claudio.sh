#!/usr/bin/env bash
# Claudio — control del daemon de voz y del equipo de trabajadores.
# Uso: ./claudio.sh {start|stop|status|log|fg|tmux|voz|code|hire|fire|team}
set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="$HOME/.local/share/claudio"
PY="$DATA/venv/bin/python"
PIDFILE="$DATA/claudio.pid"
OUT="$DATA/daemon.out"
TEAM="$DATA/team"

running() {
    [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null
}

cfg() {  # cfg CLAVE -> valor de ~/.local/share/claudio/config
    grep -s "^$1=" "$DATA/config" | head -1 | cut -d= -f2-
}

es() { [ "$(cfg CLAUDIO_LANG)" = es ] || [ -z "$(cfg CLAUDIO_LANG)" ]; }

worker_dir() {  # worker_dir nombre -> directorio del trabajador (o vacío)
    [ -f "$TEAM" ] && awk -F'\t' -v n="$1" '$1==n{print $2; exit}' "$TEAM"
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
        exec tmux new-session -A -s claudio -c "$DIR" claude
        ;;
    code)
        # claudio code [trabajador|dir] — abre Claude Code en tmux.
        # Con el nombre de un trabajador, abre SU sesión en SU proyecto.
        arg="${2:-$PWD}"
        low="$(printf '%s' "$arg" | tr '[:upper:]' '[:lower:]')"
        wdir="$(worker_dir "$low")"
        if [ -n "$wdir" ]; then
            exec tmux new-session -A -s "claudio-$low" -c "$wdir" claude
        fi
        d="$(cd "$arg" 2>/dev/null && pwd)" || {
            if es; then echo "No es un trabajador ni un directorio: $arg"
            else echo "Not a worker nor a directory: $arg"; fi
            exit 1
        }
        name="claudio-$(basename "$d" | tr -c 'A-Za-z0-9_-' '-' | sed 's/-*$//')"
        exec tmux new-session -A -s "$name" -c "$d" claude
        ;;
    hire)
        # claudio hire <nombre> <dir> [voz_kokoro] — contrata un trabajador.
        name="${2:-}"; pdir="${3:-}"; voice="${4:-ef_dora}"
        if [ -z "$name" ] || [ -z "$pdir" ]; then
            echo "Uso: claudio hire <nombre> <dir> [voz]   (voces es: ef_dora, em_alex, em_santa)"
            exit 1
        fi
        case "$name" in
            *[!a-zA-Z0-9_-]*)
                if es; then echo "Nombre inválido (una sola palabra, sin espacios): $name"
                else echo "Invalid name (single word, no spaces): $name"; fi
                exit 1 ;;
        esac
        name="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"
        d="$(cd "$pdir" 2>/dev/null && pwd)" || {
            if es; then echo "Directorio inválido: $pdir"; else echo "Invalid directory: $pdir"; fi
            exit 1
        }
        # primer hire: sembrar el trabajador por defecto para no perder v1
        if [ ! -f "$TEAM" ]; then
            wake="$(cfg CLAUDIO_WAKE)"; gvoice="$(cfg CLAUDIO_KOKORO_VOICE)"
            if [ -n "$wake" ] && [ "$wake" != "$name" ]; then
                printf '%s\t%s\t%s\n' "$wake" "${CLAUDIO_WORKDIR:-$DIR}" "${gvoice:-ef_dora}" > "$TEAM"
            fi
        fi
        { [ -f "$TEAM" ] && awk -F'\t' -v n="$name" '$1!=n' "$TEAM"; true; } > "$TEAM.tmp"
        printf '%s\t%s\t%s\n' "$name" "$d" "$voice" >> "$TEAM.tmp"
        mv "$TEAM.tmp" "$TEAM"
        if es; then echo "🤝 ${name^} entra al equipo — proyecto: $d, voz: $voice"
        else echo "🤝 ${name^} joins the team — project: $d, voice: $voice"; fi
        if es; then echo "   Llamala/o diciendo \"$name\" + tu orden. Su terminal: claudio code $name"
        else echo "   Call by saying \"$name\" + your command. Terminal: claudio code $name"; fi
        ;;
    fire)
        name="$(printf '%s' "${2:-}" | tr '[:upper:]' '[:lower:]')"
        if [ -z "$name" ]; then echo "Uso: claudio fire <nombre>"; exit 1; fi
        if [ ! -f "$TEAM" ] || ! awk -F'\t' -v n="$name" '$1==n{found=1} END{exit !found}' "$TEAM"; then
            if es; then echo "No hay ningún trabajador llamado $name."
            else echo "No worker named $name."; fi
            exit 1
        fi
        awk -F'\t' -v n="$name" '$1!=n' "$TEAM" > "$TEAM.tmp" && mv "$TEAM.tmp" "$TEAM"
        if es; then echo "👋 ${name^} dejó el equipo."
        else echo "👋 ${name^} left the team."; fi
        ;;
    team|equipo)
        if [ ! -f "$TEAM" ] || [ ! -s "$TEAM" ]; then
            if es; then echo "Todavía no hay equipo. Contratá con: claudio hire <nombre> <dir> [voz]"
            else echo "No team yet. Hire with: claudio hire <name> <dir> [voice]"; fi
            exit 0
        fi
        while IFS="$(printf '\t')" read -r n d v; do
            [ -n "$n" ] || continue
            if tmux has-session -t "=claudio-$n" 2>/dev/null; then
                st=$(es && echo "🟢 presente" || echo "🟢 present")
            else
                st=$(es && echo "⚪ ausente " || echo "⚪ away    ")
            fi
            printf '%-12s %s  %-10s %s\n' "$n" "$st" "${v:--}" "$d"
        done < "$TEAM"
        ;;
    voz|voice)
        # Claude habla sus respuestas en voz alta (hook Stop + TTS).
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
        echo "Uso: $0 {start|stop|status|log|fg|tmux|voz|code [trabajador|dir]|hire <nombre> <dir> [voz]|fire <nombre>|team}"
        exit 1
        ;;
esac
