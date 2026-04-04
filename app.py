from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, send_from_directory

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "static"),
    static_url_path="/static",
)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
_RATE: dict[str, deque[float]] = defaultdict(deque)


def _serve_page(filename: str):
    return send_from_directory(BASE_DIR, filename)


def _normalize_phone(raw: str) -> tuple[str, str]:
    value = (raw or "").strip()
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits, value


def _client_ip() -> str:
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit_ok(limit: int = 10, window_sec: int = 600) -> bool:
    ip = _client_ip()
    queue = _RATE[ip]
    now = time.time()

    while queue and (now - queue[0]) > window_sec:
        queue.popleft()

    if len(queue) >= limit:
        return False

    queue.append(now)
    return True


def _validate_lead(payload: dict[str, str]) -> tuple[bool, str | None]:
    if (payload.get("website") or "").strip():
        return False, "Не удалось отправить. Попробуйте ещё раз."

    try:
        ts = int(str(payload.get("form_ts") or "0"))
    except ValueError:
        ts = 0

    if ts and (time.time() - ts) < 2.0:
        return False, "Не удалось отправить. Попробуйте ещё раз."

    name = (payload.get("name") or "").strip()
    phone_raw = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip()
    message = (payload.get("message") or "").strip()
    telegram = (payload.get("telegram") or "").strip()

    if not name:
        return False, "Укажите имя — так мы поймём, как к вам обращаться."

    if not phone_raw and not email:
        return False, "Укажите телефон или email — чтобы мы могли ответить."

    if email:
        if len(email) > 254:
            return False, "Email слишком длинный."
        if not EMAIL_RE.match(email):
            return False, "Похоже, email указан с ошибкой."

    if phone_raw:
        digits, _ = _normalize_phone(phone_raw)

        if re.search(r"[^\d+\-\s()]", phone_raw):
            return (
                False,
                "Телефон содержит недопустимые символы. Разрешены цифры, пробел, +, -, (, ).",
            )
        if len(digits) < 10:
            return False, "Телефон слишком короткий (нужно минимум 10 цифр)."
        if len(digits) > 15:
            return False, "Телефон слишком длинный (максимум 15 цифр)."

    if telegram:
        if not telegram.startswith("@"):
            return False, "Telegram должен быть в формате @username."
        if len(telegram) < 3 or len(telegram) > 33:
            return False, "Telegram username выглядит подозрительно."
        if not re.fullmatch(r"@[A-Za-z0-9_]+", telegram):
            return False, "В Telegram username допустимы только латиница, цифры и подчёркивание."

    if len(message) > 2000:
        return False, "Сообщение слишком длинное (до 2000 символов)."

    return True, None


def _validate_brief(payload: dict[str, str]) -> tuple[bool, str | None]:
    if (payload.get("website") or "").strip():
        return False, "Не удалось отправить. Попробуйте ещё раз."

    try:
        ts = int(str(payload.get("form_ts") or "0"))
    except ValueError:
        ts = 0

    if ts and (time.time() - ts) < 2.0:
        return False, "Не удалось отправить. Попробуйте ещё раз."

    goal = (payload.get("goal") or "").strip()
    contact = (payload.get("contact") or "").strip()

    if not goal:
        return False, "Укажите цель ролика."
    if not contact:
        return False, "Укажите контакт для связи."
    if len(contact) < 3:
        return False, "Контакт выглядит слишком коротким."

    for key in (
        "goal",
        "audience",
        "format",
        "duration",
        "platform",
        "deadline",
        "refs",
        "materials",
        "graphics",
        "revisions",
        "budget",
        "contact",
    ):
        if len((payload.get(key) or "").strip()) > 2000:
            return False, "Поле слишком длинное. Укоротите текст."

    return True, None


def _notify_telegram(payload: dict[str, str]) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    text = (
        "🎬 Новая заявка\n\n"
        f"Имя: {payload.get('name') or '—'}\n"
        f"Телефон: {payload.get('phone') or '—'}\n"
        f"Email: {payload.get('email') or '—'}\n"
        f"Telegram: {payload.get('telegram') or '—'}\n"
        f"Сообщение:\n{payload.get('message') or '—'}"
    )
    _send_telegram_message(text)


def _notify_telegram_brief(payload: dict[str, str]) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    text = (
        "📝 Новый бриф\n\n"
        f"Цель: {payload.get('goal') or '—'}\n"
        f"Аудитория: {payload.get('audience') or '—'}\n"
        f"Формат: {payload.get('format') or '—'}\n"
        f"Длительность: {payload.get('duration') or '—'}\n"
        f"Площадка: {payload.get('platform') or '—'}\n"
        f"Сроки: {payload.get('deadline') or '—'}\n"
        f"Референсы: {payload.get('refs') or '—'}\n"
        f"Материалы: {payload.get('materials') or '—'}\n"
        f"Графика/титры: {payload.get('graphics') or '—'}\n"
        f"Правки: {payload.get('revisions') or '—'}\n"
        f"Бюджет: {payload.get('budget') or '—'}\n"
        f"Контакт: {payload.get('contact') or '—'}"
    )
    _send_telegram_message(text)


