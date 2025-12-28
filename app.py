from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, url_for

load_dotenv()

app = Flask(__name__)


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

BRAND = {
    "name": "KINO",
    "tagline": "Видеопродакшн полного цикла",
    "city": "Москва",
    "phone": "+7 925 603-53-11",
    "email": "kino_prod@gmail.com",
    "social": {
        "telegram": "https://t.me/molodoyeg",
        "youtube": "#",
    },
}

BENEFITS = [
    {
        "title": "Единая команда под любой проект",
        "text": "Продюсер, оператор, звук, монтаж, графика — в одном процессе без «сборной солянки».",
    },
    {
        "title": "Гибкие форматы и сроки",
        "text": "От быстрых роликов для соцсетей до постановочных проектов со сценарием и подготовкой.",
    },
    {
        "title": "От съёмки до готового ролика",
        "text": "Бриф → план → съёмка → монтаж → графика → финальные версии под нужные площадки.",
    },
]

WORK_CATEGORIES = [
    {"key": "event", "title": "Мероприятия", "desc": "Свадьбы, юбилеи, корпоративы, конференции."},
    {"key": "business", "title": "Бизнес-видео", "desc": "Реклама, презентации, контент для соцсетей."},
    {"key": "edu", "title": "Образовательный контент", "desc": "Лекции, курсы, вебинары — чисто и понятно."},
]

PROJECTS = [
    {"title": "Aftermovie конференции", "cat": "event", "duration": "1:20", "note": "репортаж + динамичный монтаж", "video_url": "#"},
    {"title": "Свадебный клип", "cat": "event", "duration": "3:10", "note": "эмоции + детали", "video_url": "#"},
    {"title": "Рекламный ролик продукта", "cat": "business", "duration": "0:30", "note": "акцент на УТП", "video_url": "#"},
    {"title": "Презентация сервиса", "cat": "business", "duration": "1:05", "note": "структура + графика", "video_url": "#"},
    {"title": "Запись лекции", "cat": "edu", "duration": "45:00", "note": "чистый звук + титры", "video_url": "#"},
    {"title": "Онлайн-курс (урок)", "cat": "edu", "duration": "12:00", "note": "экран + камера", "video_url": "#"},
]

PRICING = {
    "event": {
        "title": "Съёмка мероприятий",
        "subtitle": "Свадьбы, корпоративы, конференции. Пакеты можно комбинировать.",
        "items": [
            {"name": "Клип-фильм", "price": "15 000 ₽", "desc": "Эмоциональный видеорассказ о событии."},
            {"name": "Тизер", "price": "8 000 ₽", "desc": "Короткий ролик для анонса в соцсетях."},
            {"name": "Полный репортаж", "price": "25 000 ₽", "desc": "Запись ключевых моментов + монтаж."},
        ],
    },
    "business": {
        "title": "Коммерческое видео",
        "subtitle": "Реклама, презентации, контент для соцсетей. Под бизнес-цели.",
        "items": [
            {"name": "Рекламный ролик", "price": "15 000 ₽", "desc": "Яркое видео для продвижения."},
            {"name": "Видео для соцсетей", "price": "8 000 ₽", "desc": "Reels/TikTok/Shorts под ваш стиль."},
            {"name": "Имиджевое видео", "price": "18 000 ₽", "desc": "Про бренд, доверие и узнаваемость."},
        ],
    },
    "edu": {
        "title": "Образовательный контент",
        "subtitle": "Лекции, семинары, курсы — с чистым звуком и аккуратной подачей.",
        "items": [
            {"name": "Запись лекции", "price": "10 000 ₽", "desc": "Камера + звук + базовая графика."},
            {"name": "Вебинар", "price": "8 000 ₽", "desc": "Запись + помощь с подготовкой сцены."},
            {"name": "Онлайн-курс (урок)", "price": "15 000 ₽", "desc": "Структура + съёмка + монтаж."},
        ],
    },
}

PROCESS = [
    {"step": "01", "title": "Бриф и цель", "text": "Понимаем задачу, аудиторию и площадки. Фиксируем результат."},
    {"step": "02", "title": "Концепт и план", "text": "Предлагаем идею/структуру, план съёмки. Согласуем сроки и бюджет."},
    {"step": "03", "title": "Съёмка", "text": "Операторская работа, свет и звук. Аккуратно и без хаоса."},
    {"step": "04", "title": "Монтаж и графика", "text": "Монтаж, цвет, звук, титры/инфографика. Версии под разные форматы."},
    {"step": "05", "title": "Сдача", "text": "Финальные файлы и поддержка публикации по договорённости."},
]


