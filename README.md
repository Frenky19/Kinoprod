# EVA site

Сайт обслуживается Flask-приложением, но сам фронтенд хранится в корне репозитория:

- `index.html` — основная страница
- `success.html` — страница успешной отправки
- `404.html` — страница 404
- `static/` — CSS, JS и ассеты

Формы отправляются в Flask API:

- `POST /api/lead`
- `POST /api/brief`

Обычные HTML-post fallback-маршруты тоже есть:

- `POST /lead`
- `POST /brief`

## Локальный запуск

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Открыть:

```text
http://127.0.0.1:5000
```

## Что важно

- Telegram-уведомления читаются из `.env`
- Flask теперь обслуживает актуальный root frontend, а не отдельную версию из `templates/`
- Если меняется hero/video-ассет, обновляй ссылки в `index.html`
