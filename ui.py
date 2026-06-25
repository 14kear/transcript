#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse


BASE = Path(__file__).resolve().parent
OUT_DIR = BASE / "out"
UPLOAD_DIR = OUT_DIR / "uploads"
HOST = "127.0.0.1"
PORT = int(os.environ.get("UI_PORT", "8787"))
LOG_LIMIT = 1600

SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
UNSAFE_FILENAME_RE = re.compile(r"[/\\:\x00-\x1f\x7f]+")
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "\U0000200D"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)


HTML = r"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Transcript</title>
  <style>
    :root {
      --bg: #f7f6f3;
      --surface: #ffffff;
      --surface-soft: #fbfbfa;
      --text: #1f2320;
      --muted: #787774;
      --line: #eaeaea;
      --green-bg: #edf3ec;
      --green-text: #346538;
      --blue-bg: #e1f3fe;
      --blue-text: #1f6c9f;
      --yellow-bg: #fbf3db;
      --yellow-text: #956400;
      --red-bg: #fdebec;
      --red-text: #9f2f2d;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
      line-height: 1.55;
    }

    button,
    input {
      font: inherit;
    }

    .shell {
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 28px 0 40px;
    }

    header {
      padding: 20px 0 34px;
      border-bottom: 1px solid var(--line);
    }

    h1 {
      margin: 0;
      max-width: 760px;
      font-family: "Lyon Text", "Newsreader", "Georgia", serif;
      font-size: clamp(42px, 7vw, 82px);
      font-weight: 500;
      line-height: 0.98;
      letter-spacing: -0.03em;
    }

    .tag {
      display: inline-flex;
      align-items: center;
      min-height: 26px;
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--surface);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      white-space: nowrap;
    }

    .tag.green {
      background: var(--green-bg);
      color: var(--green-text);
      border-color: transparent;
    }

    .tag.blue {
      background: var(--blue-bg);
      color: var(--blue-text);
      border-color: transparent;
    }

    .tag.yellow {
      background: var(--yellow-bg);
      color: var(--yellow-text);
      border-color: transparent;
    }

    .tag.red {
      background: var(--red-bg);
      color: var(--red-text);
      border-color: transparent;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      padding: 22px 0;
    }

    .card,
    .panel {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 12px;
    }

    .card {
      display: flex;
      min-height: 258px;
      flex-direction: column;
      padding: 24px;
      transition: box-shadow 180ms ease, transform 180ms ease;
    }

    .card:hover {
      box-shadow: 0 2px 10px rgba(0, 0, 0, 0.035);
      transform: translateY(-1px);
    }

    .card h2,
    .panel h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 650;
      letter-spacing: 0;
    }

    .card p {
      margin: 10px 0 0;
      color: var(--muted);
      font-size: 14px;
    }

    .spacer {
      flex: 1;
    }

    .actions {
      display: grid;
      gap: 10px;
      margin-top: 20px;
    }

    .row {
      display: flex;
      gap: 10px;
      align-items: center;
    }

    .row > * {
      flex: 1;
    }

    .file {
      width: 100%;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface-soft);
      color: var(--text);
      font-size: 14px;
    }

    .button {
      min-height: 42px;
      border: 1px solid #111111;
      border-radius: 6px;
      background: #111111;
      color: #ffffff;
      cursor: pointer;
      font-weight: 650;
      transition: background 160ms ease, transform 120ms ease, border-color 160ms ease;
    }

    .button:hover:not(:disabled) {
      background: #333333;
      border-color: #333333;
    }

    .button:active:not(:disabled) {
      transform: scale(0.98);
    }

    .button.secondary {
      background: #ffffff;
      color: var(--text);
      border-color: var(--line);
    }

    .button.secondary:hover:not(:disabled) {
      background: #f4f4f2;
      border-color: #d7d7d3;
    }

    .button.danger {
      background: #ffffff;
      color: var(--red-text);
      border-color: #efcfce;
    }

    .button:disabled {
      cursor: not-allowed;
      opacity: 0.42;
    }

    progress {
      width: 100%;
      height: 8px;
      overflow: hidden;
      border: 0;
      border-radius: 999px;
      background: #ecebe8;
    }

    progress::-webkit-progress-bar {
      background: #ecebe8;
      border-radius: 999px;
    }

    progress::-webkit-progress-value {
      background: #111111;
      border-radius: 999px;
    }

    .panel {
      display: grid;
      grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
      overflow: hidden;
    }

    .result {
      padding: 24px;
      border-right: 1px solid var(--line);
      background: var(--surface-soft);
    }

    .item {
      display: grid;
      gap: 5px;
      margin-top: 18px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--line);
    }

    .item:last-child {
      border-bottom: 0;
      padding-bottom: 0;
    }

    .label {
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }

    .value {
      overflow-wrap: anywhere;
      font-family: "Geist Mono", "SF Mono", Menlo, monospace;
      font-size: 13px;
    }

    .links {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 18px;
    }

    .link {
      display: flex;
      min-height: 38px;
      align-items: center;
      justify-content: center;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--text);
      text-decoration: none;
      font-size: 14px;
      font-weight: 650;
    }

    .link.muted {
      color: var(--muted);
      pointer-events: none;
      opacity: 0.5;
    }

    .empty {
      color: var(--muted);
    }

    .log {
      min-height: 300px;
      max-height: 460px;
      margin: 0;
      padding: 24px;
      overflow: auto;
      background: #ffffff;
      color: #2f3437;
      font-family: "Geist Mono", "SF Mono", Menlo, monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
    }

    @media (max-width: 920px) {
      header,
      .panel {
        display: block;
      }

      .grid {
        grid-template-columns: 1fr;
      }

      .result {
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <h1>Запись и транскрибация</h1>
    </header>

    <section class="grid" aria-label="Actions">
      <article class="card">
        <span class="tag blue">Файл</span>
        <h2>Готовая запись</h2>
        <p>m4a, mp3, wav, mp4, caf, aiff и другие форматы ffmpeg.</p>
        <div class="spacer"></div>
        <div class="actions">
          <input id="fileInput" class="file" type="file" accept="audio/*,video/*,.m4a,.mp3,.wav,.mp4,.mov,.aac,.caf,.aif,.aiff,.flac,.ogg,.opus,.webm">
          <progress id="uploadProgress" value="0" max="100" hidden></progress>
          <button id="uploadButton" class="button" type="button">Транскрибировать файл</button>
        </div>
      </article>

      <article class="card">
        <span class="tag yellow">Микрофон</span>
        <h2>Офлайн встреча</h2>
        <p>Запись с выбранного системного микрофона через текущий record-mic.sh.</p>
        <div class="spacer"></div>
        <div class="actions">
          <div class="row">
            <button id="micStart" class="button" type="button">Начать</button>
            <button id="micStop" class="button danger" type="button">Остановить</button>
          </div>
          <button id="micProcess" class="button secondary" type="button">Обработать запись</button>
        </div>
      </article>

      <article class="card">
        <span class="tag red">Zoom</span>
        <h2>Системный звук</h2>
        <p>Запись через BlackHole и текущий record.sh.</p>
        <div class="spacer"></div>
        <div class="actions">
          <div class="row">
            <button id="zoomStart" class="button" type="button">Начать</button>
            <button id="zoomStop" class="button danger" type="button">Остановить</button>
          </div>
          <button id="zoomProcess" class="button secondary" type="button">Обработать запись</button>
        </div>
      </article>
    </section>

    <section class="panel" aria-label="Result and log">
      <div class="result">
        <h2>Результат</h2>
        <div class="item">
          <span class="label">Папка</span>
          <span id="resultPath" class="value empty">Файлы появятся после записи или загрузки.</span>
        </div>
        <div class="links">
          <a id="transcriptLink" class="link muted" href="#">transcript.txt</a>
          <a id="summaryLink" class="link muted" href="#">summary.md</a>
        </div>
      </div>
      <pre id="log" class="log">Лог появится после запуска операции.</pre>
    </section>
  </main>

  <script>
    const el = (id) => document.getElementById(id);
    const buttons = ["uploadButton", "micStart", "micStop", "micProcess", "zoomStart", "zoomStop", "zoomProcess"]
      .reduce((acc, id) => ({ ...acc, [id]: el(id) }), {});

    let lastStatus = null;

    function setDisabled(running, activeKind) {
      buttons.uploadButton.disabled = running;
      buttons.micStart.disabled = running;
      buttons.zoomStart.disabled = running;
      buttons.micStop.disabled = !(running && activeKind === "record_mic");
      buttons.zoomStop.disabled = !(running && activeKind === "record_zoom");
      buttons.micProcess.disabled = running || !lastStatus?.last_session;
      buttons.zoomProcess.disabled = running || !lastStatus?.last_session;
    }

    function updateLink(anchor, url) {
      anchor.href = url || "#";
      anchor.classList.toggle("muted", !url);
    }

    function renderStatus(data) {
      lastStatus = data;
      const running = Boolean(data.active);
      const resultPath = el("resultPath");
      resultPath.textContent = data.result?.path || "Файлы появятся после записи или загрузки.";
      resultPath.classList.toggle("empty", !data.result?.path);
      updateLink(el("transcriptLink"), data.result?.transcript_url);
      updateLink(el("summaryLink"), data.result?.summary_url);
      el("log").textContent = data.logs.length ? data.logs.join("\n") : "Лог появится после запуска операции.";
      el("log").scrollTop = el("log").scrollHeight;
      setDisabled(running, data.active?.kind);
    }

    async function refresh() {
      const response = await fetch("/api/status");
      renderStatus(await response.json());
    }

    async function postJson(path, body = {}) {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Request failed");
      await refresh();
      return data;
    }

    function uploadFile() {
      const input = el("fileInput");
      const file = input.files && input.files[0];
      if (!file) {
        alert("Выбери файл");
        return;
      }

      const progress = el("uploadProgress");
      progress.hidden = false;
      progress.value = 0;
      buttons.uploadButton.disabled = true;

      const xhr = new XMLHttpRequest();
      xhr.open("POST", `/api/upload?name=${encodeURIComponent(file.name)}`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) progress.value = Math.round((event.loaded / event.total) * 100);
      };
      xhr.onload = async () => {
        progress.value = 100;
        if (xhr.status >= 200 && xhr.status < 300) {
          input.value = "";
          await refresh();
          return;
        }
        try {
          alert(JSON.parse(xhr.responseText).error || "Upload failed");
        } catch {
          alert("Upload failed");
        }
        await refresh();
      };
      xhr.onerror = async () => {
        alert("Upload failed");
        await refresh();
      };
      xhr.send(file);
    }

    buttons.uploadButton.addEventListener("click", uploadFile);
    buttons.micStart.addEventListener("click", () => postJson("/api/record/start", { mode: "mic" }).catch((e) => alert(e.message)));
    buttons.zoomStart.addEventListener("click", () => postJson("/api/record/start", { mode: "zoom" }).catch((e) => alert(e.message)));
    buttons.micStop.addEventListener("click", () => postJson("/api/record/stop").catch((e) => alert(e.message)));
    buttons.zoomStop.addEventListener("click", () => postJson("/api/record/stop").catch((e) => alert(e.message)));
    buttons.micProcess.addEventListener("click", () => postJson("/api/process-session").catch((e) => alert(e.message)));
    buttons.zoomProcess.addEventListener("click", () => postJson("/api/process-session").catch((e) => alert(e.message)));

    refresh();
    setInterval(refresh, 1500);
  </script>
</body>
</html>
"""


class AppState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.process: subprocess.Popen[str] | None = None
        self.active: dict[str, str] | None = None
        self.last_session: str | None = None
        self.logs: deque[str] = deque(maxlen=LOG_LIMIT)

    def append_log(self, line: str) -> None:
        clean = EMOJI_RE.sub("", line).strip()
        if not clean:
            return
        stamp = time.strftime("%H:%M:%S")
        with self.lock:
            self.logs.append(f"[{stamp}] {clean}")

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            active = self.active
            last_session = active["session"] if active else self.last_session
            if not active and not session_result(last_session):
                last_session = latest_session()
                self.last_session = last_session
            result = session_result(last_session)
            return {
                "active": active,
                "last_session": last_session,
                "result": result,
                "logs": list(self.logs),
            }


STATE = AppState()


def now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def slugify(value: str, fallback: str = "session") -> str:
    stem = Path(value).stem
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem).strip("._-")
    return (slug[:48] or fallback)


def safe_upload_name(filename: str) -> str:
    name = Path(filename or "audio").name
    name = UNSAFE_FILENAME_RE.sub("_", name).strip(" .")
    if not name:
        name = "audio"
    if "." not in name:
        name = f"{name}.audio"
    return f"{now_stamp()}_{name}"


def make_session(prefix: str, name: str = "") -> str:
    slug = slugify(name, prefix)
    return f"ui_{prefix}_{slug}_{now_stamp()}"


def session_path(session: str | None) -> Path | None:
    if not session or not SESSION_RE.fullmatch(session):
        return None
    path = (OUT_DIR / session).resolve()
    if OUT_DIR.resolve() not in path.parents:
        return None
    return path


def session_result(session: str | None) -> dict[str, object] | None:
    path = session_path(session)
    if not path or not path.exists():
        return None
    transcript = path / "transcript.txt"
    summary = path / "summary.md"
    return {
        "session": session,
        "path": str(path),
        "transcript_url": f"/files/{session}/transcript.txt" if transcript.exists() and transcript.stat().st_size > 0 else None,
        "summary_url": f"/files/{session}/summary.md" if summary.exists() and summary.stat().st_size > 0 else None,
    }


def latest_session() -> str | None:
    if not OUT_DIR.exists():
        return None
    sessions = [
        path
        for path in OUT_DIR.iterdir()
        if path.is_dir() and path.name != "uploads" and SESSION_RE.fullmatch(path.name)
    ]
    if not sessions:
        return None
    return max(sessions, key=lambda path: path.stat().st_mtime).name


def command_with_caffeinate(args: list[str]) -> list[str]:
    caffeinate = shutil.which("caffeinate")
    if caffeinate:
        return [caffeinate, "-i", *args]
    return args


def start_process(
    args: list[str],
    *,
    kind: str,
    title: str,
    session: str,
    env: dict[str, str] | None = None,
) -> None:
    with STATE.lock:
        if STATE.process and STATE.process.poll() is None:
            raise RuntimeError("Уже выполняется операция")

        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        process = subprocess.Popen(
            args,
            cwd=BASE,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        STATE.process = process
        STATE.active = {
            "kind": kind,
            "title": title,
            "session": session,
            "started_at": time.strftime("%H:%M:%S"),
        }
        STATE.last_session = session
        STATE.append_log(f"{title}: {session}")

    thread = threading.Thread(target=watch_process, args=(process, kind, title, session), daemon=True)
    thread.start()


def watch_process(process: subprocess.Popen[str], kind: str, title: str, session: str) -> None:
    if process.stdout:
        for line in process.stdout:
            STATE.append_log(line)
    code = process.wait()
    with STATE.lock:
        if STATE.process is process:
            STATE.process = None
            STATE.active = None
            STATE.last_session = session
    if code == 0:
        STATE.append_log(f"{title}: завершено")
    else:
        STATE.append_log(f"{title}: завершено с кодом {code}")


def stop_recording() -> None:
    with STATE.lock:
        process = STATE.process
        active = STATE.active
        if not process or process.poll() is not None or not active:
            raise RuntimeError("Активной записи нет")
        if active["kind"] not in {"record_mic", "record_zoom"}:
            raise RuntimeError("Сейчас идет не запись")
        STATE.append_log("Останавливаю запись")

    os.killpg(process.pid, signal.SIGINT)


def process_session(session: str | None) -> None:
    target = session or STATE.last_session
    path = session_path(target)
    if not target or not path or not path.exists():
        raise RuntimeError("Нет сессии для обработки")
    start_process(
        [str(BASE / "process.sh"), target],
        kind="process",
        title="Обработка",
        session=target,
        env={"WHISPER_THREADS": "4"},
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "TranscriptUI/1.0"

    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_html(HTML)
            return
        if parsed.path == "/api/status":
            self.send_json(STATE.snapshot())
            return
        if parsed.path.startswith("/files/"):
            self.send_result_file(parsed.path)
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/upload":
                self.handle_upload(parsed)
            elif parsed.path == "/api/record/start":
                self.handle_record_start()
            elif parsed.path == "/api/record/stop":
                stop_recording()
                self.send_json({"ok": True})
            elif parsed.path == "/api/process-session":
                payload = self.read_json_body()
                process_session(payload.get("session"))
                self.send_json({"ok": True})
            else:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
        except RuntimeError as exc:
            self.send_error_json(HTTPStatus.CONFLICT, str(exc))
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
        except Exception as exc:
            self.send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))

    def handle_upload(self, parsed) -> None:
        with STATE.lock:
            if STATE.process and STATE.process.poll() is None:
                raise RuntimeError("Уже выполняется операция")

        length_header = self.headers.get("Content-Length")
        if not length_header:
            raise ValueError("Не передан размер файла")
        try:
            remaining = int(length_header)
        except ValueError as exc:
            raise ValueError("Некорректный размер файла") from exc
        if remaining <= 0:
            raise ValueError("Файл пустой")

        name = parse_qs(parsed.query).get("name", ["audio"])[0]
        upload_name = safe_upload_name(unquote(name))
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        destination = UPLOAD_DIR / upload_name

        with destination.open("wb") as file:
            while remaining > 0:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                file.write(chunk)
                remaining -= len(chunk)

        if remaining != 0:
            destination.unlink(missing_ok=True)
            raise ValueError("Файл загрузился не полностью")

        session = make_session("upload", upload_name)
        start_process(
            [str(BASE / "process.sh"), str(destination)],
            kind="process",
            title="Обработка файла",
            session=session,
            env={"SESSION": session, "WHISPER_THREADS": "4"},
        )
        self.send_json({"ok": True, "session": session})

    def handle_record_start(self) -> None:
        payload = self.read_json_body()
        mode = payload.get("mode")
        if mode == "mic":
            session = make_session("mic", "offline")
            cmd = command_with_caffeinate([str(BASE / "record-mic.sh")])
            start_process(cmd, kind="record_mic", title="Запись микрофона", session=session, env={"SESSION": session})
            self.send_json({"ok": True, "session": session})
            return
        if mode == "zoom":
            session = make_session("zoom", "blackhole")
            cmd = command_with_caffeinate([str(BASE / "record.sh"), session])
            start_process(cmd, kind="record_zoom", title="Запись Zoom", session=session)
            self.send_json({"ok": True, "session": session})
            return
        raise ValueError("Неизвестный режим записи")

    def read_json_body(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def send_html(self, body: str) -> None:
        data = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def send_result_file(self, request_path: str) -> None:
        parts = request_path.split("/")
        if len(parts) != 4 or parts[1] != "files":
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return

        session = unquote(parts[2])
        filename = unquote(parts[3])
        if filename not in {"transcript.txt", "summary.md"}:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return

        root = session_path(session)
        if not root:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        file_path = root / filename
        if not file_path.exists():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "text/plain"
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"UI: http://{HOST}:{PORT}")
    print("Stop: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        with STATE.lock:
            process = STATE.process
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        server.server_close()


if __name__ == "__main__":
    main()
