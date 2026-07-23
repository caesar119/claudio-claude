# Claudio 🎤 — asistente de voz para Claude Code

*Read this in English: [README.md](README.md)*

Claudio deja el micrófono escuchando en segundo plano. Cuando decís la palabra
de activación (**"claudio"** por defecto), transcribe la orden que sigue y se
la manda a [Claude Code](https://claude.com/claude-code) — tipeada directo en
tu terminal. Y Claude puede **contestarte hablando** en voz alta.

El reconocimiento de voz corre **100% offline** con modelos chicos de
[Vosk](https://alphacephei.com/vosk/) (~40–50 MB, livianos para CPU; el audio
nunca sale de tu máquina), y la voz de salida con
[Kokoro](https://github.com/thewh1teagle/kokoro-onnx) o
[Piper](https://github.com/OHF-Voice/piper1-gpl) (también offline).
**12 idiomas soportados**: es, en, pt, fr, de, it, ca, nl, ru, hi, zh, ja —
todos escuchan y hablan.

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

¿Querés un asistente por proyecto, cada uno con su nombre y su voz? Mirá
[Un equipo de trabajadores](#un-equipo-de-trabajadores-).

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

## Darle voz a Claude 🔊

`setup.sh` ofrece dos motores TTS offline:

- **kokoro** (default donde está disponible) — [Kokoro-82M](https://github.com/thewh1teagle/kokoro-onnx),
  lejos la voz más natural; un solo modelo de ~340 MB cubre en, es, fr, it,
  pt, hi, ja, zh. Corre más rápido que tiempo real en una CPU normal.
- **piper** — liviano (~60 MB por idioma), voz más plana/robótica; cubre todo
  menos hi/ja. Se usa automáticamente donde Kokoro no tiene voz (de, ca, nl,
  ru) y como fallback si Kokoro falla.

Activala con:

```bash
claudio voz on       # Claude lee cada respuesta en voz alta
claudio voz test     # escuchá la voz sin involucrar a Claude
claudio voz off      # de vuelta al silencio
```

`voz on` registra un [hook Stop](https://docs.anthropic.com/en/docs/claude-code/hooks)
en `~/.claude/settings.json`: cada vez que Claude Code termina una respuesta —
en cualquier proyecto, disparada por voz o tipeada — la lee con Piper.
Reiniciá tu sesión de Claude Code (o corré `/hooks`) después de activarla o
desactivarla para que lo tome.

Detalles que conviene saber:

- Antes de hablar se eliminan bloques de código, tablas y markdown, y el texto
  se corta en `CLAUDIO_VOICE_MAX_CHARS` (500) para que las respuestas largas
  no se vuelvan un monólogo.
- Mientras Claude habla, Claudio **silencia el mic** (archivo flag `speaking`)
  para no despertarse escuchando su propia voz.
- Una respuesta nueva interrumpe a la anterior — gana la última.
- La síntesis es local; no se manda nada a ningún lado.

## Un equipo de trabajadores 👥

Contratá un **trabajador con nombre para cada proyecto** — como empleados a
los que llamás por su nombre:

```bash
claudio hire marcela ~/proyectos/backend ef_dora   # nombre, proyecto, voz
claudio hire bruno ~/proyectos/webapp em_santa
claudio team          # quién trabaja dónde (y quién está presente en tmux)
claudio fire bruno    # sacar un trabajador
```

Y después les hablás directamente:

> **"Marcela, corré los tests"** — se tipea en la terminal de Marcela (la
> abrís con `claudio code marcela`), o corre headless **en su proyecto** si
> está cerrada. **"Claudio, commiteá todo"** — va al proyecto de Claudio.
> El mismo mic, distintos trabajadores, al mismo tiempo.

- Cada trabajador es dueño de un proyecto y de una sesión tmux
  (`claudio-<nombre>`).
- Cada uno **contesta con su propia voz** (elegí cualquier voz Kokoro).
- El daemon recarga el equipo al vuelo — no hay que reiniciar tras
  hire/fire.
- El primer `hire` conserva automáticamente tu palabra de activación
  original como trabajador, así no se rompe nada.
- El equipo vive en `~/.local/share/claudio/team` (una línea
  `nombre  dir  voz` por trabajador). Elegí nombres que el modelo de voz
  reconozca bien — los nombres de pila comunes de tu idioma andan mejor.

### Sin equipo (una sola palabra de activación)

Si nunca contratás a nadie, vale el comportamiento v1: `claudio code
~/algún/proyecto` abre cada proyecto en su propia sesión tmux y las órdenes
de voz van al pane **que estás mirando** (sesión atacada, pane activo); si
ninguno está a la vista, a la primera sesión `claudio-*` que encuentre.

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
| `CLAUDIO_TTS` | `auto` | Motor de voz: `kokoro`, `piper` o `auto` |
| `CLAUDIO_KOKORO_VOICE` | según idioma | Voz Kokoro (es: `ef_dora`/`em_alex`/`em_santa`) |
| `CLAUDIO_VOICE` | según idioma | Voz Piper (ej. `es_MX-claude-high`) |
| `CLAUDIO_VOICE_MAX_CHARS` | `500` | Tope de largo de la respuesta hablada |

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

## Apoyar el proyecto ☕

Si Claudio te ahorra tecleo, podés invitarme un café — hasta 1–5 USD se
agradecen:

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

## Licencia

MIT
