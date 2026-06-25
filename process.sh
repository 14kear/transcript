#!/bin/bash
# После вебинара: транскрибирует все куски и делает саммари.
# Использование:  ./process.sh                         (берёт самую свежую сессию)
#                 ./process.sh webinar_20260625_1600  (конкретная папка в out/)
#                 ./process.sh /path/to/audio.m4a      (готовый аудиофайл)
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="$BASE/models/ggml-large-v3-turbo.bin"
LANG_CODE="${WHISPER_LANG:-ru}"   # язык вебинара; переопредели: WHISPER_LANG=en ./process.sh
SUMMARY_PROVIDER="${SUMMARY_PROVIDER:-none}" # none | auto | claude | codex
INPUT="${1:-}"

case "$SUMMARY_PROVIDER" in
  none|auto|claude|codex) ;;
  *) echo "❌ SUMMARY_PROVIDER должен быть: none, auto, claude или codex"; exit 1 ;;
esac

make_session_name() {
  local source="$1"
  local name slug
  name="$(basename "$source")"
  name="${name%.*}"
  slug="$(printf '%s' "$name" | tr '[:space:]' '_' | tr -cd '[:alnum:]_.-')"
  [ -n "$slug" ] || slug="audio"
  printf 'audio_%s_%s' "$slug" "$(date +%Y%m%d_%H%M)"
}

# Выбор сессии или импорт готового аудиофайла
if [ -n "$INPUT" ] && [ -f "$INPUT" ]; then
  command -v ffmpeg >/dev/null || { echo "❌ ffmpeg не найден (brew install ffmpeg)"; exit 1; }

  SESSION="${SESSION:-$(make_session_name "$INPUT")}"
  SESSDIR="$BASE/out/$SESSION"
  if [ -e "$SESSDIR" ]; then
    echo "❌ Папка сессии уже существует: $SESSDIR"
    echo "   Выбери другое имя: SESSION=my_session ./process.sh \"$INPUT\""
    exit 1
  fi

  mkdir -p "$SESSDIR"
  echo "📥 Импортирую аудиофайл: $INPUT"
  echo "   Сессия: $SESSDIR"
  echo "   Формат: 16 кГц mono WAV, куски по 30 мин"
  ffmpeg -hide_banner -loglevel warning \
    -i "$INPUT" -vn \
    -ac 1 -ar 16000 \
    -f segment -segment_time 1800 -reset_timestamps 1 \
    "$SESSDIR/chunk_%03d.wav"
elif [ -n "$INPUT" ]; then
  SESSDIR=$([ -d "$INPUT" ] && echo "$INPUT" || echo "$BASE/out/$INPUT")
