#!/bin/bash
# После вебинара: транскрибирует все куски и делает саммари.
# Использование:  ./process.sh                  (берёт самую свежую сессию)
#                 ./process.sh webinar_20260625_1600   (конкретная папка в out/)
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL="$BASE/models/ggml-large-v3-turbo.bin"
LANG_CODE="${WHISPER_LANG:-ru}"   # язык вебинара; переопредели: WHISPER_LANG=en ./process.sh

# Выбор сессии
if [ -n "${1:-}" ]; then
  SESSDIR=$([ -d "$1" ] && echo "$1" || echo "$BASE/out/$1")
else
  SESSDIR=$(ls -dt "$BASE"/out/*/ 2>/dev/null | head -1)
fi
[ -d "${SESSDIR:-}" ] || { echo "❌ Не найдена папка сессии. Укажи её: ./process.sh <имя>"; exit 1; }
SESSDIR="${SESSDIR%/}"
echo "📂 Сессия: $SESSDIR"

# whisper бинарь
WBIN=$(command -v whisper-cli || command -v whisper-cpp || true)
[ -n "$WBIN" ] || { echo "❌ whisper-cli не найден (brew install whisper-cpp)"; exit 1; }
[ -f "$MODEL" ] || { echo "❌ Нет модели $MODEL"; exit 1; }

THREADS=$(sysctl -n hw.perflevel0.physicalcpu 2>/dev/null || sysctl -n hw.physicalcpu 2>/dev/null || echo 8)

TRANSCRIPT="$SESSDIR/transcript.txt"
: > "$TRANSCRIPT"
shopt -s nullglob
CHUNKS=("$SESSDIR"/chunk_*.wav)
[ ${#CHUNKS[@]} -gt 0 ] || { echo "❌ Нет файлов chunk_*.wav в $SESSDIR"; exit 1; }

echo "🗣  Транскрибирую ${#CHUNKS[@]} кусок(ов) моделью large-v3-turbo, lang=$LANG_CODE, threads=$THREADS"
for f in "${CHUNKS[@]}"; do
  echo "   >> $(basename "$f")"
  "$WBIN" -m "$MODEL" -l "$LANG_CODE" -f "$f" -otxt -of "${f%.wav}" -t "$THREADS" -pp 2>/dev/null
  cat "${f%.wav}.txt" >> "$TRANSCRIPT"
  printf '\n' >> "$TRANSCRIPT"
done
WORDS=$(wc -w < "$TRANSCRIPT" | tr -d ' ')
echo "✅ Транскрипт готов: $TRANSCRIPT ($WORDS слов)"

# ---- Саммари через локальный LLM ----
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

# 1) claude CLI как one-shot генератор (без агентного цикла)
if command -v claude >/dev/null 2>&1; then
  claude -p --model claude-sonnet-4-6 \
    --allowedTools "" --strict-mcp-config --setting-sources "" \
    --system-prompt "Ты аккуратный редактор, делающий конспекты. Отвечай только готовым текстом саммари." \
    < "$PROMPTFILE" > "$SUMMARY" 2>/dev/null || true
fi

# 2) fallback — codex CLI (ChatGPT-подписка)
if [ ! -s "$SUMMARY" ] && command -v codex >/dev/null 2>&1; then
  codex exec --skip-git-repo-check --ephemeral --color never \
    --sandbox read-only -c model_reasoning_effort=low \
    --output-last-message "$SUMMARY" - < "$PROMPTFILE" >/dev/null 2>&1 || true
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
