#!/bin/bash
# Установка зависимостей для webinar-recorder (macOS).
# Запуск: ./setup.sh
set -euo pipefail
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Проверяю Homebrew"
command -v brew >/dev/null || { echo "❌ Нет Homebrew. Поставь: https://brew.sh"; exit 1; }

echo "==> Ставлю ffmpeg + whisper-cpp"
brew install ffmpeg whisper-cpp

echo "==> Ставлю BlackHole (виртуальное аудио; попросит пароль админа)"
brew list --cask blackhole-2ch >/dev/null 2>&1 || brew install --cask blackhole-2ch
echo "    Перезагружаю аудио-демон, чтобы BlackHole появился без ребута..."
sudo killall coreaudiod || true

echo "==> Качаю модель whisper large-v3-turbo (~1.6 ГБ)"
mkdir -p "$BASE/models"
if [ ! -f "$BASE/models/ggml-large-v3-turbo.bin" ]; then
  curl -L -f -o "$BASE/models/ggml-large-v3-turbo.bin" \
    https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin
else
  echo "    Модель уже на месте, пропускаю."
fi

echo
echo "✅ Зависимости готовы."
echo "ОСТАЛСЯ ОДИН РУЧНОЙ ШАГ (см. README → «Настройка звука»):"
echo "  создай Multi-Output Device в Audio MIDI Setup (твои наушники + BlackHole 2ch)"
echo "  и выбери его в System Settings → Sound → Output."
echo "Потом проверь: ./test-capture.sh"
