#!/bin/bash
# Записывает системный звук (то, что слышно из Zoom) через BlackHole.
# Пишет 30-минутными кусками 16kHz mono WAV — если что-то упадёт, теряется максимум последний кусок.
# Остановить запись: Ctrl+C (или просто закрой окно после вебинара).
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SESSION="${1:-webinar_$(date +%Y%m%d_%H%M)}"
DIR="$BASE/out/$SESSION"
mkdir -p "$DIR"

# Найти индекс аудио-устройства BlackHole для avfoundation
DEVLIST=$(ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true)
IDX=$(printf '%s\n' "$DEVLIST" \
  | awk '/AVFoundation audio devices/{a=1;next} /AVFoundation video devices/{a=0} a' \
  | grep -i blackhole | head -1 | sed -E 's/.*\[([0-9]+)\].*/\1/' || true)

if [ -z "${IDX:-}" ]; then
  echo "❌ BlackHole не найден среди аудио-устройств. Что увидел ffmpeg:"
  echo "------------------------------------------"
  printf '%s\n' "$DEVLIST"
  echo "------------------------------------------"
  echo "Если список аудио пуст / есть 'Input/output error' → нет доступа к микрофону:"
  echo "  System Settings → Privacy & Security → Microphone → включи свой Terminal."
  echo "Если BlackHole нет в списке → перезагрузи Mac (BlackHole не подхватился)."
  exit 1
fi

echo "🎙  Пишу с устройства [$IDX] BlackHole → $DIR"
echo "    Куски по 30 мин: chunk_000.wav, chunk_001.wav, ..."
echo "    Останови: Ctrl+C после вебинара."
echo

exec ffmpeg -hide_banner -loglevel warning \
  -f avfoundation -i ":$IDX" \
  -ac 1 -ar 16000 \
  -f segment -segment_time 1800 -reset_timestamps 1 \
  "$DIR/chunk_%03d.wav"
