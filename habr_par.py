import sqlite3
import re
import textwrap
from datetime import datetime
from typing import Optional, List, Dict

import requests
from bs4 import BeautifulSoup, Tag

URL = "https://habr.com/ru/hub/python/articles/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}
DB_NAME = "habr_articles.db"
MAX_ARTICLES = 5
SNIPPET_MAX_LEN = 200

def fetch_page(url: str) -> Optional[BeautifulSoup]:
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        response.encoding = response.apparent_encoding
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as exc:
        print(f"[!] Ошибка при загрузке страницы: {exc}")
        return None

def extract_title(article: Tag) -> Optional[str]:
    title_tag = article.select_one(".tm-article-snippet__title")
    if not title_tag:
        title_tag = article.find("h2")
    return title_tag.get_text(strip=True) if title_tag else None

def extract_date(article: Tag) -> Optional[str]:
    date_tag = article.select_one("time.tm-article-snippet__datetime-published")
    if not date_tag:
        date_tag = article.select_one("time.tm-megapost-snippet__datetime-published")
    if not date_tag:
        date_tag = article.find("time")
    if date_tag:
        dt = date_tag.get("datetime") or date_tag.get_text(strip=True)
        try:
            if dt and "T" in dt:
                dt_obj = datetime.fromisoformat(dt.replace("Z", "+00:00"))
                return dt_obj.strftime("%Y-%m-%d %H:%M")
            return dt.strip() if dt else None
        except (ValueError, TypeError):
            return dt.strip() if dt else None
    return None

def extract_views(article: Tag) -> Optional[int]:
    counters = article.select('.tm-icon-counter__value')
    for counter in counters:
        text = counter.get_text(strip=True).replace('\xa0', '').replace(' ', '')
        if "мин" in text.lower() or "min" in text.lower():
            continue
        if 'k' in text.lower():
            return int(float(text.lower().replace('k', '')) * 1000)
        elif 'm' in text.lower():
            return int(float(text.lower().replace('m', '')) * 1000000)
        else:
            try:
                return int(text)
            except ValueError:
                pass
                
    text_all = article.get_text(" ", strip=True)
    match = re.search(r"([\d\s]+)\s*(?:просмотр|views)", text_all, re.IGNORECASE)
    if match:
        num_str = re.sub(r"\s+", "", match.group(1))
        try:
            return int(num_str)
        except ValueError:
            pass
    return None

def extract_snippet(article: Tag) -> Optional[str]:
    lead_tag = article.select_one(".tm-article-snippet__lead")
    if not lead_tag:
        lead_tag = article.select_one(".tm-article-snippet__body, .tm-article-body, article p")
    if lead_tag:
        snippet = lead_tag.get_text(" ", strip=True)
        if len(snippet) > SNIPPET_MAX_LEN:
            snippet = snippet[:SNIPPET_MAX_LEN].rstrip() + "…"
        return snippet
    return None

def parse_articles(soup: BeautifulSoup, limit: int = MAX_ARTICLES) -> List[Dict]:
    articles = []
    article_tags = soup.select("article.tm-articles-list__item")[:limit]
    if not article_tags:
        print("[!] Не найдено ни одной статьи.")
        return articles
    for idx, art in enumerate(article_tags, start=1):
        title = extract_title(art)
        date = extract_date(art)
        views = extract_views(art)
        snippet = extract_snippet(art)
        if not title:
            continue
        articles.append({"title": title, "date": date, "readings": views, "snippet": snippet})
    return articles

def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL UNIQUE,
            date TEXT,
            readings INTEGER,
            snippet TEXT
        )
        """
    )
    conn.commit()
    return conn

def save_articles(conn: sqlite3.Connection, articles: List[Dict]) -> int:
    cursor = conn.cursor()
    added = 0
    for art in articles:
        try:
            cursor.execute(
                "INSERT INTO articles (title, date, readings, snippet) VALUES (?, ?, ?, ?)",
                (art["title"], art["date"], art["readings"], art["snippet"]),
            )
            added += 1
        except sqlite3.IntegrityError:
            print(f"[i] Пропущена (дубликат): {art['title'][:60]}…")
    conn.commit()
    return added

def print_articles(articles: List[Dict]) -> None:
    if not articles:
        print("Нет данных для отображения.")
        return
    separator = "=" * 80
    print(separator)
    print(f"📰  ПОСЛЕДНИЕ {len(articles)} СТАТЕЙ ИЗ ХАБА PYTHON (Habr.com)")
    print(separator)
    for i, art in enumerate(articles, start=1):
        print(f"\n{i}. {art['title']}")
        print("-" * 80)
        print(f"   📅 Дата публикации : {art['date'] or '—'}")
        print(f"   👁  Просмотры      : {art['readings'] if art['readings'] is not None else '—'}")
        
        prefix = "   📝 Сниппет        : "
        indent = " " * len(prefix)
        snippet_text = art['snippet'] or '—'
        
        formatted_snippet = textwrap.fill(
            snippet_text, 
            width=95, 
            initial_indent=prefix, 
            subsequent_indent=indent
        )
        print(formatted_snippet)
    print("\n" + separator)

def main() -> None:
    print("[*] Загрузка страницы Хабра…")
    soup = fetch_page(URL)
    if soup is None:
        return
    print("[*] Парсинг статей…")
    articles = parse_articles(soup, limit=MAX_ARTICLES)
    print_articles(articles)
    
    print("[*] Подключение к SQLite…")
    try:
        conn = init_db(DB_NAME)
        added = save_articles(conn, articles)
        print(f"[✓] В базу «{DB_NAME}» добавлено новых записей: {added}")
    except sqlite3.Error as exc:
        print(f"[!] Ошибка при работе с БД: {exc}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    main()
