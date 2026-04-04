from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
CONTENT_PATH = DATA_DIR / 'site_content.json'
SUBMISSIONS_PATH = DATA_DIR / 'submissions.jsonl'

ADMIN_ROUTE = '/control-room'
ADMIN_QUESTION = 'Лалка или гей?'
ADMIN_SECRET_ANSWER = os.getenv('ADMIN_SECRET_ANSWER', '').strip()
SITE_URL = os.getenv('SITE_URL', '').strip().rstrip('/')
TURNSTILE_SITE_KEY = os.getenv('TURNSTILE_SITE_KEY', '').strip()
TURNSTILE_SECRET_KEY = os.getenv('TURNSTILE_SECRET_KEY', '').strip()
TURNSTILE_VERIFY_URL = 'https://challenges.cloudflare.com/turnstile/v0/siteverify'
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)

HONEYPOT_FIELD = 'website'
MIN_FORM_SECONDS = 2.0
RATE_LIMIT_WINDOW = 15 * 60
RATE_LIMIT_MAX = 8

ALLOWED_WORK_CATEGORIES = {'event', 'business', 'edu'}
FORM_FIELD_LIMITS = {
    'lead': {
        'name': 120,
        'phone': 80,
        'email': 160,
        'telegram': 80,
        'message': 3000,
    },
    'brief': {
        'goal': 300,
        'audience': 300,
        'format': 120,
        'duration': 120,
        'platform': 200,
        'deadline': 120,
        'refs': 3000,
        'materials': 3000,
        'graphics': 200,
        'revisions': 120,
        'budget': 120,
        'contact': 200,
    },
}

rate_buckets: dict[str, deque[float]] = defaultdict(deque)

app = Flask(__name__, template_folder=str(BASE_DIR / 'templates'))
app.secret_key = os.getenv('FLASK_SECRET_KEY') or os.getenv('SECRET_KEY') or 'change-me-in-production'


def _read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def _ensure_site_content(content: dict[str, Any]) -> None:
    brief = content.setdefault('brief', {})
    brief.setdefault('results_title', 'Что будет после')
    brief.setdefault(
        'results_items',
        [
            'Понятный старт проекта без хаотичной переписки',
            'Оценка сроков, этапов и объёма работ под вашу задачу',
            'Чёткое понимание, что именно нужно снять, собрать и отдать в финале',
        ],
    )

    lead_modal = content.setdefault('lead_modal', {})
    lead_modal.setdefault('kicker', 'Заявка')

    brief_modal = content.setdefault('brief_modal', {})
    brief_modal.setdefault('kicker', 'Бриф')

    work_modal = content.setdefault('work_modal', {})
    work_modal.setdefault('placeholder', 'Видео скоро будет здесь')

    footer = content.setdefault('footer', {})
    footer.setdefault('back_to_top', 'Наверх ↑')


def _load_site_content() -> dict[str, Any]:
    content = json.loads(_read_text(CONTENT_PATH))
    _ensure_site_content(content)
    return content


def _save_site_content(content: dict[str, Any]) -> None:
    _ensure_site_content(content)
    temp_path = CONTENT_PATH.with_suffix('.tmp')
    temp_path.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding='utf-8')
    temp_path.replace(CONTENT_PATH)


def _render_html_file(filename: str, status: int = 200) -> Response:
    html = _read_text(BASE_DIR / filename)
    return Response(html, status=status, mimetype='text/html; charset=utf-8')


def _set_text(node: Any, text: str) -> None:
    if node is None:
        return
    node.clear()
    node.append(text or '')


def _set_meta_name(soup: BeautifulSoup, name: str, value: str) -> None:
    tag = soup.find('meta', attrs={'name': name})
    if tag is None and soup.head is not None:
        tag = soup.new_tag('meta', attrs={'name': name})
        soup.head.append(tag)
    if tag is not None:
        tag['content'] = value


def _set_meta_property(soup: BeautifulSoup, prop: str, value: str) -> None:
    tag = soup.find('meta', attrs={'property': prop})
    if tag is None and soup.head is not None:
        tag = soup.new_tag('meta', attrs={'property': prop})
        soup.head.append(tag)
    if tag is not None:
        tag['content'] = value


def _set_link_rel(soup: BeautifulSoup, rel: str, href: str, **attrs: str) -> None:
    tag = soup.find('link', attrs={'rel': rel})
    if tag is None and soup.head is not None:
        tag = soup.new_tag('link', rel=rel)
        soup.head.append(tag)
    if tag is not None:
        tag['href'] = href
        for key, value in attrs.items():
            tag[key.replace('_', '-')] = value


def _set_meta_http_equiv(soup: BeautifulSoup, key: str, value: str) -> None:
    tag = soup.find('meta', attrs={'http-equiv': key})
    if tag is None and soup.head is not None:
        tag = soup.new_tag('meta', attrs={'http-equiv': key})
        soup.head.append(tag)
    if tag is not None:
        tag['content'] = value


def _phone_href(phone_value: str) -> str:
    digits = ''.join(ch for ch in phone_value if ch.isdigit() or ch == '+')
    return f'tel:{digits}' if digits else '#'


def _email_href(email_value: str) -> str:
    email = email_value.strip()
    return f'mailto:{email}' if email else '#'


def _telegram_href(telegram_value: str) -> str:
    value = telegram_value.strip()
    if not value:
        return '#'
    if value.startswith('http://') or value.startswith('https://'):
        return value
    return f"https://t.me/{value.lstrip('@')}"


def _site_origin() -> str:
    if SITE_URL:
        return SITE_URL
    return request.url_root.rstrip('/')


def _absolute_url(path: str) -> str:
    if path.startswith('http://') or path.startswith('https://'):
        return path
    if path == '/':
        return f'{_site_origin()}/'
    return f"{_site_origin()}/{path.lstrip('/')}"


