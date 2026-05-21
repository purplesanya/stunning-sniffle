import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, url_for

from flibusta_utils import (
    ALLOWED_FORMATS,
    download_books_to_disk,
    download_single_book,
    fetch_recommendations,
    find_books,
    get_author_profile,
    get_author_name,
    get_book_details,
    search_authors,
    search_books,
    validate_download_link,
)

app = Flask(__name__)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

CACHE_DURATION = timedelta(hours=1)
MAX_CACHE_ITEMS = 256
JOB_TTL_SECONDS = 60 * 60
MAX_BULK_BOOKS = 1000

cache = {}
CACHE_LOCK = threading.Lock()
JOBS = {}
JOBS_LOCK = threading.Lock()

LANGUAGES = {"en", "ru"}
TRANSLATIONS = {
    "en": {
        "app_name": "FLoader",
        "topbar_note": "For books you are allowed to download",
        "go_search": "Go to search",
        "search_title": "Search - FLoader",
        "search_eyebrow": "Book and author search",
        "search_heading": "Find a book, choose formats, download cleanly.",
        "search_lead": "Search by author or title. Results split authors and direct book matches so you can move quickly.",
        "search_label": "Search query",
        "search_placeholder": "Author name or book title",
        "search_button": "Search",
        "search_hint": "Tip: press",
        "search_hint_tail": "anywhere on this page to focus search.",
        "searching": "Searching...",
        "results_title": "Results - FLoader",
        "results_eyebrow": "Search results",
        "results_for": "Results for",
        "also_searched": "Also searched",
        "new_search": "New Search",
        "authors": "Authors",
        "books": "Books",
        "view_books": "View books",
        "no_author_matches": "No author matches.",
        "no_book_matches": "No direct book matches.",
        "no_results": "No results found",
        "no_results_hint": "Try another spelling, a shorter author name, or a book title fragment.",
        "search_again": "Search Again",
        "books_title": "Books - FLoader",
        "author_library": "Author library",
        "books_found_note": "{count} books found. Single selections download as files; multiple selections download as ZIP.",
        "back_to_search": "Back to Search",
        "filter_titles": "Filter titles",
        "filter_placeholder": "Type to narrow this author...",
        "book_format": "Book format",
        "selected": "selected",
        "select_visible": "Select Visible",
        "clear": "Clear",
        "preparing_download": "Preparing download...",
        "no_books_match": "No books match this view",
        "no_books_match_hint": "Try another format or clear the title filter.",
        "choose_books": "Choose books to download",
        "format_selected": "{format} format selected",
        "download": "Download",
        "book_selected": "book selected",
        "books_selected": "books selected",
        "selected_count": "{count} selected",
        "single_file_output": "single file output",
        "zip_output": "ZIP archive output",
        "no_valid_selection_title": "No valid selection",
        "no_valid_selection_message": "Select at least one visible book in the chosen format.",
        "starting_download": "Starting download...",
        "download_started_title": "Download started",
        "download_started_message": "Preparing your selection.",
        "download_ready_title": "Download ready",
        "download_ready_message": "Your file is ready.",
        "download_failed_title": "Download failed",
        "download_failed_message": "Could not start download.",
        "processing": "Processing...",
        "downloaded": "Downloaded {done}/{total}",
        "archiving": "Archiving {done}/{total}",
        "invalid_author": "Invalid author ID",
        "load_books_error": "Error loading books",
        "empty_query": "Please enter a search query.",
        "search_error": "An error occurred during the search. Please try again.",
        "page_not_found": "Page not found",
        "server_error": "An internal error occurred",
        "selected_author": "Selected Author",
        "nav_search": "Search",
        "nav_recommendations": "Recommendations",
        "nav_bookmarks": "Bookmarks",
        "recommendations_title": "Recommendations - FLoader",
        "recommendations_eyebrow": "Community recommendations",
        "recommendations_heading": "Books people are recommending now.",
        "recommendations_lead": "Parsed from Flibusta community recommendation pages and cached for a short time.",
        "recommended_books": "Recommended books",
        "recent_recommendations": "Recent recommendations",
        "recommended_by": "Recommended by",
        "open_book": "Open book",
        "bookmark": "Bookmark",
        "bookmarked": "Bookmarked",
        "remove_bookmark": "Remove",
        "bookmarks_title": "Bookmarks - FLoader",
        "bookmarks_eyebrow": "Saved locally",
        "bookmarks_heading": "Bookmarks",
        "bookmarks_lead": "Saved in this browser only, so they stay private and do not need a login.",
        "no_bookmarks": "No bookmarks yet",
        "no_bookmarks_hint": "Add books from recommendations, search results, or an author page.",
        "recommendations_error": "Could not load recommendations right now.",
        "unknown_author": "Unknown author",
        "author_biography": "Author biography",
        "no_author_bio": "No biography was found on the author page.",
        "book_description": "Description",
        "loading_description": "Loading description...",
        "no_book_description": "No description found on Flibusta.",
        "download_formats": "Download",
        "details_failed": "Details unavailable",
        "preferred_download": "Download",
        "show_more": "Show more",
        "show_less": "Show less",
        "details": "Details",
        "close": "Close",
    },
    "ru": {
        "app_name": "FLoader",
        "topbar_note": "Для книг, которые вы имеете право скачивать",
        "go_search": "Перейти к поиску",
        "search_title": "Поиск - FLoader",
        "search_eyebrow": "Поиск книг и авторов",
        "search_heading": "Найдите книгу, выберите формат и скачайте без лишнего.",
        "search_lead": "Ищите по автору или названию. Результаты отдельно показывают авторов и найденные книги.",
        "search_label": "Поисковый запрос",
        "search_placeholder": "Автор или название книги",
        "search_button": "Искать",
        "search_hint": "Подсказка: нажмите",
        "search_hint_tail": "на этой странице, чтобы перейти к поиску.",
        "searching": "Ищем...",
        "results_title": "Результаты - FLoader",
        "results_eyebrow": "Результаты поиска",
        "results_for": "Результаты для",
        "also_searched": "Также искали",
        "new_search": "Новый поиск",
        "authors": "Авторы",
        "books": "Книги",
        "view_books": "Открыть книги",
        "no_author_matches": "Авторы не найдены.",
        "no_book_matches": "Книги напрямую не найдены.",
        "no_results": "Ничего не найдено",
        "no_results_hint": "Попробуйте другое написание, более короткое имя автора или часть названия.",
        "search_again": "Искать снова",
        "books_title": "Книги - FLoader",
        "author_library": "Книги автора",
        "books_found_note": "Найдено книг: {count}. Одна выбранная книга скачивается файлом; несколько книг скачиваются ZIP-архивом.",
        "back_to_search": "Назад к поиску",
        "filter_titles": "Фильтр по названию",
        "filter_placeholder": "Введите часть названия...",
        "book_format": "Формат книги",
        "selected": "выбрано",
        "select_visible": "Выбрать видимые",
        "clear": "Сбросить",
        "preparing_download": "Готовим скачивание...",
        "no_books_match": "В этом режиме книг нет",
        "no_books_match_hint": "Выберите другой формат или очистите фильтр.",
        "choose_books": "Выберите книги для скачивания",
        "format_selected": "Выбран формат {format}",
        "download": "Скачать",
        "book_selected": "книга выбрана",
        "books_selected": "книг выбрано",
        "selected_count": "Выбрано: {count}",
        "single_file_output": "скачается одним файлом",
        "zip_output": "скачается ZIP-архивом",
        "no_valid_selection_title": "Нет выбранных книг",
        "no_valid_selection_message": "Выберите хотя бы одну видимую книгу в выбранном формате.",
        "starting_download": "Запускаем скачивание...",
        "download_started_title": "Скачивание начато",
        "download_started_message": "Готовим выбранные книги.",
        "download_ready_title": "Файл готов",
        "download_ready_message": "Скачивание должно начаться автоматически.",
        "download_failed_title": "Не удалось скачать",
        "download_failed_message": "Не удалось запустить скачивание.",
        "processing": "Обработка...",
        "downloaded": "Скачано {done}/{total}",
        "archiving": "Архивируем {done}/{total}",
        "invalid_author": "Неверный ID автора",
        "load_books_error": "Не удалось загрузить книги",
        "empty_query": "Введите поисковый запрос.",
        "search_error": "Во время поиска произошла ошибка. Попробуйте еще раз.",
        "page_not_found": "Страница не найдена",
        "server_error": "Внутренняя ошибка сервера",
        "selected_author": "Выбранный автор",
        "nav_search": "Поиск",
        "nav_recommendations": "Рекомендации",
        "nav_bookmarks": "Закладки",
        "recommendations_title": "Рекомендации - FLoader",
        "recommendations_eyebrow": "Рекомендации сообщества",
        "recommendations_heading": "Книги, которые сейчас рекомендуют.",
        "recommendations_lead": "Список берется со страниц рекомендаций Flibusta и ненадолго кешируется.",
        "recommended_books": "Рекомендуемые книги",
        "recent_recommendations": "Свежие рекомендации",
        "recommended_by": "Рекомендует",
        "open_book": "Открыть книгу",
        "bookmark": "В закладки",
        "bookmarked": "В закладках",
        "remove_bookmark": "Удалить",
        "bookmarks_title": "Закладки - FLoader",
        "bookmarks_eyebrow": "Сохранено локально",
        "bookmarks_heading": "Закладки",
        "bookmarks_lead": "Закладки хранятся только в этом браузере, без логина и сервера.",
        "no_bookmarks": "Закладок пока нет",
        "no_bookmarks_hint": "Добавляйте книги из рекомендаций, результатов поиска или страницы автора.",
        "recommendations_error": "Сейчас не удалось загрузить рекомендации.",
        "unknown_author": "Автор неизвестен",
        "author_biography": "Биография автора",
        "no_author_bio": "На странице автора биография не найдена.",
        "book_description": "Описание",
        "loading_description": "Загружаем описание...",
        "no_book_description": "На Flibusta описание не найдено.",
        "download_formats": "Скачать",
        "details_failed": "Детали недоступны",
        "preferred_download": "Скачать",
        "show_more": "Показать полностью",
        "show_less": "Свернуть",
        "details": "Подробнее",
        "close": "Закрыть",
    },
}