else
  SESSDIR=$(ls -dt "$BASE"/out/*/ 2>/dev/null | head -1)
fi
[ -d "${SESSDIR:-}" ] || { echo "❌ Не найдена папка сессии или аудиофайл. Укажи: ./process.sh <имя-сессии|путь-к-аудио>"; exit 1; }
SESSDIR="${SESSDIR%/}"
echo "📂 Сессия: $SESSDIR"

# whisper бинарь
WBIN=$(command -v whisper-cli || command -v whisper-cpp || true)
[ -n "$WBIN" ] || { echo "❌ whisper-cli не найден (brew install whisper-cpp)"; exit 1; }
[ -f "$MODEL" ] || { echo "❌ Нет модели $MODEL"; exit 1; }

THREADS="${WHISPER_THREADS:-$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || sysctl -n hw.physicalcpu 2>/dev/null || echo 4)}"
CPU_THREADS="${WHISPER_CPU_THREADS:-2}"
CPU_NICE="${WHISPER_CPU_NICE:-10}"

run_cpu_whisper() {
  local input="$1"
  local output="${input%.wav}"
  nice -n "$CPU_NICE" "$WBIN" -ng -m "$MODEL" -l "$LANG_CODE" -f "$input" -otxt -of "$output" -t "$CPU_THREADS" -pp 2>/dev/null
}

run_whisper() {
  local input="$1"
  local output="${input%.wav}"

  if [ "${WHISPER_NO_GPU:-0}" = "1" ]; then
    run_cpu_whisper "$input"
    return 0
  fi

  if "$WBIN" -m "$MODEL" -l "$LANG_CODE" -f "$input" -otxt -of "$output" -t "$THREADS" -pp 2>/dev/null; then
    return 0
  fi

  echo "⚠️  whisper-cli упал на GPU/Metal, повторяю на CPU (-ng, threads=$CPU_THREADS, nice=$CPU_NICE)"
  run_cpu_whisper "$input"
}

TRANSCRIPT="$SESSDIR/transcript.txt"
: > "$TRANSCRIPT"
shopt -s nullglob
CHUNKS=("$SESSDIR"/chunk_*.wav)
[ ${#CHUNKS[@]} -gt 0 ] || { echo "❌ Нет файлов chunk_*.wav в $SESSDIR"; exit 1; }

echo "🗣  Транскрибирую ${#CHUNKS[@]} кусок(ов) моделью large-v3-turbo, lang=$LANG_CODE, gpu_threads=$THREADS, cpu_fallback_threads=$CPU_THREADS"
for f in "${CHUNKS[@]}"; do
  echo "   >> $(basename "$f")"
  run_whisper "$f"
  cat "${f%.wav}.txt" >> "$TRANSCRIPT"
  printf '\n' >> "$TRANSCRIPT"
done
WORDS=$(wc -w < "$TRANSCRIPT" | tr -d ' ')
echo "✅ Транскрипт готов: $TRANSCRIPT ($WORDS слов)"

# ---- Саммари через внешний CLI по явному opt-in ----
SUMMARY="$SESSDIR/summary.md"
PROMPTFILE="$SESSDIR/.prompt.txt"
{
  cat <<'EOP'
Ты делаешь конспект вебинара. Ниже — автоматическая расшифровка ~4-часового вебинара
(язык русский, возможны ошибки распознавания речи). Сделай структурированное саммари
на русском в Markdown:

1. **Краткое резюме** — 3-5 предложений, о чём вебинар.
2. **Основные темы** — по разделам, с ключевыми тезисами.
3. **Важные факты, цифры, определения.**
4. **Практические выводы и рекомендации.**
5. **Action items** — что конкретно сделать / проверить.
6. **Открытые вопросы.**

Игнорируй оговорки, повторы и явный шум распознавания. Не выдумывай того, чего нет в тексте.

=== РАСШИФРОВКА ===
EOP
  cat "$TRANSCRIPT"
} > "$PROMPTFILE"

echo "🧠 Делаю саммари…"
: > "$SUMMARY"

if [ "$SUMMARY_PROVIDER" = "none" ]; then
  rm -f "$PROMPTFILE" "$SUMMARY"
  echo "ℹ️  Саммари пропущено: по умолчанию транскрипт не отправляется во внешние CLI."
  echo "   Если нужен конспект через claude/codex, запусти: SUMMARY_PROVIDER=auto ./process.sh <сессия>"
  exit 0
fi

# 1) claude CLI как one-shot генератор (без агентного цикла)
if [ "$SUMMARY_PROVIDER" = "auto" ] || [ "$SUMMARY_PROVIDER" = "claude" ]; then
if command -v claude >/dev/null 2>&1; then
  claude -p --model claude-sonnet-4-6 \
    --allowedTools "" --strict-mcp-config --setting-sources "" \
    --system-prompt "Ты аккуратный редактор, делающий конспекты. Отвечай только готовым текстом саммари." \
    < "$PROMPTFILE" > "$SUMMARY" 2>/dev/null || true
fi
fi

# 2) fallback — codex CLI (ChatGPT-подписка)
if [ ! -s "$SUMMARY" ] && { [ "$SUMMARY_PROVIDER" = "auto" ] || [ "$SUMMARY_PROVIDER" = "codex" ]; }; then
if command -v codex >/dev/null 2>&1; then
  codex exec --skip-git-repo-check --ephemeral --color never \
    --sandbox read-only -c model_reasoning_effort=low \
    --output-last-message "$SUMMARY" - < "$PROMPTFILE" >/dev/null 2>&1 || true
fi
fi

rm -f "$PROMPTFILE"
if [ -s "$SUMMARY" ]; then
  echo "✅ Саммари: $SUMMARY"
  echo "------------------------------------------"
  cat "$SUMMARY"
else
  echo "⚠️  LLM не дал саммари автоматически. Транскрипт готов ($TRANSCRIPT) —"
  echo "   можешь скинуть его мне в чат, и я сделаю конспект."
fi