def _normalize_duration_to_iso(value: str) -> str | None:
    match = re.fullmatch(r'(\d+):(\d{1,2})', value.strip())
    if not match:
        return None
    minutes = int(match.group(1))
    seconds = int(match.group(2))
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f'PT{hours}H{minutes}M{seconds}S'
    return f'PT{minutes}M{seconds}S'


def _ensure_turnstile_script(soup: BeautifulSoup) -> None:
    if not TURNSTILE_ENABLED:
        return
    existing = soup.find(
        'script',
        attrs={'src': lambda value: value and 'challenges.cloudflare.com/turnstile/' in value},
    )
    if existing is not None:
        return

    script = soup.new_tag(
        'script',
        src='https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit',
    )
    script['defer'] = ''
    if soup.body is not None:
        soup.body.append(script)


def _ensure_turnstile_widget(soup: BeautifulSoup, form_id: str, action: str) -> None:
    if not TURNSTILE_ENABLED:
        return

    form = soup.select_one(f'#{form_id}')
    if form is None or form.select_one('[data-turnstile-widget]') is not None:
        return

    wrapper = soup.new_tag('div', attrs={'class': 'form__captcha'})
    widget = soup.new_tag(
        'div',
        attrs={
            'class': 'turnstileWidget',
            'data-turnstile-widget': '1',
            'data-sitekey': TURNSTILE_SITE_KEY,
            'data-action': action,
            'data-theme': 'dark',
        },
    )
    token_input = soup.new_tag(
        'input',
        attrs={
            'type': 'hidden',
            'name': 'cf-turnstile-response',
            'value': '',
        },
    )
    wrapper.append(widget)
    wrapper.append(token_input)

    actions = form.select_one('.form__actions')
    if actions is not None:
        actions.insert_before(wrapper)
    else:
        form.append(wrapper)


def _build_structured_data(content: dict[str, Any], page: str) -> list[dict[str, Any]]:
    footer = content['footer']
    contact = content['contact']
    origin = _site_origin()
    works = content['works']

    organization = {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        'name': footer['brand'],
        'url': f'{origin}/',
        'logo': _absolute_url('static/assets/logo-header.png'),
        'email': contact['email_value'],
        'telephone': contact['phone_value'],
        'sameAs': [_telegram_href(contact['telegram_value'])],
        'contactPoint': [
            {
                '@type': 'ContactPoint',
                'contactType': 'sales',
                'telephone': contact['phone_value'],
                'email': contact['email_value'],
                'availableLanguage': ['ru'],
            }
        ],
    }

    professional_service = {
        '@context': 'https://schema.org',
        '@type': 'ProfessionalService',
        'name': footer['brand'],
        'url': f'{origin}/',
        'image': _absolute_url('static/assets/og-cover.svg'),
        'logo': _absolute_url('static/assets/logo-header.png'),
        'telephone': contact['phone_value'],
        'email': contact['email_value'],
        'sameAs': [_telegram_href(contact['telegram_value'])],
        'serviceType': [
            'Видеопродакшн',
            'Монтаж и постпродакшн',
            'Aftermovie',
            'Бизнес-видео',
            'Обучающие ролики',
        ],
        'areaServed': {
            '@type': 'Country',
            'name': 'Россия',
        },
    }

    if page == 'index':
        website = {
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            'name': footer['brand'],
            'url': f'{origin}/',
            'inLanguage': 'ru-RU',
        }
        return [organization, professional_service, website]

    if page == 'works':
        item_list_elements = []
        for idx, card in enumerate(works['cards'], start=1):
            item = {
                '@type': 'CreativeWork',
                'name': card['title'],
                'description': card['note'],
                'genre': card['tag'],
                'image': _absolute_url('static/assets/showreel_poster.webp'),
                'url': _absolute_url('/works'),
            }
            duration = _normalize_duration_to_iso(card['duration'])
            if duration:
                item['duration'] = duration
            item_list_elements.append(
                {
                    '@type': 'ListItem',
                    'position': idx,
                    'item': item,
                }
            )

        collection_page = {
            '@context': 'https://schema.org',
            '@type': 'CollectionPage',
            'name': works['works_heading'],
            'url': _absolute_url('/works'),
            'inLanguage': 'ru-RU',
            'isPartOf': {
                '@type': 'WebSite',
                'name': footer['brand'],
                'url': f'{origin}/',
            },
            'mainEntity': {
                '@type': 'ItemList',
                'itemListElement': item_list_elements,
            },
        }
        breadcrumb = {
            '@context': 'https://schema.org',
            '@type': 'BreadcrumbList',
            'itemListElement': [
                {
                    '@type': 'ListItem',
                    'position': 1,
                    'name': content['nav']['home'],
                    'item': f'{origin}/',
                },
                {
                    '@type': 'ListItem',
                    'position': 2,
                    'name': works['works_heading'],
                    'item': _absolute_url('/works'),
                },
            ],
        }
        return [organization, professional_service, collection_page, breadcrumb]

    return []


def _apply_jsonld(soup: BeautifulSoup, content: dict[str, Any], page: str) -> None:
    for script in soup.find_all('script', attrs={'type': 'application/ld+json'}):
        script.decompose()

    if soup.head is None:
        return

    for payload in _build_structured_data(content, page):
        script = soup.new_tag('script', attrs={'type': 'application/ld+json'})
        script.string = json.dumps(payload, ensure_ascii=False, indent=2)
        soup.head.append(script)