EN_TO_RU_LAYOUT = str.maketrans(
    "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~",
    "йцукенгшщзхъфывапролджэячсмитьбюёйцукенгшщзхъфывапролджэячсмитьбюЁ",
)
RU_TO_EN_LAYOUT = str.maketrans(
    "йцукенгшщзхъфывапролджэячсмитьбюёЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ",
    "qwertyuiop[]asdfghjkl;'zxcvbnm,.`QWERTYUIOP{}ASDFGHJKL:\"ZXCVBNM<>~",
)


@app.route("/favicon.ico")
def favicon():
    return send_file(Path(app.root_path) / "icon.ico", mimetype="image/vnd.microsoft.icon")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


def get_lang():
    explicit_lang = request.values.get("lang") or request.cookies.get("app_lang")
    if explicit_lang in LANGUAGES:
        return explicit_lang

    best_match = request.accept_languages.best_match(["ru", "en"])
    return best_match if best_match in LANGUAGES else "en"


def translate(key, **kwargs):
    lang = get_lang()
    text = TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def lang_url(endpoint=None, **values):
    endpoint = endpoint or request.endpoint or "index"
    merged = dict(request.view_args or {})
    merged.update(values)
    merged["lang"] = values.get("lang", get_lang())
    return url_for(endpoint, **merged)