def _send_telegram_message(text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=6,
        )
    except Exception:
        pass


def _lead_payload_from_form() -> dict[str, str]:
    return {
        "name": (request.form.get("name") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "telegram": (request.form.get("telegram") or "").strip(),
        "message": (request.form.get("message") or "").strip(),
        "website": (request.form.get("website") or "").strip(),
        "form_ts": (request.form.get("form_ts") or "").strip(),
    }


def _brief_payload_from_form() -> dict[str, str]:
    return {
        "goal": (request.form.get("goal") or "").strip(),
        "audience": (request.form.get("audience") or "").strip(),
        "format": (request.form.get("format") or "").strip(),
        "duration": (request.form.get("duration") or "").strip(),
        "platform": (request.form.get("platform") or "").strip(),
        "deadline": (request.form.get("deadline") or "").strip(),
        "refs": (request.form.get("refs") or "").strip(),
        "materials": (request.form.get("materials") or "").strip(),
        "graphics": (request.form.get("graphics") or "").strip(),
        "revisions": (request.form.get("revisions") or "").strip(),
        "budget": (request.form.get("budget") or "").strip(),
        "contact": (request.form.get("contact") or "").strip(),
        "website": (request.form.get("website") or "").strip(),
        "form_ts": (request.form.get("form_ts") or "").strip(),
    }


def _lead_payload_from_json() -> dict[str, str]:
    data: dict[str, Any] = request.get_json(silent=True) or {}
    return {
        "name": str(data.get("name") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "email": str(data.get("email") or "").strip(),
        "telegram": str(data.get("telegram") or "").strip(),
        "message": str(data.get("message") or "").strip(),
        "website": str(data.get("website") or "").strip(),
        "form_ts": str(data.get("form_ts") or "").strip(),
    }


def _brief_payload_from_json() -> dict[str, str]:
    data: dict[str, Any] = request.get_json(silent=True) or {}
    return {
        "goal": str(data.get("goal") or "").strip(),
        "audience": str(data.get("audience") or "").strip(),
        "format": str(data.get("format") or "").strip(),
        "duration": str(data.get("duration") or "").strip(),
        "platform": str(data.get("platform") or "").strip(),
        "deadline": str(data.get("deadline") or "").strip(),
        "refs": str(data.get("refs") or "").strip(),
        "materials": str(data.get("materials") or "").strip(),
        "graphics": str(data.get("graphics") or "").strip(),
        "revisions": str(data.get("revisions") or "").strip(),
        "budget": str(data.get("budget") or "").strip(),
        "contact": str(data.get("contact") or "").strip(),
        "website": str(data.get("website") or "").strip(),
        "form_ts": str(data.get("form_ts") or "").strip(),
    }


@app.get("/")
def index():
    return _serve_page("index.html")


@app.get("/works")
def works():
    return _serve_page("works.html")


@app.get("/success")
def success():
    return _serve_page("success.html")


@app.post("/lead")
def lead_form_post():
    if not _rate_limit_ok():
        return _serve_page("index.html"), 429

    payload = _lead_payload_from_form()
    ok, _error = _validate_lead(payload)
    if not ok:
        return _serve_page("index.html"), 400

    _notify_telegram(payload)
    return redirect("/success")


@app.post("/brief")
def brief_form_post():
    if not _rate_limit_ok():
        return _serve_page("index.html"), 429

    payload = _brief_payload_from_form()
    ok, _error = _validate_brief(payload)
    if not ok:
        return _serve_page("index.html"), 400

    _notify_telegram_brief(payload)
    return redirect("/success")


@app.post("/api/lead")
def api_lead():
    if not _rate_limit_ok():
        return jsonify({"ok": False, "error": "Слишком часто. Попробуйте чуть позже."}), 429

    payload = _lead_payload_from_json()
    ok, error = _validate_lead(payload)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400

    _notify_telegram(payload)
    return jsonify({"ok": True})


@app.post("/api/brief")
def api_brief():
    if not _rate_limit_ok():
        return jsonify({"ok": False, "error": "Слишком часто. Попробуйте чуть позже."}), 429

    payload = _brief_payload_from_json()
    ok, error = _validate_brief(payload)
    if not ok:
        return jsonify({"ok": False, "error": error}), 400

    _notify_telegram_brief(payload)
    return jsonify({"ok": True})


@app.errorhandler(404)
def page_not_found(_error):
    return _serve_page("404.html"), 404


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