def _apply_seo(soup: BeautifulSoup, content: dict[str, Any], page: str) -> None:
    seo = content['seo']
    if page == 'index':
        title = seo['index_title']
        description = seo['index_description']
        canonical = _absolute_url('/')
        robots = 'index,follow,max-image-preview:large'
    elif page == 'works':
        title = seo['works_title']
        description = seo['works_description']
        canonical = _absolute_url('/works')
        robots = 'index,follow,max-image-preview:large'
    else:
        title = seo['success_title']
        description = ''
        canonical = _absolute_url('/success')
        robots = 'noindex,follow'

    site_name = content['footer']['brand']
    og_image = _absolute_url('static/assets/og-cover.svg')
    logo_png = _absolute_url('static/assets/logo-header.png')

    if soup.title is not None:
        soup.title.string = title

    if description:
        _set_meta_name(soup, 'description', description)
        _set_meta_property(soup, 'og:description', description)
    _set_meta_property(soup, 'og:title', title)
    _set_meta_property(soup, 'og:url', canonical)
    _set_meta_property(soup, 'og:site_name', site_name)
    _set_meta_property(soup, 'og:image', og_image)
    _set_meta_property(soup, 'og:image:alt', f'{site_name} — видеопродакшн')
    _set_meta_name(soup, 'twitter:title', title)
    _set_meta_name(soup, 'twitter:description', description)
    _set_meta_name(soup, 'twitter:image', og_image)
    _set_meta_name(soup, 'twitter:image:alt', f'{site_name} — видеопродакшн')
    _set_meta_name(soup, 'robots', robots)
    _set_meta_name(soup, 'application-name', site_name)
    _set_meta_name(soup, 'apple-mobile-web-app-title', site_name)
    _set_meta_name(soup, 'format-detection', 'telephone=no')
    _set_meta_http_equiv(soup, 'content-language', 'ru')
    _set_link_rel(soup, 'canonical', canonical)
    _set_link_rel(soup, 'manifest', _absolute_url('/site.webmanifest'))
    _set_link_rel(soup, 'apple-touch-icon', logo_png)
    _set_link_rel(soup, 'icon', _absolute_url('static/assets/favicon.ico'), type='image/x-icon')

    if page != 'success':
        _apply_jsonld(soup, content, page)


def _apply_navigation(soup: BeautifulSoup, content: dict[str, Any], page: str) -> None:
    nav = content['nav']
    contact = content['contact']

    phone_link = soup.select_one('.header__phone')
    if phone_link is not None:
        phone_link['href'] = _phone_href(contact['phone_value'])
        _set_text(phone_link, contact['phone_value'])

    header_icons = soup.select('.header__icons .iconLink')
    if len(header_icons) >= 2:
        header_icons[0]['href'] = _email_href(contact['email_value'])
        header_icons[0]['aria-label'] = contact['email_label']
        header_icons[1]['href'] = _telegram_href(contact['telegram_value'])
        header_icons[1]['aria-label'] = contact['telegram_label']

    for button in soup.select('.header__cta, .mobileNav__leadBtn, .workModal__actions .btn--primary'):
        _set_text(button, nav['discuss_project'])
    for button in soup.select('.mobileNav__briefBtn, .brief__actions .btn, [data-open-modal="briefModal"].btn--primary'):
        if 'header__cta' not in button.get('class', []):
            _set_text(button, nav['fill_brief'])

    nav_links = soup.select('.mobileNav__links a')
    links = [
        ('#top' if page == 'index' else '/', nav['home']),
        ('/works', nav['works']),
        ('#process' if page == 'index' else '/#process', nav['process']),
        ('#contact' if page == 'index' else '/#contact', nav['contact']),
    ]
    for idx, link in enumerate(nav_links[:4]):
        href, text = links[idx]
        link['href'] = href
        _set_text(link, text)
        if page == 'index' and href == '#top':
            link['aria-current'] = 'page'
        elif page == 'works' and href == '/works':
            link['aria-current'] = 'page'
        else:
            link.attrs.pop('aria-current', None)

    logo = soup.select_one('.logo')
    if logo is not None:
        logo['href'] = '#top' if page == 'index' else '/'