@app.context_processor
def inject_i18n():
    lang = get_lang()
    other_lang = "ru" if lang == "en" else "en"
    return {
        "t": translate,
        "lang": lang,
        "other_lang": other_lang,
        "lang_url": lang_url,
    }


@app.after_request
def persist_language(response):
    lang = request.values.get("lang")
    if lang in LANGUAGES:
        response.set_cookie("app_lang", lang, max_age=60 * 60 * 24 * 365, samesite="Lax")
    return response


def _now():
    return datetime.now()


def cleanup_cache():
    cutoff = _now() - CACHE_DURATION
    expired_keys = [key for key, (_, timestamp) in cache.items() if timestamp < cutoff]
    for key in expired_keys:
        cache.pop(key, None)

    if len(cache) > MAX_CACHE_ITEMS:
        oldest_keys = sorted(cache, key=lambda key: cache[key][1])
        for key in oldest_keys[: len(cache) - MAX_CACHE_ITEMS]:
            cache.pop(key, None)


def get_cached(key):
    with CACHE_LOCK:
        cleanup_cache()
        cached = cache.get(key)
        if not cached:
            return None
        value, timestamp = cached
        if _now() - timestamp >= CACHE_DURATION:
            cache.pop(key, None)
            return None
        return value


def set_cached(key, value):
    with CACHE_LOCK:
        cleanup_cache()
        cache[key] = (value, _now())


