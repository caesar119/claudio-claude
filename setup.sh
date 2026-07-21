#!/usr/bin/env bash
# Claudio setup: venv + Vosk model in your language + global `claudio` command.
# Usage:
#   bash setup.sh                    # interactive (suggests your system language)
#   bash setup.sh en                 # pick a language directly
#   bash setup.sh en jarvis          # language + custom wake word
#   bash setup.sh en jarvis kokoro   # voice engine: kokoro | piper | novoice
set -eu

DATA="$HOME/.local/share/claudio"
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$DATA"

# --- supported languages: Vosk small models (~40-50 MB each) ----------------
declare -A MODELS=(
    [es]=vosk-model-small-es-0.42
    [en]=vosk-model-small-en-us-0.15
    [pt]=vosk-model-small-pt-0.3
    [fr]=vosk-model-small-fr-0.22
    [de]=vosk-model-small-de-0.15
    [it]=vosk-model-small-it-0.22
    [ca]=vosk-model-small-ca-0.4
    [nl]=vosk-model-small-nl-0.22
    [ru]=vosk-model-small-ru-0.22
    [hi]=vosk-model-small-hi-0.22
    [zh]=vosk-model-small-cn-0.22
    [ja]=vosk-model-small-ja-0.22
)
# default wake word per language (any single word the model recognizes works)
declare -A WAKES=(
    [es]=claudio [it]=claudio [pt]=claudio [ca]=claudio
    [en]=claude  [fr]=claude  [de]=claude  [nl]=claude
    [ru]=клод    [hi]=क्लॉड    [zh]=克劳德   [ja]=クロード
)
# TTS so Claude can speak its replies. Two engines:
# - kokoro: most natural, one ~340 MB model for its 8 languages
# - piper:  lightweight (~60 MB per language), flatter voice
declare -A KOKORO_VOICES=(
    [es]=ef_dora [en]=af_heart [pt]=pf_dora  [fr]=ff_siwis
    [it]=if_sara [hi]=hf_alpha [ja]=jf_alpha [zh]=zf_xiaobei
)
declare -A VOICES=(
    [es]=es_MX-claude-high
    [en]=en_US-lessac-medium
    [pt]=pt_BR-faber-medium
    [fr]=fr_FR-siwis-medium
    [de]=de_DE-thorsten-medium
    [it]=it_IT-paola-medium
    [ca]=ca_ES-upc_ona-medium
    [nl]=nl_BE-nathalie-medium
    [ru]=ru_RU-irina-medium
    [zh]=zh_CN-huayan-medium
)
KOKORO_URL=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0

# --- language selection: detect from system locale, allow override ----------
sys_lang="${LANG%%[._]*}"; sys_lang="${sys_lang%%_*}"
[ -n "${MODELS[$sys_lang]+x}" ] || sys_lang=en

lang="${1:-}"
if [ -z "$lang" ]; then
    echo "Available languages: ${!MODELS[*]}"
    if [ -t 0 ]; then
        read -r -p "Language [$sys_lang]: " lang
    fi
    lang="${lang:-$sys_lang}"
fi
if [ -z "${MODELS[$lang]+x}" ]; then
    echo "Unsupported language: '$lang'. Available: ${!MODELS[*]}" >&2
    exit 1
fi

wake="${2:-}"
if [ -z "$wake" ] && [ -t 0 ]; then
    read -r -p "Wake word (one word) [${WAKES[$lang]}]: " wake
fi
wake="${wake:-${WAKES[$lang]}}"

echo "Language: $lang — wake word: \"$wake\""

# --- venv + vosk ------------------------------------------------------------
if [ ! -x "$DATA/venv/bin/python" ]; then
    echo "Creating venv…"
    python3 -m venv "$DATA/venv"
fi
"$DATA/venv/bin/pip" install --quiet --upgrade vosk

# --- model ------------------------------------------------------------------
model_dir="$DATA/model-$lang"
if [ ! -d "$model_dir" ]; then
    if [ "$lang" = es ] && [ -d "$DATA/model" ]; then
        mv "$DATA/model" "$model_dir"   # migrate pre-multilanguage layout
    else
        name="${MODELS[$lang]}"
        echo "Downloading Vosk model $name…"
        curl -L --progress-bar -o "$DATA/model.zip" "https://alphacephei.com/vosk/models/$name.zip"
        python3 -c "import zipfile; zipfile.ZipFile('$DATA/model.zip').extractall('$DATA')"
        mv "$DATA/$name" "$model_dir"
        rm "$DATA/model.zip"
    fi
fi

