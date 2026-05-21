import io
import logging
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BASE_URL = "https://flibusta.is"
FORMAT_ORDER = ("epub", "fb2", "mobi", "pdf", "docx")
ALLOWED_FORMATS = frozenset(FORMAT_ORDER)
MIME_TYPES = {
    "epub": "application/epub+zip",
    "fb2": "application/x-fictionbook+xml",
    "mobi": "application/x-mobipocket-ebook",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
DESCRIPTION_LIMIT = 6000
BIO_LIMIT = 9000

_BOOK_PATH_RE = re.compile(r"^/b/(?P<book_id>\d+)(?:/(?P<action>[A-Za-z0-9_-]+))?/?$")
_AUTHOR_PATH_RE = re.compile(r"^/a/(?P<author_id>\d+)/?$")
_USER_PATH_RE = re.compile(r"^/user/(?P<user_id>\d+)/?$")
_last_request_time = 0.0
_rate_limit_lock = threading.Lock()
MIN_REQUEST_INTERVAL = 0.2


def rate_limit():
    global _last_request_time
    with _rate_limit_lock:
        current_time = time.time()
        time_since_last = current_time - _last_request_time
        if time_since_last < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
        _last_request_time = time.time()


def get_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko)"
            )
        }
    )
    return session


def _get_soup(session, url, *, params=None, timeout=15):
    rate_limit()
    response = session.get(url, params=params, timeout=timeout)
    response.raise_for_status()
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    return BeautifulSoup(response.text, "html.parser")


def _absolute_url(href):
    return urljoin(BASE_URL, href)


def _extract_book_id(href):
    parsed = urlparse(_absolute_url(href))
    match = _BOOK_PATH_RE.match(parsed.path)
    return match.group("book_id") if match else None


def _extract_author_id(href):
    parsed = urlparse(_absolute_url(href))
    match = _AUTHOR_PATH_RE.match(parsed.path)
    return match.group("author_id") if match else None


def _extract_user_id(href):
    parsed = urlparse(_absolute_url(href))
    match = _USER_PATH_RE.match(parsed.path)
    return match.group("user_id") if match else None


def _clean_link_text(link):
    return link.get_text(" ", strip=True)


def _compact_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate_text(text, limit):
    text = _compact_text(text)
    if len(text) <= limit:
        return text
    return f"{text[:limit].rsplit(' ', 1)[0].rstrip()}..."


def _format_from_link_text(text):
    normalized = text.casefold()
    for file_format in FORMAT_ORDER:
        if file_format in normalized:
            return file_format
    return None


def validate_download_link(link, expected_format):
    if expected_format not in ALLOWED_FORMATS:
        return False

    parsed = urlparse(link)
    base = urlparse(BASE_URL)
    if parsed.scheme != base.scheme or parsed.netloc != base.netloc:
        return False

    match = _BOOK_PATH_RE.match(parsed.path)
    if not match:
        return False

    action = match.group("action")
    if action == expected_format:
        return True
    return action == "download"