# Helpers
def _index_context() -> dict[str, Any]:
    return dict(
        brand=BRAND,
        benefits=BENEFITS,
        work_categories=WORK_CATEGORIES,
        projects=PROJECTS,
        pricing=PRICING,
        process=PROCESS,
        form_ts=int(time.time()),  # anti-spam timestamp
    )


EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")


def _normalize_phone(raw: str) -> tuple[str, str]:
    s = (raw or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits, s


_RATE: dict[str, deque[float]] = defaultdict(deque)


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _rate_limit_ok(limit: int = 10, window_sec: int = 600) -> bool:
    ip = _client_ip()
    q = _RATE[ip]
    now = time.time()

    while q and (now - q[0]) > window_sec:
        q.popleft()

    if len(q) >= limit:
        return False

    q.append(now)
    return True


def _validate_lead(payload: dict[str, str]) -> tuple[bool, str | None]:
    if (payload.get("website") or "").strip():
        return False, "Не удалось отправить. Попробуйте ещё раз."
    try:
        ts = int(str(payload.get("form_ts") or "0"))
    except ValueError:
        ts = 0
    if ts:
        if (time.time() - ts) < 2.0:
            return False, "Не удалось отправить. Попробуйте ещё раз."
    name = (payload.get("name") or "").strip()
    phone_raw = (payload.get("phone") or "").strip()
    email = (payload.get("email") or "").strip()
    msg = (payload.get("message") or "").strip()
    tg = (payload.get("telegram") or "").strip()
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
        digits, _pretty = _normalize_phone(phone_raw)

        if re.search(r"[^\d+\-\s()]", phone_raw):
            return False, "Телефон содержит недопустимые символы. Разрешены цифры, пробел, +, -, (, )."
        if len(digits) < 10:
            return False, "Телефон слишком короткий (нужно минимум 10 цифр)."
        if len(digits) > 15:
            return False, "Телефон слишком длинный (максимум 15 цифр)."
    if tg:
        if not tg.startswith("@"):
            return False, "Telegram должен быть в формате @username."
        if len(tg) < 3 or len(tg) > 33:
            return False, "Telegram username выглядит подозрительно."
        if not re.fullmatch(r"@[A-Za-z0-9_]+", tg):
            return False, "В Telegram username допустимы только латиница, цифры и подчёркивание."
    if len(msg) > 2000:
        return False, "Сообщение слишком длинное (до 2000 символов)."
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


# Routes
@app.get("/")
def index():
    return render_template("index.html", **_index_context())


@app.get("/success")
def success():
    return render_template("success.html", brand=BRAND)


@app.post("/lead")
def lead_form_post():
    if not _rate_limit_ok():
        return render_template("index.html", error="Слишком часто. Попробуйте чуть позже.", **_index_context()), 429

    payload = {
        "name": (request.form.get("name") or "").strip(),
        "phone": (request.form.get("phone") or "").strip(),
        "email": (request.form.get("email") or "").strip(),
        "telegram": (request.form.get("telegram") or "").strip(),
        "message": (request.form.get("message") or "").strip(),
        # anti-spam fields
        "website": (request.form.get("website") or "").strip(),
        "form_ts": (request.form.get("form_ts") or "").strip(),
    }
    ok, err = _validate_lead(payload)
    if not ok:
        return render_template("index.html", error=err, **_index_context()), 400
    _notify_telegram(payload)
    return redirect(url_for("success"))


@app.post("/api/lead")
def api_lead():
    if not _rate_limit_ok():
        return jsonify({"ok": False, "error": "Слишком часто. Попробуйте чуть позже."}), 429
    data: dict[str, Any] = request.get_json(silent=True) or {}
    payload = {
        "name": str(data.get("name") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "email": str(data.get("email") or "").strip(),
        "telegram": str(data.get("telegram") or "").strip(),
        "message": str(data.get("message") or "").strip(),
        # anti-spam fields
        "website": str(data.get("website") or "").strip(),
        "form_ts": str(data.get("form_ts") or "").strip(),
    }
    ok, err = _validate_lead(payload)
    if not ok:
        return jsonify({"ok": False, "error": err}), 400
    _notify_telegram(payload)
    return jsonify({"ok": True})


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="127.0.0.1", port=port, debug=debug)
