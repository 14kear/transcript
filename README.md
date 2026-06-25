# webinar-recorder

Локальный пайплайн **запись → транскрипция → саммари** для онлайн-встреч и вебинаров на **macOS**. Всё считается локально, без облака и без подписок на транскрибацию: данные не покидают твой Mac.

- 🎙 Захват системного звука (Zoom / любой плеер) через виртуальное аудио **BlackHole**
- 🗣 Распознавание речи локально на GPU через **whisper.cpp** (модель large-v3-turbo, русский и др.)
- 📝 Структурированный конспект в **Markdown + PDF**

---

## Требования
- macOS (Apple Silicon или Intel)
- [Homebrew](https://brew.sh)
- ~2 ГБ места под модель
- Для шага саммари — установленный и залогиненный CLI `claude` **или** `codex` (опционально; без них получишь только транскрипт)

## Установка
```bash
git clone <этот-репозиторий> webinar-recorder
cd webinar-recorder
./setup.sh          # ffmpeg + whisper-cpp + BlackHole + скачивание модели
```

## Настройка звука (один раз, вручную)
macOS не даёт писать системный звук напрямую — нужен «двойной выход», чтобы ты **и слышал**, и **записывал**:

1. Открой **Audio MIDI Setup** (Spotlight → «Audio MIDI Setup»).
2. Внизу слева **«+» → Create Multi-Output Device**.
3. Поставь галочки на **двух** устройствах: то, через что слушаешь (наушники/динамики) **и** **BlackHole 2ch**.
4. Устройство, через которое слушаешь, оставь **Master/Primary**; у **BlackHole** включи **Drift Correction**.

   | Устройство | Use | Master | Drift Correction |
   |---|---|---|---|
   | Твои наушники/динамики | ✅ | ✅ | ⬜ |
   | BlackHole 2ch | ✅ | ⬜ | ✅ |

5. **System Settings → Sound → Output → выбери Multi-Output Device.**
   (Громкость с клавиатуры при этом не работает — выставь её заранее в Zoom.)

## Использование
```bash
# 1) Проверь захват ДО встречи (включи любое видео со звуком):
./test-capture.sh                 # ждём «✅ Звук захватывается»

# 2) Во время встречи (caffeinate не даёт Mac уснуть):
caffeinate -i ./record.sh         # Ctrl+C в конце

# 3) После встречи — транскрипция + саммари:
./process.sh                      # берёт последнюю сессию
# или конкретную:  ./process.sh webinar_20260625_1700
```

Результаты — в `out/<сессия>/`:
- `transcript.txt` — полная расшифровка
- `summary.md` / `summary.pdf` — конспект

### Язык
По умолчанию русский. Другой язык:
```bash
WHISPER_LANG=en ./process.sh
```

### PDF
`process.sh` делает только `.md`. Для PDF нужен `pandoc` (`brew install pandoc`) — конвертация идёт через headless Google Chrome:
```bash
pandoc summary.md -s -o summary.html
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --no-pdf-header-footer --print-to-pdf=summary.pdf "file://$PWD/summary.html"
```

## Как это работает
- `record.sh` — находит BlackHole в `ffmpeg avfoundation`, пишет **16 кГц моно** кусками по 30 мин (`chunk_NNN.wav`) — при сбое теряется максимум последние полчаса.
- `process.sh` — гоняет каждый кусок через `whisper-cli` → склеивает `transcript.txt` → отдаёт в `claude`/`codex` CLI для конспекта.

## Известные ограничения
- ⚠️ **Потеря ~10–15% сэмплов** при длинной записи (дрейф тактовой частоты BlackHole vs ресемплер в ffmpeg). На транскрипт влияет мелкими пропусками слов; для конспекта обычно некритично. *(TODO: писать в нативные 48 кГц без ресемплинга на лету, понижать до 16 кГц уже при транскрипции.)*
- Нужен ручной шаг с Multi-Output Device (см. выше) — автоматизировать средствами CLI нельзя.

## Траблшутинг
- **`record.sh`/`test-capture.sh` молча выходят или «Input/output error»** → нет доступа к микрофону: **System Settings → Privacy & Security → Microphone → включи свой Terminal** и запусти заново (BlackHole для macOS = «микрофон»).
- **«BlackHole не найден»** → не сделал `sudo killall coreaudiod`, либо нужен ребут.
- **Тишина в `test-capture.sh`** → в System Settings → Sound → Output не выбран Multi-Output Device, или звук реально не играет.
