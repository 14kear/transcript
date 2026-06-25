#!/bin/bash
# Запись с МИКРОФОНА — для офлайн-лекций/встреч в комнате (без BlackHole).
# Пишет 16 кГц моно кусками по 30 мин в out/<сессия>/.
#
#   ./record-mic.sh            запись (авто-выбор встроенного микрофона)
#   ./record-mic.sh --list     показать доступные аудио-входы и выйти
#   ./record-mic.sh --test     8-секундный тест уровня звука
#   MIC=2 ./record-mic.sh      принудительно устройство с индексом 2 (внешний микрофон)
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="${1:-record}"

DEVLIST=$(ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true)
AUDIO=$(printf '%s\n' "$DEVLIST" | awk '/AVFoundation audio devices/{a=1;next} /AVFoundation video devices/{a=0} a')

if [ "$MODE" = "--list" ]; then
  echo "Доступные аудио-входы:"; printf '%s\n' "$AUDIO"; exit 0
fi

# Выбор устройства: MIC=<index> приоритетнее; иначе встроенный микрофон; иначе индекс 0
if [ -n "${MIC:-}" ]; then
  IDX="$MIC"
else
  IDX=$(printf '%s\n' "$AUDIO" | grep -iE 'microphone|macbook' | grep -vi blackhole \
        | head -1 | sed -E 's/.*\[([0-9]+)\].*/\1/' || true)
  [ -n "${IDX:-}" ] || IDX=0
fi

if [ -z "${IDX:-}" ]; then
  echo "❌ Не нашёл аудио-вход. Список:"; printf '%s\n' "$AUDIO"
  echo "Укажи вручную:  MIC=<индекс> ./record-mic.sh"
  exit 1
fi
DEVNAME=$(printf '%s\n' "$AUDIO" | grep -E "\[$IDX\]" | head -1 | sed -E 's/.*\] //')

if [ "$MODE" = "--test" ]; then
  echo "🔎 Тест 8 сек с устройства [$IDX] ${DEVNAME:-?}. Говори в микрофон..."
  L=$(ffmpeg -hide_banner -f avfoundation -i ":$IDX" -t 8 -af volumedetect -f null - 2>&1 \
      | grep -E "mean_volume|max_volume" || true)
  echo "$L"
  MAX=$(echo "$L" | grep max_volume | sed -E 's/.*max_volume: (-?[0-9.]+) dB.*/\1/')
  if [ -z "${MAX:-}" ]; then echo "⚠️ Не измерил уровень. Проверь доступ к микрофону."
  elif awk "BEGIN{exit !($MAX < -80)}"; then echo "❌ Тишина — звук не доходит. Проверь устройство/доступ к микрофону."
  else echo "✅ Звук ловится (max ${MAX} dB). Готово к записи."; fi
  exit 0
fi

SESSION="${SESSION:-lecture_$(date +%Y%m%d_%H%M)}"
DIR="$BASE/out/$SESSION"; mkdir -p "$DIR"
echo "🎙  Пишу с микрофона [$IDX] ${DEVNAME:-?} → $DIR"
echo "    Куски по 30 мин. Останови: Ctrl+C."
echo
exec ffmpeg -hide_banner -loglevel warning \
  -f avfoundation -i ":$IDX" \
  -ac 1 -ar 16000 \
  -f segment -segment_time 1800 -reset_timestamps 1 \
  "$DIR/chunk_%03d.wav"
