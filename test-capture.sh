#!/bin/bash
# Быстрый тест ДО вебинара: 8 секунд записи + проверка, что звук реально захватывается.
# Перед запуском включи любое видео/музыку со звуком (YouTube и т.п.).
set -euo pipefail

DEVLIST=$(ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 || true)
IDX=$(printf '%s\n' "$DEVLIST" \
  | awk '/AVFoundation audio devices/{a=1;next} /AVFoundation video devices/{a=0} a' \
  | grep -i blackhole | head -1 | sed -E 's/.*\[([0-9]+)\].*/\1/' || true)

if [ -z "${IDX:-}" ]; then
  echo "❌ BlackHole не найден. Что увидел ffmpeg:"
  echo "------------------------------------------"
  printf '%s\n' "$DEVLIST"
  echo "------------------------------------------"
  echo "Пустой список аудио / 'Input/output error' → нет доступа к микрофону:"
  echo "  System Settings → Privacy & Security → Microphone → включи свой Terminal."
  exit 1
fi

echo "🔎 Тест 8 сек с устройства [$IDX] BlackHole. Включи звук (видео/музыку)..."
LEVELS=$(ffmpeg -hide_banner -f avfoundation -i ":$IDX" -t 8 -af volumedetect -f null - 2>&1 \
  | grep -E "mean_volume|max_volume" || true)
echo "$LEVELS"

MAX=$(echo "$LEVELS" | grep max_volume | sed -E 's/.*max_volume: (-?[0-9.]+) dB.*/\1/')
if [ -z "${MAX:-}" ]; then
  echo "⚠️  Не удалось измерить уровень. Проверь, что выбран Multi-Output Device в System Settings → Sound → Output."
elif awk "BEGIN{exit !($MAX < -80)}"; then
  echo "❌ Тишина (max ${MAX} dB). Звук НЕ доходит до BlackHole."
  echo "   Проверь: System Settings → Sound → Output = Multi-Output Device, и звук реально играет."
else
  echo "✅ Звук захватывается (max ${MAX} dB). Всё готово к записи — запускай ./record.sh"
fi