def search_authors(author_name, max_retries=3):
    session = get_session()
    for attempt in range(max_retries):
        try:
            logger.info("Searching authors for %r (attempt %s)", author_name, attempt + 1)
            soup = _get_soup(
                session,
                f"{BASE_URL}/booksearch",
                params={"ask": author_name},
                timeout=15,
            )
            authors = []
            author_section = None
            for header_text in ("Найденные писатели", "Авторы", "Authors"):
                author_section = soup.find("h3", string=lambda text: text and header_text in text)
                if author_section:
                    break

            if author_section:
                author_list = author_section.find_next_sibling("ul")
                if author_list:
                    for link in author_list.find_all("a"):
                        author_id = _extract_author_id(link.get("href", ""))
                        if author_id:
                            authors.append((link.text.strip(), author_id))

            logger.info("Found %s author(s)", len(authors))
            return authors
        except requests.exceptions.RequestException as exc:
            logger.warning("Author search attempt %s failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(2**attempt)
    return []


def get_author_name(author_id, max_retries=3):
    if not str(author_id).isdigit():
        raise ValueError("Invalid author ID")

    session = get_session()
    for attempt in range(max_retries):
        try:
            soup = _get_soup(session, f"{BASE_URL}/a/{author_id}", timeout=20)
            heading = soup.find("h1", class_="title") or soup.find("h1")
            if heading:
                return heading.get_text(" ", strip=True)
            return None
        except requests.exceptions.RequestException as exc:
            logger.warning("Author name attempt %s failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                return None
            time.sleep(2**attempt)
    return None


def download_single_book(book_id, file_format, title):
    if not str(book_id).isdigit() or file_format not in ALLOWED_FORMATS:
        raise ValueError("Invalid book ID or format")

    session = get_session()
    path_suffix = "download" if file_format in {"pdf", "docx"} else file_format
    url = f"{BASE_URL}/b/{book_id}/{path_suffix}"
    logger.info("Proxy downloading book %s in %s format", book_id, file_format)

    try:
        rate_limit()
        response = session.get(url, timeout=60)
        response.raise_for_status()
        filename = f"{sanitize_filename(title)}.{file_format}"
        return filename, io.BytesIO(response.content), MIME_TYPES.get(file_format, "application/octet-stream")
    except requests.exceptions.RequestException:
        logger.exception("Failed to proxy download book %s", book_id)
        raise


def _get_download_links_from_book_page(book_page_url):
    logger.debug("Fetching details from book page: %s", book_page_url)
    session = get_session()
    try:
        soup = _get_soup(session, book_page_url, timeout=10)
        book_id = _extract_book_id(book_page_url)
        if not book_id:
            return {}

        download_links = _collect_download_links(soup, book_id)

        logger.debug("Found formats on page: %s", list(download_links.keys()))
        return download_links
    except requests.exceptions.RequestException as exc:
        logger.warning("Failed to fetch book page %s: %s", book_page_url, exc)
        return {}


def _extract_section_after_heading(main, heading_markers, limit):
    for heading in main.find_all(["h2", "h3", "h4"]):
        heading_text = heading.get_text(" ", strip=True).casefold()
        if not any(marker in heading_text for marker in heading_markers):
            continue

        chunks = []
        for sibling in heading.find_next_siblings():
            if getattr(sibling, "name", None) in {"h1", "h2", "h3", "h4"}:
                break
            if getattr(sibling, "name", None) not in {"p", "div", "blockquote"}:
                continue
            text = _compact_text(sibling.get_text(" ", strip=True))
            if text:
                chunks.append(text)
            if len(" ".join(chunks)) >= limit:
                break
        if chunks:
            return _truncate_text(" ".join(chunks), limit)
    return ""


def _extract_book_description(soup):
    main = soup.find(id="main") or soup

    description = _extract_section_after_heading(
        main,
        ("аннотац", "описан", "annotation", "description"),
        DESCRIPTION_LIMIT,
    )
    if description:
        return description

    for selector in (".annotation", ".book-description", ".book_desc", "#book_descr", "#annotation"):
        node = main.select_one(selector)
        if node:
            text = _truncate_text(node.get_text(" ", strip=True), DESCRIPTION_LIMIT)
            if text:
                return text

    for paragraph in main.find_all("p"):
        text = _compact_text(paragraph.get_text(" ", strip=True))
        if len(text) >= 120 and not any(skip in text.casefold() for skip in ("скачать", "download", "жанр")):
            return _truncate_text(text, DESCRIPTION_LIMIT)
    return ""


def _book_details_from_soup(soup, book_id, book_page_url):
    title_node = soup.find("h1", class_="title") or soup.find("h1")
    author_link = soup.find("a", href=lambda href: href and _extract_author_id(href))
    return {
        "book_id": str(book_id),
        "title": title_node.get_text(" ", strip=True) if title_node else "",
        "book_url": book_page_url,
        "author_name": author_link.get_text(" ", strip=True) if author_link else None,
        "author_id": _extract_author_id(author_link.get("href", "")) if author_link else None,
        "description": _extract_book_description(soup),
        "links": _collect_download_links(soup, book_id),
    }


def _collect_download_links(soup, book_id):
    download_links = {}
    for link in soup.find_all("a", href=lambda href: href and f"/b/{book_id}" in href):
        file_format = _format_from_link_text(link.text.strip())
        if file_format:
            download_links[file_format] = _absolute_url(link["href"])
    return download_links


def get_book_details(book_id, max_retries=3):
    if not str(book_id).isdigit():
        raise ValueError("Invalid book ID")

    session = get_session()
    book_page_url = f"{BASE_URL}/b/{book_id}"
    for attempt in range(max_retries):
        try:
            soup = _get_soup(session, book_page_url, timeout=15)
            return _book_details_from_soup(soup, book_id, book_page_url)
        except requests.exceptions.RequestException as exc:
            logger.warning("Book details attempt %s failed for %s: %s", attempt + 1, book_id, exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(2**attempt)
    return {}


def search_books(book_title, max_retries=3):
    session = get_session()
    for attempt in range(max_retries):
        try:
            logger.info("Searching books for %r (attempt %s)", book_title, attempt + 1)
            soup = _get_soup(
                session,
                f"{BASE_URL}/booksearch",
                params={"ask": book_title},
                timeout=15,
            )
            break
        except requests.exceptions.RequestException as exc:
            logger.warning("Book search attempt %s failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                return []
            time.sleep(2**attempt)
    else:
        return []

    book_section_header = soup.find("h3", string=lambda text: text and "Найденные книги" in text)
    if not book_section_header:
        return []

    results_list = book_section_header.find_next_sibling("ul")
    if not results_list:
        return []

    potential_books = []
    for item in results_list.find_all("li", recursive=False):
        main_book_link = item.find("a", href=lambda href: href and href.startswith("/b/"))
        if not main_book_link:
            continue

        book_id = _extract_book_id(main_book_link.get("href", ""))
        if not book_id:
            continue

        author_link = item.find("a", href=lambda href: href and href.startswith("/a/"))
        potential_books.append(
            {
                "title": main_book_link.text.strip(),
                "book_page_url": _absolute_url(main_book_link["href"]),
                "author_name": author_link.text.strip() if author_link else "Unknown Author",
                "author_id": _extract_author_id(author_link.get("href", "")) if author_link else None,
                "book_id": book_id,
            }
        )

    if not potential_books:
        return []

    final_books = []
    with ThreadPoolExecutor(max_workers=min(3, len(potential_books))) as executor:
        future_to_book = {
            executor.submit(get_book_details, book["book_id"]): book
            for book in potential_books
        }
        for future in as_completed(future_to_book):
            book_data = future_to_book[future]
            try:
                details = future.result()
                download_links = details.get("links", {})
                if download_links:
                    book_data["description"] = details.get("description", "")
                    del book_data["book_page_url"]
                    book_data["links"] = download_links
                    final_books.append(book_data)
            except Exception:
                logger.exception("Failed to process details for %r", book_data["title"])

    logger.info("Found %s books with download links", len(final_books))
    return final_books


def _recommendation_links(soup):
    main = soup.find(id="main") or soup
    for link in main.find_all("a", href=True):
        text = _clean_link_text(link)
        if not text:
            continue
        href = link.get("href", "")
        yield {
            "text": text,
            "href": href,
            "book_id": _extract_book_id(href),
            "author_id": _extract_author_id(href),
            "user_id": _extract_user_id(href),
        }


def _parse_recommendation_page(soup, *, include_users=False, limit=40):
    entries = []
    seen_book_ids = set()
    last_author = None
    pending_entry = None
    last_book_href = None

    for link in _recommendation_links(soup):
        if link["author_id"]:
            last_author = {
                "author_id": link["author_id"],
                "author_name": link["text"],
            }
            last_book_href = None
            continue

        if link["book_id"]:
            if link["href"] == last_book_href:
                continue
            if not include_users and link["book_id"] in seen_book_ids:
                continue

            entry = {
                "book_id": link["book_id"],
                "title": link["text"],
                "book_url": _absolute_url(link["href"]),
                "author_id": last_author["author_id"] if last_author else None,
                "author_name": last_author["author_name"] if last_author else None,
            }
            entries.append(entry)
            pending_entry = entry
            seen_book_ids.add(link["book_id"])
            last_book_href = link["href"]

            if len(entries) >= limit and not include_users:
                break
            continue

        if include_users and link["user_id"] and pending_entry and not pending_entry.get("user_id"):
            pending_entry["user_id"] = link["user_id"]
            pending_entry["user_name"] = link["text"]
            pending_entry = None
            if len(entries) >= limit:
                break

    return entries[:limit]


def fetch_recommendations(limit=40):
    session = get_session()
    recommended_books = []
    recent_recommendations = []

    try:
        soup = _get_soup(session, f"{BASE_URL}/rec", params={"view": "books"}, timeout=20)
        recommended_books = _parse_recommendation_page(soup, include_users=False, limit=limit)
    except requests.exceptions.RequestException as exc:
        logger.warning("Failed to fetch recommended books: %s", exc)

    try:
        soup = _get_soup(session, f"{BASE_URL}/rec", params={"view": "recs"}, timeout=20)
        recent_recommendations = _parse_recommendation_page(soup, include_users=True, limit=limit)
    except requests.exceptions.RequestException as exc:
        logger.warning("Failed to fetch recent recommendations: %s", exc)

    return {
        "recommended_books": recommended_books,
        "recent_recommendations": recent_recommendations,
    }


def _extract_author_bio(soup):
    main = soup.find(id="main") or soup
    biography = _extract_section_after_heading(
        main,
        ("биограф", "об автор", "about", "biography"),
        BIO_LIMIT,
    )
    if biography:
        return biography

    heading = main.find("h1", class_="title") or main.find("h1")
    candidates = []
    siblings = heading.find_next_siblings() if heading else main.find_all(["p", "div"], recursive=False)
    for sibling in siblings:
        if getattr(sibling, "name", None) in {"h2", "h3", "h4", "ul"}:
            break
        if getattr(sibling, "name", None) not in {"p", "div", "blockquote"}:
            continue
        text = _compact_text(sibling.get_text(" ", strip=True))
        lowered = text.casefold()
        if len(text) < 80 or any(skip in lowered for skip in ("книги автора", "скачать", "fb2", "epub")):
            continue
        candidates.append(text)
        if len(" ".join(candidates)) >= BIO_LIMIT:
            break
    return _truncate_text(" ".join(candidates), BIO_LIMIT) if candidates else ""


def get_author_profile(author_id, max_retries=3):
    if not str(author_id).isdigit():
        raise ValueError("Invalid author ID")

    session = get_session()
    for attempt in range(max_retries):
        try:
            soup = _get_soup(session, f"{BASE_URL}/a/{author_id}", timeout=20)
            heading = soup.find("h1", class_="title") or soup.find("h1")
            return {
                "author_id": str(author_id),
                "name": heading.get_text(" ", strip=True) if heading else None,
                "bio": _extract_author_bio(soup),
            }
        except requests.exceptions.RequestException as exc:
            logger.warning("Author profile attempt %s failed for %s: %s", attempt + 1, author_id, exc)
            if attempt == max_retries - 1:
                return {"author_id": str(author_id), "name": None, "bio": ""}
            time.sleep(2**attempt)
    return {"author_id": str(author_id), "name": None, "bio": ""}


def find_books(author_id, max_retries=3):
    if not str(author_id).isdigit():
        raise ValueError("Invalid author ID")

    session = get_session()
    for attempt in range(max_retries):
        try:
            logger.info("Fetching all books and formats for author %s", author_id)
            soup = _get_soup(session, f"{BASE_URL}/a/{author_id}", timeout=20)
            books = []
            seen_book_ids = set()

            for link in soup.select("a[href^='/b/']"):
                book_id = _extract_book_id(link.get("href", ""))
                if not book_id or book_id in seen_book_ids:
                    continue
                seen_book_ids.add(book_id)

                title = link.text.strip()
                parent = link.find_parent(["div", "li"]) or soup

                download_links = {}
                for format_link in parent.find_all("a", href=lambda href: href and f"/b/{book_id}" in href):
                    file_format = _format_from_link_text(format_link.text.strip())
                    if file_format:
                        download_links[file_format] = _absolute_url(format_link["href"])

                if title and download_links:
                    books.append({"title": title, "book_id": book_id, "links": download_links})

            logger.info("Found %s unique books for author %s", len(books), author_id)
            return books
        except requests.exceptions.RequestException as exc:
            logger.warning("Author page attempt %s failed: %s", attempt + 1, exc)
            if attempt == max_retries - 1:
                raise
            time.sleep(2**attempt)
    return []


def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    cleaned = str(filename)
    for char in invalid_chars:
        cleaned = cleaned.replace(char, "_")
    cleaned = cleaned.strip(". ")
    if len(cleaned) > 200:
        cleaned = cleaned[:200].rstrip(". ")
    return cleaned or "untitled"


def _unique_destination(directory, title, file_format, index):
    safe_title = sanitize_filename(title)
    destination = directory / f"{safe_title}.{file_format}"
    if not destination.exists():
        return destination
    return directory / f"{safe_title}_{index}.{file_format}"


def _unique_temp_output(filename):
    safe_name = sanitize_filename(filename)
    suffix = Path(safe_name).suffix
    stem = Path(safe_name).stem or "flibusta_download"
    token = secrets.token_hex(4)
    return Path(tempfile.gettempdir()) / f"{stem}_{token}{suffix}"


def _fetch_book_to_file(title, link, file_format, destination_path):
    if not validate_download_link(link, file_format):
        logger.warning("Rejected invalid download link for %r: %s", title, link)
        return False

    session = get_session()
    logger.info("Downloading %r to %s", title, destination_path)
    try:
        rate_limit()
        with session.get(link, stream=True, timeout=60) as response:
            response.raise_for_status()
            with destination_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        file.write(chunk)
        return destination_path.stat().st_size > 0
    except (OSError, requests.exceptions.RequestException) as exc:
        logger.error("Download failed for %r: %s", title, exc)
        return False


def _update_job(job_id, jobs_dict, lock, **fields):
    with lock:
        job = jobs_dict.get(job_id, {})
        job.update(fields)
        job["updated_at"] = time.time()
        jobs_dict[job_id] = job


def download_books_to_disk(job_id, books, file_format, author_name, jobs_dict, lock):
    if not books:
        _update_job(job_id, jobs_dict, lock, status="error", message="No books selected")
        return
    if file_format not in ALLOWED_FORMATS:
        _update_job(job_id, jobs_dict, lock, status="error", message="Invalid format")
        return

    download_dir = Path(tempfile.mkdtemp(prefix="flibusta_books_"))
    total_books = len(books)
    books_downloaded = 0

    try:
        _update_job(job_id, jobs_dict, lock, status="processing", progress=0, message="Starting downloads")

        with ThreadPoolExecutor(max_workers=min(3, total_books)) as executor:
            future_to_book = {}
            for index, (title, link) in enumerate(books, 1):
                destination_path = _unique_destination(download_dir, title, file_format, index)
                future = executor.submit(_fetch_book_to_file, title, link, file_format, destination_path)
                future_to_book[future] = title

            for future in as_completed(future_to_book):
                title = future_to_book[future]
                if future.result():
                    books_downloaded += 1
                else:
                    logger.warning("Skipping %r due to download failure", title)

                progress = int((books_downloaded / total_books) * 80)
                _update_job(
                    job_id,
                    jobs_dict,
                    lock,
                    status="processing",
                    progress=progress,
                    message=f"Downloaded {books_downloaded}/{total_books}",
                )

        downloaded_files = [path for path in download_dir.iterdir() if path.is_file()]
        if not downloaded_files:
            _update_job(
                job_id,
                jobs_dict,
                lock,
                status="error",
                progress=0,
                message="No books could be downloaded.",
            )
            return

        if len(downloaded_files) == 1:
            source_path = downloaded_files[0]
            output_path = _unique_temp_output(source_path.name)
            shutil.move(str(source_path), str(output_path))
            _update_job(
                job_id,
                jobs_dict,
                lock,
                status="complete",
                progress=100,
                message="Download ready",
                filename=source_path.name,
                output_path=str(output_path),
                mimetype=MIME_TYPES.get(file_format, "application/octet-stream"),
                download_token=secrets.token_urlsafe(24),
            )
            logger.info("Single-file download prepared: %s", output_path)
            return

        archive_name_base = f"{sanitize_filename(author_name)}_books" if author_name else "flibusta_books"
        archive_name = f"{archive_name_base}_{job_id[:8]}.zip"
        archive_path = Path(tempfile.gettempdir()) / archive_name

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for archived_count, file_path in enumerate(downloaded_files, 1):
                zip_file.write(file_path, arcname=file_path.name)
                progress = 80 + int((archived_count / len(downloaded_files)) * 20)
                _update_job(
                    job_id,
                    jobs_dict,
                    lock,
                    status="processing",
                    progress=progress,
                    message=f"Archiving {archived_count}/{len(downloaded_files)}",
                )

        _update_job(
            job_id,
            jobs_dict,
            lock,
            status="complete",
            progress=100,
            message="Download ready",
            filename=archive_name,
            output_path=str(archive_path),
            mimetype="application/zip",
            download_token=secrets.token_urlsafe(24),
        )
        logger.info("Archive created successfully: %s", archive_path)
    except Exception:
        logger.exception("Error during job %s", job_id)
        _update_job(job_id, jobs_dict, lock, status="error", message="An unexpected error occurred.")
    finally:
        shutil.rmtree(download_dir, ignore_errors=True)
