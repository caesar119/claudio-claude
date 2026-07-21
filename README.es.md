# Claudio 🎤 — asistente de voz para Claude Code

*Read this in English: [README.md](README.md)*

Claudio deja el micrófono escuchando en segundo plano. Cuando decís la palabra
de activación (**"claudio"** por defecto), transcribe la orden que sigue y se
la manda a [Claude Code](https://claude.com/claude-code) — tipeada directo en
tu terminal.

El reconocimiento de voz corre **100% offline** con modelos chicos de
[Vosk](https://alphacephei.com/vosk/) (~40–50 MB, livianos para CPU; el audio
nunca sale de tu máquina). **12 idiomas soportados**: es, en, pt, fr, de, it,
ca, nl, ru, hi, zh, ja.

## Requisitos

- Linux con ALSA (`arecord`) — viene de fábrica en casi todas las distros
- Python 3.9+
- [Claude Code CLI](https://claude.com/claude-code) instalado y logueado
- Opcional pero recomendado: `tmux` (modo interactivo), `notify-send`
  (notificaciones de escritorio), `aplay` (beep de confirmación)

## Instalación

```bash
git clone https://github.com/caesar119/claudio-claude.git
cd claudio-claude
bash setup.sh
```

El setup detecta el idioma de tu sistema y lo sugiere, te deja elegir
cualquier idioma soportado y la palabra de activación, baja el modelo Vosk
correspondiente e instala el comando global `claudio` en `~/.local/bin`.
Sin interacción: `bash setup.sh es claudio` (idioma + palabra).

El venv, el modelo y la config viven en `~/.local/share/claudio/`.

## Uso

```bash
claudio start        # arranca el daemon de voz en segundo plano
claudio code         # abre Claude Code adentro de tmux en el proyecto actual
```

Y después decís:

> **"Claudio, corré los tests"**

- Un *beep* corto confirma que escuchó la palabra de activación.
- Si decís la palabra sola, hace beep y espera tu orden hasta 10 segundos.
- `claudio log` muestra lo que escucha; `claudio stop` lo apaga.

## ¿A dónde van las órdenes?

Claudio prueba dos vías, en orden:

1. **Modo tmux (recomendado)** — si Claude Code está corriendo adentro de tmux
   (`claudio code` lo deja así), la orden se **tipea en esa terminal** con
   `tmux send-keys`, como si la escribieras vos. Ves la orden y la respuesta
   en vivo, y Claude puede pedirte permisos normalmente.
2. **Fallback headless** — si no, ejecuta `claude --continue -p "<orden>"` en
   el directorio configurado, continuando la última conversación de ese
   directorio. La respuesta llega por notificación de escritorio y al log.
   ⚠️ En headless Claude no puede pedir permisos interactivos; para dejarlo
   editar sin preguntar: `export CLAUDIO_CLAUDE_ARGS="--permission-mode acceptEdits"`.

### Varios proyectos

`claudio code ~/algún/proyecto` abre cada proyecto en su propia sesión tmux
(`claudio-<nombre>`). Con varios abiertos a la vez, las órdenes de voz van al
pane **que estás mirando** (sesión atacada, pane activo); si ninguno está a la
vista, a la primera sesión `claudio-*` que encuentre.

## Configuración

`setup.sh` la escribe en `~/.local/share/claudio/config`; las variables de
entorno tienen prioridad.

| Variable | Default | Qué hace |
|---|---|---|
| `CLAUDIO_LANG` | idioma del sistema | Modelo de reconocimiento + idioma de mensajes |
| `CLAUDIO_WAKE` | según idioma | Palabra de activación (una sola palabra) |
| `CLAUDIO_WORKDIR` | dir del repo | Dónde corre `claude` headless |
| `CLAUDIO_CLAUDE_ARGS` | *(vacío)* | Flags extra para `claude` |
| `CLAUDIO_COMMAND_TIMEOUT` | `10` | Segundos de espera tras el beep |
| `CLAUDIO_DEVICE` | default del sistema | Dispositivo ALSA (`arecord -l`) |
| `CLAUDIO_MODEL` | `~/.local/share/claudio/model-<lang>` | Ruta al modelo Vosk |
| `CLAUDIO_TMUX_TARGET` | autodetecta | Pane de tmux donde tipear |

Tip: si el modelo chico no engancha bien tu palabra de activación, elegí una
palabra común de tu idioma, o bajá un modelo Vosk grande y apuntá
`CLAUDIO_MODEL` ahí.

## Arranque automático al iniciar sesión

`setup.sh` genera una unidad systemd de usuario:

```bash
cp ~/.local/share/claudio/claudio.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claudio
```

## Licencia

MIT