def cleanup_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    expired = []
    with JOBS_LOCK:
        for job_id, job in JOBS.items():
            updated_at = job.get("updated_at") or job.get("created_at") or 0
            if updated_at < cutoff:
                expired.append((job_id, job.get("output_path")))
        for job_id, _ in expired:
            JOBS.pop(job_id, None)

    for _, output_path in expired:
        if not output_path:
            continue
        try:
            Path(output_path).unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to remove expired download output: %s", output_path, exc_info=True)


def public_job_status(job):
    public_keys = {"status", "progress", "message", "filename", "download_token"}
    return {key: value for key, value in job.items() if key in public_keys}


def is_valid_id(value):
    return bool(value) and str(value).isdigit()


def get_format_counts(books_list):
    counts = {file_format: 0 for file_format in ALLOWED_FORMATS}
    for book in books_list:
        for file_format in book.get("links", {}):
            if file_format in counts:
                counts[file_format] += 1
    return counts


def keyboard_layout_variants(query):
    variants = []
    for candidate in (query, query.translate(EN_TO_RU_LAYOUT), query.translate(RU_TO_EN_LAYOUT)):
        candidate = candidate.strip()
        if candidate and candidate.casefold() not in {value.casefold() for value in variants}:
            variants.append(candidate)
            for fuzzy_candidate in fuzzy_russian_variants(candidate):
                if fuzzy_candidate.casefold() not in {value.casefold() for value in variants}:
                    variants.append(fuzzy_candidate)
    return variants


def fuzzy_russian_variants(query):
    if not any("а" <= char.casefold() <= "я" or char.casefold() == "ё" for char in query):
        return []
    lowered = query.casefold()
    variants = []
    if lowered.endswith("вн"):
        variants.append(f"{query[:-1]}ин")
    return variants


def merge_authors(existing, incoming):
    seen = {author_id for _, author_id in existing}
    for name, author_id in incoming:
        if author_id not in seen:
            existing.append((name, author_id))
            seen.add(author_id)
    return existing


def merge_books(existing, incoming):
    seen = {book.get("book_id") for book in existing}
    for book in incoming:
        book_id = book.get("book_id")
        if book_id not in seen:
            existing.append(book)
            seen.add(book_id)
    return existing


def cached_author_search(query):
    normalized_query = query.casefold()
    authors = get_cached(f"author_search:{normalized_query}")
    if authors is None:
        authors = search_authors(query)
        set_cached(f"author_search:{normalized_query}", authors)
    return authors


def cached_book_search(query):
    normalized_query = query.casefold()
    books_found = get_cached(f"book_search:{normalized_query}")
    if books_found is None:
        books_found = search_books(query)
        set_cached(f"book_search:{normalized_query}", books_found)
    return books_found