def _apply_hero(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    hero = content['hero']

    brand = soup.select_one('.hero__brand')
    if brand is not None:
        brand.clear()
        brand.append(hero['brand_main'])
        brand.append(soup.new_tag('br'))
        accent = soup.new_tag('span', attrs={'class': 'hero__brand-accent'})
        accent.string = hero['brand_accent']
        brand.append(accent)

    typed_wrap = soup.select_one('.hero__typed')
    if typed_wrap is not None:
        typed_wrap.clear()
        typed_wrap.append(f"{hero['typed_prefix']}\xa0")
        typed = soup.new_tag('span', attrs={'class': 'typed', 'data-typed': json.dumps(hero['typed_items'], ensure_ascii=False)})
        typed.string = hero['typed_items'][0] if hero['typed_items'] else ''
        typed_wrap.append(typed)
        cursor = soup.new_tag('span', attrs={'class': 'typed__cursor', 'aria-hidden': 'true'})
        cursor.string = '|'
        typed_wrap.append(cursor)

    _set_text(soup.select_one('.hero__clients-label'), hero['clients_label'])

    logos = soup.select_one('.clientLogos')
    if logos is not None:
        logos.clear()
        for item in hero['clients']:
            logo = soup.new_tag('span', attrs={'class': 'clientLogo'})
            logo.string = item
            logos.append(logo)


def _apply_work_cards(soup: BeautifulSoup, cards: list[dict[str, Any]]) -> None:
    nodes = soup.select('.gridWork .workCard[data-work-title]')
    for node, payload in zip(nodes, cards):
        category = payload.get('category', 'event')
        if category not in ALLOWED_WORK_CATEGORIES:
            category = 'event'

        featured = bool(payload.get('featured'))
        title = payload.get('title', '')
        tag = payload.get('tag', '')
        duration = payload.get('duration', '')
        note = payload.get('note', '')

        node['data-cat'] = category
        node['data-featured'] = '1' if featured else '0'
        node['data-work-title'] = title
        node['data-work-tag'] = tag
        node['data-work-dur'] = duration
        node['data-work-note'] = note
        node['aria-label'] = f'{title} — {duration}' if duration else title

        _set_text(node.select_one('.frameTag'), tag)
        _set_text(node.select_one('.workCard__title'), title)
        _set_text(node.select_one('.workCard__dur'), duration)
        _set_text(node.select_one('.workCard__note'), note)


def _apply_works_section(soup: BeautifulSoup, content: dict[str, Any], page: str) -> None:
    works = content['works']
    heading = soup.select_one('#works .section__head .h1, #works .section__head .h2')
    if heading is not None:
        _set_text(heading, works['works_heading'] if page == 'works' else works['index_heading'])

    tabs = soup.select('#works .worksToolbar .tab')
    if page == 'works':
        tab_content = works['tabs_works']
        keys = ['all', 'event', 'business', 'edu']
    else:
        tab_content = works['tabs_main']
        keys = ['featured', 'event', 'business', 'edu']
    for tab, key in zip(tabs, keys):
        _set_text(tab, tab_content[key])

    cta = soup.select_one('#works .worksToolbar__cta')
    if cta is not None:
        _set_text(cta, works['cta'])

    more = soup.select_one('[data-work-more]')
    if more is not None:
        _set_text(more, works['load_more'])

    _apply_work_cards(soup, works['cards'])


def _apply_suite(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    suite = content['suite']
    _set_text(soup.select_one('.suite__title-main'), suite['heading'])
    paragraphs = soup.select('.suite__text')
    for node, text in zip(paragraphs, suite['paragraphs']):
        _set_text(node, text)


def _apply_process(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    process = content['process']
    _set_text(soup.select_one('#process .section__head .h2'), process['heading'])
    items = soup.select('.processCard')
    for node, item in zip(items, process['items']):
        _set_text(node.select_one('.processCard__step'), item['step'])
        _set_text(node.select_one('.processCard__text'), item['text'])


def _apply_brief(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    brief = content['brief']
    _set_text(soup.select_one('.brief__headline'), brief['heading'])
    _set_text(soup.select_one('.brief__lead'), brief['lead'])
    _set_text(soup.select_one('.brief__actions .btn'), brief['cta'])
    _set_text(soup.select_one('.brief__panelTitle'), brief['panel_title'])
    _set_text(soup.select_one('.brief__resultTitle'), brief['results_title'])

    stats = soup.select('.brief__stat')
    for node, item in zip(stats, brief['stats']):
        _set_text(node.select_one('.brief__statValue'), item['value'])
        _set_text(node.select_one('.brief__statText'), item['text'])

    items = soup.select('.brief__item')
    for node, item in zip(items, brief['items']):
        _set_text(node.select_one('.brief__itemTitle'), item['title'])
        _set_text(node.select_one('.brief__itemText'), item['text'])

    for node, text in zip(soup.select('.brief__resultItem'), brief['results_items']):
        _set_text(node, text)


def _apply_faq(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    faq = content['faq']
    _set_text(soup.select_one('.faqSection__title'), faq['heading'])
    _set_text(soup.select_one('.faqSection__desc'), faq['description'])
    for node, item in zip(soup.select('.faqItem'), faq['items']):
        _set_text(node.select_one('summary span'), item['question'])
        _set_text(node.select_one('.faqItem__a'), item['answer'])


def _apply_contact(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    contact = content['contact']
    _set_text(soup.select_one('#contact .section__head .h2'), contact['heading'])

    items = soup.select('.contactCard__item')
    values = [
        (contact['phone_label'], contact['phone_value'], _phone_href(contact['phone_value'])),
        (contact['email_label'], contact['email_value'], _email_href(contact['email_value'])),
        (contact['telegram_label'], contact['telegram_value'], _telegram_href(contact['telegram_value'])),
        (contact['lead_label'], contact['lead_button'], None),
    ]
    for node, payload in zip(items, values):
        label, value, href = payload
        _set_text(node.select_one('.contactCard__label'), label)
        value_node = node.select_one('.contactCard__value, .btn')
        if value_node is None:
            continue
        _set_text(value_node, value)
        if href and value_node.name == 'a':
            value_node['href'] = href
            if href.startswith('https://t.me/'):
                value_node['target'] = '_blank'
                value_node['rel'] = 'noreferrer'

    tg_float = soup.select_one('.tgFloat')
    if tg_float is not None:
        tg_float['href'] = _telegram_href(contact['telegram_value'])
        tg_float['aria-label'] = f'Написать в {contact["telegram_label"]}'


def _apply_footer(soup: BeautifulSoup, content: dict[str, Any], page: str) -> None:
    footer = content['footer']
    contact = content['contact']

    _set_text(soup.select_one('.footer__brand'), footer['brand'])
    _set_text(soup.select_one('.footer__muted'), footer['copyright'])

    footer_links = soup.select('.footer__links')
    if len(footer_links) >= 3:
        links = footer_links[0].select('a')
        if len(links) >= 2:
            links[0]['href'] = _phone_href(contact['phone_value'])
            _set_text(links[0], contact['phone_value'])
            links[1]['href'] = _email_href(contact['email_value'])
            _set_text(links[1], contact['email_value'])

        tg_link = footer_links[1].select_one('a')
        if tg_link is not None:
            tg_link['href'] = _telegram_href(contact['telegram_value'])
            _set_text(tg_link, footer['telegram_label'])

        top_link = footer_links[2].select_one('a')
        if top_link is not None:
            top_link['href'] = '#top' if page == 'index' else '/'
            _set_text(top_link, footer['back_to_top'])


def _apply_lead_modal(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    modal = content['lead_modal']
    _set_text(soup.select_one('#leadModal .kicker'), modal['kicker'])
    _set_text(soup.select_one('#leadModal .h3'), modal['title'])
    _set_text(soup.select_one('#leadForm button[type="submit"]'), modal['submit'])

    fields = soup.select('#leadForm .field')
    for node, item in zip(fields, modal['fields']):
        _set_text(node.select_one('span'), item['label'])
        field = node.select_one('input, textarea')
        if field is not None:
            field['placeholder'] = item['placeholder']

def _apply_brief_modal(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    modal = content['brief_modal']
    _set_text(soup.select_one('#briefModal .kicker'), modal['kicker'])
    _set_text(soup.select_one('#briefModal .h3'), modal['title'])
    _set_text(soup.select_one('#briefForm button[type="submit"]'), modal['submit'])
    _set_text(soup.select_one('#briefForm .form__hint'), modal['hint'])

    fields = soup.select('#briefForm .field')
    for node, item in zip(fields, modal['fields']):
        _set_text(node.select_one('span'), item['label'])
        field = node.select_one('input, textarea')
        if field is not None:
            field['placeholder'] = item['placeholder']


def _apply_work_modal(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    modal = content['work_modal']
    _set_text(soup.select_one('#workTitle'), modal['title'])
    _set_text(soup.select_one('.workModal__actions .btn--primary'), modal['discuss_button'])
    _set_text(soup.select_one('.workModal__actions .btn--ghost'), modal['close_button'])
    _set_text(soup.select_one('[data-work-fallback]'), modal['placeholder'])


def _apply_success(soup: BeautifulSoup, content: dict[str, Any]) -> None:
    success = content['success']
    if soup.title is not None:
        soup.title.string = content['seo']['success_title']
    _set_text(soup.select_one('.kicker'), success['kicker'])
    _set_text(soup.select_one('.h2'), success['title'])
    _set_text(soup.select_one('.lead'), success['text'])
    _set_text(soup.select_one('.btn'), success['button'])


def _render_public_page(filename: str) -> Response:
    content = _load_site_content()
    soup = BeautifulSoup(_read_text(BASE_DIR / filename), 'html.parser')

    if filename == 'index.html':
        _apply_seo(soup, content, 'index')
        _apply_navigation(soup, content, 'index')
        _apply_hero(soup, content)
        _apply_works_section(soup, content, 'index')
        _apply_suite(soup, content)
        _apply_process(soup, content)
        _apply_brief(soup, content)
        _apply_faq(soup, content)
        _apply_contact(soup, content)
        _apply_footer(soup, content, 'index')
        _apply_lead_modal(soup, content)
        _apply_brief_modal(soup, content)
        _apply_work_modal(soup, content)
    elif filename == 'works.html':
        _apply_seo(soup, content, 'works')
        _apply_navigation(soup, content, 'works')
        _apply_works_section(soup, content, 'works')
        _apply_footer(soup, content, 'works')
        _apply_lead_modal(soup, content)
        _apply_brief_modal(soup, content)
        _apply_work_modal(soup, content)
    elif filename == 'success.html':
        _apply_success(soup, content)

    if filename in {'index.html', 'works.html'}:
        _ensure_turnstile_script(soup)
        _ensure_turnstile_widget(soup, 'leadForm', 'lead')
        _ensure_turnstile_widget(soup, 'briefForm', 'brief')

    return Response(str(soup), mimetype='text/html; charset=utf-8')


def _normalize_answer(value: str) -> str:
    return ' '.join(value.casefold().split())


def _is_admin_authenticated() -> bool:
    return bool(session.get('admin_ok'))


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
    return forwarded or request.remote_addr or 'unknown'


def _is_rate_limited(ip: str) -> bool:
    now = time.time()
    bucket = rate_buckets[ip]
    while bucket and bucket[0] <= now - RATE_LIMIT_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        return True
    bucket.append(now)
    return False


def _clean_text(value: Any, max_length: int | None = None) -> str:
    text = str(value or '').strip()
    text = re.sub(r'\s+', ' ', text)
    if max_length is not None:
        text = text[:max_length]
    return text


def _clean_multiline(value: Any, max_length: int | None = None) -> str:
    text = str(value or '').replace('\r\n', '\n').strip()
    text = re.sub(r'\n{3,}', '\n\n', text)
    if max_length is not None:
        text = text[:max_length]
    return text


def _validate_submission_gate(payload: dict[str, Any]) -> str | None:
    if payload.get(HONEYPOT_FIELD):
        return 'Не удалось отправить форму.'

    raw_ts = str(payload.get('form_ts', '')).strip()
    if raw_ts:
        try:
            elapsed = time.time() - float(raw_ts)
        except ValueError:
            return 'Обновите страницу и попробуйте ещё раз.'
        if elapsed < MIN_FORM_SECONDS:
            return 'Форма отправлена слишком быстро. Попробуйте ещё раз.'

    return None


def _validate_turnstile_token(token: str, expected_action: str) -> str | None:
    if not TURNSTILE_ENABLED:
        return None

    cleaned_token = _clean_text(token, 2048)
    if not cleaned_token:
        return 'Подтвердите, что форму отправляет человек.'

    try:
        response = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                'secret': TURNSTILE_SECRET_KEY,
                'response': cleaned_token,
                'remoteip': _client_ip(),
            },
            timeout=10,
        )
        response.raise_for_status()
        result = response.json()
    except (requests.RequestException, ValueError):
        return 'Не удалось проверить защиту формы. Попробуйте ещё раз.'

    if not result.get('success'):
        error_codes = result.get('error-codes') or []
        if 'timeout-or-duplicate' in error_codes:
            return 'Проверка формы истекла. Обновите её и попробуйте ещё раз.'
        return 'Не удалось проверить защиту формы. Попробуйте ещё раз.'

    if result.get('action') != expected_action:
        return 'Не удалось проверить защиту формы. Обновите страницу и попробуйте ещё раз.'

    return None


def _store_submission(kind: str, payload: dict[str, Any], ip: str) -> None:
    record = {
        'kind': kind,
        'ip': ip,
        'created_at': int(time.time()),
        'payload': payload,
    }
    with SUBMISSIONS_PATH.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + '\n')


def _send_telegram_message(text: str) -> None:
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    if not token or not chat_id:
        return

    try:
        requests.post(
            f'https://api.telegram.org/bot{token}/sendMessage',
            data={'chat_id': chat_id, 'text': text},
            timeout=10,
        ).raise_for_status()
    except requests.RequestException as exc:
        print(f'Telegram send failed: {exc}')


def _format_lead_message(payload: dict[str, str]) -> str:
    return '\n'.join(
        [
            'Новая заявка с сайта',
            f"Имя: {payload['name']}",
            f"Телефон: {payload['phone'] or '—'}",
            f"Email: {payload['email'] or '—'}",
            f"Telegram: {payload['telegram'] or '—'}",
            '',
            'Задача:',
            payload['message'] or '—',
        ]
    )


def _format_brief_message(payload: dict[str, str]) -> str:
    labels = {
        'goal': 'Цель ролика',
        'audience': 'Аудитория',
        'format': 'Формат',
        'duration': 'Длительность',
        'platform': 'Площадка',
        'deadline': 'Сроки',
        'refs': 'Референсы',
        'materials': 'Материалы',
        'graphics': 'Графика/титры',
        'revisions': 'Количество правок',
        'budget': 'Бюджет',
        'contact': 'Контакт',
    }
    lines = ['Новый бриф с сайта', '']
    for key in labels:
        lines.append(f"{labels[key]}: {payload.get(key) or '—'}")
    return '\n'.join(lines)

def _lead_payload_from_request(source: dict[str, Any]) -> dict[str, str]:
    limits = FORM_FIELD_LIMITS['lead']
    return {
        'name': _clean_text(source.get('name'), limits['name']),
        'phone': _clean_text(source.get('phone'), limits['phone']),
        'email': _clean_text(source.get('email'), limits['email']),
        'telegram': _clean_text(source.get('telegram'), limits['telegram']),
        'message': _clean_multiline(source.get('message'), limits['message']),
        'turnstile_token': _clean_text(source.get('cf-turnstile-response'), 2048),
        HONEYPOT_FIELD: _clean_text(source.get(HONEYPOT_FIELD), 200),
        'form_ts': _clean_text(source.get('form_ts'), 100),
    }


def _brief_payload_from_request(source: dict[str, Any]) -> dict[str, str]:
    limits = FORM_FIELD_LIMITS['brief']
    return {
        'goal': _clean_text(source.get('goal'), limits['goal']),
        'audience': _clean_text(source.get('audience'), limits['audience']),
        'format': _clean_text(source.get('format'), limits['format']),
        'duration': _clean_text(source.get('duration'), limits['duration']),
        'platform': _clean_text(source.get('platform'), limits['platform']),
        'deadline': _clean_text(source.get('deadline'), limits['deadline']),
        'refs': _clean_multiline(source.get('refs'), limits['refs']),
        'materials': _clean_multiline(source.get('materials'), limits['materials']),
        'graphics': _clean_text(source.get('graphics'), limits['graphics']),
        'revisions': _clean_text(source.get('revisions'), limits['revisions']),
        'budget': _clean_text(source.get('budget'), limits['budget']),
        'contact': _clean_text(source.get('contact'), limits['contact']),
        'turnstile_token': _clean_text(source.get('cf-turnstile-response'), 2048),
        HONEYPOT_FIELD: _clean_text(source.get(HONEYPOT_FIELD), 200),
        'form_ts': _clean_text(source.get('form_ts'), 100),
    }


def _handle_lead_submission(payload: dict[str, str]) -> str | None:
    error = _validate_submission_gate(payload)
    if error:
        return error
    if not payload['name']:
        return 'Укажите имя.'
    if not any([payload['phone'], payload['email'], payload['telegram']]):
        return 'Оставьте телефон, email или Telegram для связи.'

    ip = _client_ip()
    if _is_rate_limited(ip):
        return 'Слишком много попыток. Попробуйте чуть позже.'

    turnstile_error = _validate_turnstile_token(payload.get('turnstile_token', ''), 'lead')
    if turnstile_error:
        return turnstile_error

    cleaned = {
        key: value
        for key, value in payload.items()
        if key not in {HONEYPOT_FIELD, 'form_ts', 'turnstile_token'}
    }
    _store_submission('lead', cleaned, ip)
    _send_telegram_message(_format_lead_message(cleaned))
    return None


def _handle_brief_submission(payload: dict[str, str]) -> str | None:
    error = _validate_submission_gate(payload)
    if error:
        return error
    if not payload['goal']:
        return 'Укажите цель ролика.'
    if not payload['contact']:
        return 'Оставьте контакт для связи.'

    ip = _client_ip()
    if _is_rate_limited(ip):
        return 'Слишком много попыток. Попробуйте чуть позже.'

    turnstile_error = _validate_turnstile_token(payload.get('turnstile_token', ''), 'brief')
    if turnstile_error:
        return turnstile_error

    cleaned = {
        key: value
        for key, value in payload.items()
        if key not in {HONEYPOT_FIELD, 'form_ts', 'turnstile_token'}
    }
    _store_submission('brief', cleaned, ip)
    _send_telegram_message(_format_brief_message(cleaned))
    return None


def _field(form_data: Any, name: str, max_length: int = 1000) -> str:
    return _clean_multiline(form_data.get(name, ''), max_length)


def _update_admin_content(content: dict[str, Any], form_data: Any) -> None:
    content['seo']['index_title'] = _field(form_data, 'seo_index_title', 200)
    content['seo']['index_description'] = _field(form_data, 'seo_index_description', 500)
    content['seo']['works_title'] = _field(form_data, 'seo_works_title', 200)
    content['seo']['works_description'] = _field(form_data, 'seo_works_description', 500)
    content['seo']['success_title'] = _field(form_data, 'seo_success_title', 200)

    for key in ['home', 'works', 'process', 'contact', 'discuss_project', 'fill_brief']:
        content['nav'][key] = _field(form_data, f'nav_{key}', 200)

    content['hero']['brand_main'] = _field(form_data, 'hero_brand_main', 120)
    content['hero']['brand_accent'] = _field(form_data, 'hero_brand_accent', 120)
    content['hero']['typed_prefix'] = _field(form_data, 'hero_typed_prefix', 120)
    content['hero']['clients_label'] = _field(form_data, 'hero_clients_label', 120)
    content['hero']['typed_items'] = [
        _field(form_data, f'hero_typed_item_{idx}', 120)
        for idx in range(len(content['hero']['typed_items']))
    ]
    content['hero']['clients'] = [
        _field(form_data, f'hero_client_{idx}', 120)
        for idx in range(len(content['hero']['clients']))
    ]

    content['works']['index_heading'] = _field(form_data, 'works_index_heading', 200)
    content['works']['works_heading'] = _field(form_data, 'works_works_heading', 200)
    content['works']['cta'] = _field(form_data, 'works_cta', 120)
    content['works']['load_more'] = _field(form_data, 'works_load_more', 120)

    for key in ['featured', 'event', 'business', 'edu']:
        content['works']['tabs_main'][key] = _field(form_data, f'works_tabs_main_{key}', 120)
    for key in ['all', 'event', 'business', 'edu']:
        content['works']['tabs_works'][key] = _field(form_data, f'works_tabs_works_{key}', 120)

    for idx, card in enumerate(content['works']['cards']):
        card['title'] = _field(form_data, f'works_card_{idx}_title', 200)
        card['tag'] = _field(form_data, f'works_card_{idx}_tag', 120)
        card['duration'] = _field(form_data, f'works_card_{idx}_duration', 120)
        card['note'] = _field(form_data, f'works_card_{idx}_note', 300)
        category = _field(form_data, f'works_card_{idx}_category', 40)
        card['category'] = category if category in ALLOWED_WORK_CATEGORIES else 'event'
        card['featured'] = form_data.get(f'works_card_{idx}_featured') == 'on'

    content['suite']['heading'] = _field(form_data, 'suite_heading', 240)
    content['suite']['paragraphs'] = [
        _field(form_data, f'suite_paragraph_{idx}', 2000)
        for idx in range(len(content['suite']['paragraphs']))
    ]

    content['process']['heading'] = _field(form_data, 'process_heading', 200)
    for idx, item in enumerate(content['process']['items']):
        item['step'] = _field(form_data, f'process_item_{idx}_step', 120)
        item['text'] = _field(form_data, f'process_item_{idx}_text', 1000)

    content['brief']['heading'] = _field(form_data, 'brief_heading', 220)
    content['brief']['lead'] = _field(form_data, 'brief_lead', 3000)
    content['brief']['cta'] = _field(form_data, 'brief_cta', 120)
    content['brief']['panel_title'] = _field(form_data, 'brief_panel_title', 180)
    content['brief']['results_title'] = _field(form_data, 'brief_results_title', 180)
    for idx, item in enumerate(content['brief']['stats']):
        item['value'] = _field(form_data, f'brief_stat_{idx}_value', 120)
        item['text'] = _field(form_data, f'brief_stat_{idx}_text', 300)
    for idx, item in enumerate(content['brief']['items']):
        item['title'] = _field(form_data, f'brief_item_{idx}_title', 180)
        item['text'] = _field(form_data, f'brief_item_{idx}_text', 600)
    content['brief']['results_items'] = [
        _field(form_data, f'brief_result_item_{idx}', 500)
        for idx in range(len(content['brief']['results_items']))
    ]

    content['faq']['heading'] = _field(form_data, 'faq_heading', 200)
    content['faq']['description'] = _field(form_data, 'faq_description', 3000)
    for idx, item in enumerate(content['faq']['items']):
        item['question'] = _field(form_data, f'faq_item_{idx}_question', 220)
        item['answer'] = _field(form_data, f'faq_item_{idx}_answer', 1200)

    for key in ['heading', 'phone_label', 'phone_value', 'email_label', 'email_value', 'telegram_label', 'telegram_value', 'lead_label', 'lead_button']:
        content['contact'][key] = _field(form_data, f'contact_{key}', 220)

    for key in ['brand', 'copyright', 'telegram_label', 'back_to_top']:
        content['footer'][key] = _field(form_data, f'footer_{key}', 220)

    content['lead_modal']['kicker'] = _field(form_data, 'lead_modal_kicker', 120)
    content['lead_modal']['title'] = _field(form_data, 'lead_modal_title', 220)
    content['lead_modal']['submit'] = _field(form_data, 'lead_modal_submit', 120)
    for idx, item in enumerate(content['lead_modal']['fields']):
        item['label'] = _field(form_data, f'lead_modal_field_{idx}_label', 180)
        item['placeholder'] = _field(form_data, f'lead_modal_field_{idx}_placeholder', 220)

    content['brief_modal']['kicker'] = _field(form_data, 'brief_modal_kicker', 120)
    content['brief_modal']['title'] = _field(form_data, 'brief_modal_title', 220)
    content['brief_modal']['submit'] = _field(form_data, 'brief_modal_submit', 120)
    content['brief_modal']['hint'] = _field(form_data, 'brief_modal_hint', 300)
    for idx, item in enumerate(content['brief_modal']['fields']):
        item['label'] = _field(form_data, f'brief_modal_field_{idx}_label', 180)
        item['placeholder'] = _field(form_data, f'brief_modal_field_{idx}_placeholder', 220)

    content['work_modal']['title'] = _field(form_data, 'work_modal_title', 180)
    content['work_modal']['placeholder'] = _field(form_data, 'work_modal_placeholder', 220)
    content['work_modal']['discuss_button'] = _field(form_data, 'work_modal_discuss_button', 120)
    content['work_modal']['close_button'] = _field(form_data, 'work_modal_close_button', 120)

    content['success']['kicker'] = _field(form_data, 'success_kicker', 120)
    content['success']['title'] = _field(form_data, 'success_title', 220)
    content['success']['text'] = _field(form_data, 'success_text', 2000)
    content['success']['button'] = _field(form_data, 'success_button', 120)


def _build_robots_txt() -> str:
    lines = [
        'User-agent: *',
        'Allow: /',
        'Disallow: /control-room',
        'Disallow: /success',
        'Disallow: /api/',
        'Disallow: /lead',
        'Disallow: /brief',
        '',
        f'Sitemap: {_absolute_url("/sitemap.xml")}',
    ]
    return '\n'.join(lines)


def _build_sitemap_xml() -> str:
    entries = [
        ('/', BASE_DIR / 'index.html', 'daily', '1.0'),
        ('/works', BASE_DIR / 'works.html', 'weekly', '0.8'),
    ]
    urls = []
    for path, file_path, changefreq, priority in entries:
        lastmod = time.strftime('%Y-%m-%d', time.localtime(file_path.stat().st_mtime))
        urls.append(
            '\n'.join(
                [
                    '  <url>',
                    f'    <loc>{_absolute_url(path)}</loc>',
                    f'    <lastmod>{lastmod}</lastmod>',
                    f'    <changefreq>{changefreq}</changefreq>',
                    f'    <priority>{priority}</priority>',
                    '  </url>',
                ]
            )
        )
    return '\n'.join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
            *urls,
            '</urlset>',
        ]
    )


@app.get('/')
def home() -> Response:
    return _render_public_page('index.html')


@app.get('/works')
def works_page() -> Response:
    return _render_public_page('works.html')


@app.get('/success')
def success_page() -> Response:
    response = _render_public_page('success.html')
    response.headers['X-Robots-Tag'] = 'noindex, follow'
    return response


@app.get('/robots.txt')
def robots_txt() -> Response:
    return Response(_build_robots_txt(), mimetype='text/plain; charset=utf-8')


@app.get('/sitemap.xml')
def sitemap_xml() -> Response:
    return Response(_build_sitemap_xml(), mimetype='application/xml; charset=utf-8')


@app.get('/site.webmanifest')
def site_webmanifest() -> Response:
    content = _load_site_content()
    footer = content['footer']
    payload = {
        'name': footer['brand'],
        'short_name': footer['brand'],
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#0b0f14',
        'theme_color': '#0b0f14',
        'lang': 'ru',
        'icons': [
            {
                'src': _absolute_url('static/assets/favicon.ico'),
                'sizes': 'any',
                'type': 'image/x-icon',
            }
        ],
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        mimetype='application/manifest+json; charset=utf-8',
    )


@app.route(ADMIN_ROUTE, methods=['GET', 'POST'])
def admin_panel() -> Response | str:
    if not ADMIN_SECRET_ANSWER:
        return Response('ADMIN_SECRET_ANSWER is not configured.', status=500)

    if _is_admin_authenticated():
        return render_template(
            'admin.html',
            content=_load_site_content(),
            admin_route=ADMIN_ROUTE,
            saved=request.args.get('saved') == '1',
        )

    error = ''
    if request.method == 'POST':
        answer = _normalize_answer(request.form.get('answer', ''))
        if answer == _normalize_answer(ADMIN_SECRET_ANSWER):
            session['admin_ok'] = True
            return redirect(url_for('admin_panel'))
        error = 'Неверный ответ.'

    return render_template(
        'admin_login.html',
        admin_route=ADMIN_ROUTE,
        question=ADMIN_QUESTION,
        error=error,
    )


@app.post(f'{ADMIN_ROUTE}/save')
def admin_save() -> Response:
    if not _is_admin_authenticated():
        return redirect(url_for('admin_panel'))

    content = _load_site_content()
    _update_admin_content(content, request.form)
    _save_site_content(content)
    return redirect(url_for('admin_panel', saved=1))


@app.post(f'{ADMIN_ROUTE}/logout')
def admin_logout() -> Response:
    session.clear()
    return redirect(url_for('admin_panel'))


@app.post('/api/lead')
def api_lead() -> Response:
    payload = _lead_payload_from_request(request.get_json(silent=True) or {})
    error = _handle_lead_submission(payload)
    if error:
        return jsonify({'ok': False, 'error': error}), 400
    return jsonify({'ok': True})


@app.post('/lead')
def lead_form() -> Response:
    payload = _lead_payload_from_request(request.form)
    error = _handle_lead_submission(payload)
    if error:
        return redirect(url_for('home'))
    return redirect(url_for('success_page'))


@app.post('/api/brief')
def api_brief() -> Response:
    payload = _brief_payload_from_request(request.get_json(silent=True) or {})
    error = _handle_brief_submission(payload)
    if error:
        return jsonify({'ok': False, 'error': error}), 400
    return jsonify({'ok': True})


@app.post('/brief')
def brief_form() -> Response:
    payload = _brief_payload_from_request(request.form)
    error = _handle_brief_submission(payload)
    if error:
        return redirect(url_for('home'))
    return redirect(url_for('success_page'))


@app.errorhandler(404)
def not_found(_: Any) -> Response:
    response = _render_html_file('404.html', status=404)
    response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


if __name__ == '__main__':
    port = int(os.getenv('PORT', '8000'))
    debug = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