# --- voice (optional): TTS so Claude can speak its replies ------------------
kokoro_voice="${KOKORO_VOICES[$lang]:-}"
piper_voice="${VOICES[$lang]:-}"
engine="${3:-}"
if [ -z "$engine" ] && { [ -n "$kokoro_voice" ] || [ -n "$piper_voice" ]; }; then
    if [ -t 0 ]; then
        echo "Claude can speak its replies out loud. Voice engines:"
        [ -n "$kokoro_voice" ] && echo "  kokoro  - most natural voice (~340 MB download)"
        [ -n "$piper_voice" ]  && echo "  piper   - lightweight (~60 MB), flatter voice"
        echo "  novoice - skip, text only"
        default_engine=$([ -n "$kokoro_voice" ] && echo kokoro || echo piper)
        read -r -p "Voice engine [$default_engine]: " engine
        engine="${engine:-$default_engine}"
    else
        engine=$([ -n "$kokoro_voice" ] && echo kokoro || echo piper)
    fi
fi
case "$engine" in
    kokoro)
        if [ -z "$kokoro_voice" ]; then
            echo "Kokoro has no '$lang' voice yet; falling back to piper." >&2
            engine=piper
        else
            echo "Installing Kokoro TTS…"
            "$DATA/venv/bin/pip" install --quiet kokoro-onnx
            mkdir -p "$DATA/kokoro"
            for f in kokoro-v1.0.onnx voices-v1.0.bin; do
                if [ ! -f "$DATA/kokoro/$f" ]; then
                    echo "Downloading $f…"
                    curl -L --progress-bar -o "$DATA/kokoro/$f" "$KOKORO_URL/$f"
                fi
            done
        fi
        ;;
esac
case "$engine" in
    piper)
        if [ -z "$piper_voice" ]; then
            echo "(No voice available for '$lang' yet — Claudio will listen but not speak.)"
            engine=""
        else
            echo "Installing Piper TTS…"
            "$DATA/venv/bin/pip" install --quiet piper-tts
            if [ ! -f "$DATA/voices/$piper_voice.onnx" ]; then
                echo "Downloading voice $piper_voice…"
                "$DATA/venv/bin/python" -m piper.download_voices "$piper_voice" --data-dir "$DATA/voices"
            fi
        fi
        ;;
    kokoro) ;;
    *) engine="" ;;
esac

# --- config -----------------------------------------------------------------
cat > "$DATA/config" <<EOF
CLAUDIO_LANG=$lang
CLAUDIO_WAKE=$wake
EOF
if [ "$engine" = kokoro ]; then
    printf 'CLAUDIO_TTS=kokoro\nCLAUDIO_KOKORO_VOICE=%s\n' "$kokoro_voice" >> "$DATA/config"
elif [ "$engine" = piper ]; then
    printf 'CLAUDIO_TTS=piper\nCLAUDIO_VOICE=%s\n' "$piper_voice" >> "$DATA/config"
fi

# --- global `claudio` command -----------------------------------------------
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/claudio" <<EOF
#!/usr/bin/env bash
# Claudio — global command (generated by setup.sh).
#   claudio code [dir]   open Claude Code in tmux in a project (default: cwd);
#                        voice commands get typed there
#   claudio voz on|off|status|test     Claude speaks its replies (Piper TTS)
#   claudio start|stop|status|log|fg   control the voice daemon
set -u
REPO="$DIR"
case "\${1:-}" in
    code)
        d="\$(cd "\${2:-\$PWD}" 2>/dev/null && pwd)" || { echo "Invalid directory: \${2:-}"; exit 1; }
        name="claudio-\$(basename "\$d" | tr -c 'A-Za-z0-9_-' '-' | sed 's/-*\$//')"
        exec tmux new-session -A -s "\$name" -c "\$d" claude
        ;;
    start|stop|status|log|fg|tmux|voz|voice)
        exec bash "\$REPO/claudio.sh" "\$@"
        ;;
    *)
        echo "Usage: claudio {code [dir]|voz on|off|status|test|start|stop|status|log|fg}"
        exit 1
        ;;
esac
EOF
chmod +x "$HOME/.local/bin/claudio" 2>/dev/null || true

# --- systemd user service (optional autostart) ------------------------------
cat > "$DATA/claudio.service" <<EOF
[Unit]
Description=Claudio - voice assistant for Claude Code
After=default.target sound.target

[Service]
ExecStart=$DATA/venv/bin/python $DIR/claudio.py
Environment=CLAUDIO_WORKDIR=$DIR
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF

echo
echo "Done. Start with:  claudio start   (or: bash claudio.sh start)"
[ -n "$engine" ] && echo "Give Claude a voice:  claudio voz on   (try it: claudio voz test)"
echo "Autostart on login (optional):"
echo "  cp $DATA/claudio.service ~/.config/systemd/user/ && systemctl --user enable --now claudio"