def cached_recommendations():
    recommendations = get_cached("recommendations")
    if recommendations is None:
        recommendations = fetch_recommendations()
        set_cached("recommendations", recommendations)
    return recommendations


def cached_book_details(book_id):
    details = get_cached(f"book_details:{book_id}")
    if details is None:
        details = get_book_details(book_id)
        set_cached(f"book_details:{book_id}", details)
    return details


def cached_author_profile(author_id):
    profile = get_cached(f"author_profile:{author_id}")
    if profile is None:
        profile = get_author_profile(author_id)
        set_cached(f"author_profile:{author_id}", profile)
    return profile


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if not query:
            return render_template("index.html", error=translate("empty_query"))

        try:
            query_variants = keyboard_layout_variants(query)
            authors = []
            books_found = []
            for search_query in query_variants:
                merge_authors(authors, cached_author_search(search_query))
                merge_books(books_found, cached_book_search(search_query))

            return render_template(
                "results.html",
                authors=authors,
                books=books_found,
                search_query=query,
                searched_variants=[variant for variant in query_variants if variant != query],
            )
        except Exception:
            logger.exception("Error during unified search for %r", query)
            return render_template(
                "index.html",
                error=translate("search_error"),
            )

    return render_template("index.html")


@app.route("/recommendations")
def recommendations():
    try:
        data = cached_recommendations()
        error = None
    except Exception:
        logger.exception("Error loading recommendations")
        data = {"recommended_books": [], "recent_recommendations": []}
        error = translate("recommendations_error")

    return render_template(
        "recommendations.html",
        recommended_books=data.get("recommended_books", []),
        recent_recommendations=data.get("recent_recommendations", []),
        error=error,
    )


@app.route("/bookmarks")
def bookmarks():
    return render_template("bookmarks.html")


@app.route("/book-details/<book_id>")
def book_details(book_id):
    if not is_valid_id(book_id):
        return jsonify({"error": "Invalid book ID"}), 400
    try:
        details = cached_book_details(book_id)
        return jsonify(
            {
                "book_id": details.get("book_id", str(book_id)),
                "title": details.get("title") or "",
                "description": details.get("description") or "",
                "links": {
                    file_format: link
                    for file_format, link in (details.get("links") or {}).items()
                    if file_format in ALLOWED_FORMATS and validate_download_link(link, file_format)
                },
            }
        )
    except Exception:
        logger.exception("Failed to load details for book %s", book_id)
        return jsonify({"error": translate("details_failed")}), 500


@app.route("/download-book/<book_id>/<file_format>")
def download_book_proxy(book_id, file_format):
    if not is_valid_id(book_id) or file_format not in ALLOWED_FORMATS:
        return "Invalid book or format", 400

    title = request.args.get("title", "book")[:200]
    try:
        filename, buffer, mimetype = download_single_book(book_id, file_format, title)
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype=mimetype)
    except Exception:
        logger.exception("Failed to serve single book download for %s", book_id)
        return "Download failed.", 500


@app.route("/books/<author_id>")
def books(author_id):
    if not is_valid_id(author_id):
        return render_template(
            "books.html",
            books=[],
            author_id=author_id,
            author_name=translate("selected_author"),
            author_bio="",
            format_counts=get_format_counts([]),
            error=translate("invalid_author"),
        ), 400

    try:
        cache_key = f"all_books_for_author:{author_id}"
        books_list = get_cached(cache_key)

        if books_list is None:
            logger.info("Fetching all books for author %s", author_id)
            books_list = find_books(author_id)
            set_cached(cache_key, books_list)

        author_name = None
        author_bio = ""
        with CACHE_LOCK:
            author_search_items = [
                cached_value
                for key, (cached_value, _) in cache.items()
                if key.startswith("author_search:")
            ]
        for authors_list in author_search_items:
            for name, aid in authors_list:
                if aid == author_id:
                    author_name = name
                    break
            if author_name:
                break

        if not author_name:
            profile = cached_author_profile(author_id)
            author_name = profile.get("name") or get_author_name(author_id) or translate("selected_author")
            author_bio = profile.get("bio") or ""
        else:
            profile = cached_author_profile(author_id)
            author_bio = profile.get("bio") or ""

        return render_template(
            "books.html",
            books=books_list,
            author_id=author_id,
            author_name=author_name or translate("selected_author"),
            author_bio=author_bio,
            format_counts=get_format_counts(books_list),
        )
    except Exception:
        logger.exception("Error fetching books page for author %s", author_id)
        return render_template(
            "books.html",
            books=[],
            author_id=author_id,
            author_name=translate("selected_author"),
            author_bio="",
            format_counts=get_format_counts([]),
            error=translate("load_books_error"),
        )


@app.route("/start-download", methods=["POST"])
def start_download_job():
    cleanup_jobs()
    data = request.get_json(silent=True) or {}
    book_links = data.get("book_links") or []
    book_titles = data.get("book_titles") or []
    file_format = data.get("format", "epub")
    author_name = str(data.get("author_name", ""))[:200]

    if file_format not in ALLOWED_FORMATS:
        return jsonify({"error": "Invalid format"}), 400
    if not isinstance(book_links, list) or not isinstance(book_titles, list):
        return jsonify({"error": "Invalid book data"}), 400
    if not book_links or len(book_links) != len(book_titles):
        return jsonify({"error": "Invalid book data"}), 400
    if len(book_links) > MAX_BULK_BOOKS:
        return jsonify({"error": f"Please select {MAX_BULK_BOOKS} books or fewer."}), 400

    books_to_download = []
    skipped_links = 0
    for title, link in zip(book_titles, book_links):
        if not isinstance(title, str) or not isinstance(link, str):
            return jsonify({"error": "Invalid book data"}), 400
        if not validate_download_link(link, file_format):
            logger.warning("Skipping invalid bulk download link for %r: %s", title, link)
            skipped_links += 1
            continue
        books_to_download.append((title[:200], link))

    if not books_to_download:
        return jsonify({"error": "No valid download links for the selected format."}), 400

    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "pending",
            "progress": 0,
            "message": "Job received",
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    thread = threading.Thread(
        target=download_books_to_disk,
        args=(job_id, books_to_download, file_format, author_name, JOBS, JOBS_LOCK),
        daemon=True,
    )
    thread.start()
    return jsonify({"job_id": job_id, "skipped_links": skipped_links})


@app.route("/job-status/<job_id>")
def get_job_status(job_id):
    cleanup_jobs()
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job:
            job = public_job_status(job)
    if not job:
        return jsonify({"status": "error", "message": "Job not found"}), 404
    return jsonify(job)


@app.route("/fetch/<job_id>/<token>")
def fetch_file(job_id, token):
    cleanup_jobs()
    with JOBS_LOCK:
        job = JOBS.get(job_id)

    if not job or job.get("status") != "complete" or job.get("download_token") != token:
        return "Download not found", 404

    output_path = Path(job.get("output_path", ""))
    temp_dir = Path(tempfile.gettempdir()).resolve()
    try:
        resolved_output = output_path.resolve()
    except OSError:
        return "Download not found", 404

    if temp_dir not in resolved_output.parents or not resolved_output.is_file():
        logger.warning("Refusing to serve output outside temp dir: %s", resolved_output)
        return "Download not found", 404

    return send_file(
        resolved_output,
        as_attachment=True,
        download_name=job.get("filename", "flibusta_download"),
        mimetype=job.get("mimetype", "application/octet-stream"),
    )


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", error=translate("page_not_found")), 404


@app.errorhandler(500)
def server_error(e):
    logger.error("Server error: %s", e)
    return render_template("index.html", error=translate("server_error")), 500


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(debug=debug, port=port, host=host)
