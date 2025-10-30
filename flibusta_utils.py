# flibusta_utils.py - Enhanced version with retry logic and rate limiting
import io
import time
import requests
import py7zr
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://flibusta.is"

# Rate limiting
last_request_time = 0
MIN_REQUEST_INTERVAL = 0.2  # Reduced from 0.5s to 0.2s for faster downloads


def rate_limit():
    """Simple rate limiting"""
    global last_request_time
    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
    last_request_time = time.time()


def get_session():
    """Create a requests session with retry logic"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    return session


def search_authors(author_name, max_retries=3):
    """Search for authors on Flibusta with retry logic."""
    session = get_session()

    for attempt in range(max_retries):
        try:
            rate_limit()
            url = f"{BASE_URL}/booksearch?ask={author_name}"
            logger.info(f"Searching authors: {url} (attempt {attempt + 1})")

            response = session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            authors = []

            # Try multiple possible section headers
            author_section = None
            for header_text in ["Найденные писатели", "Авторы", "Authors"]:
                author_section = soup.find("h3", string=lambda x: x and header_text in x)
                if author_section:
                    break

            if author_section:
                ul = author_section.find_next_sibling("ul")
                if ul:
                    for link in ul.find_all("a"):
                        href = link.get("href", "")
                        if "/a/" in href:
                            author_id = href.split("/")[-1]
                            authors.append((link.text.strip(), author_id))

            logger.info(f"Found {len(authors)} author(s)")
            return authors

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                logger.error(f"All attempts failed for author search: {author_name}")
                raise
            time.sleep(2 ** attempt)  # Exponential backoff

    return []


def find_books(author_id, file_format, max_retries=3):
    """Find all books by an author in a specific format with retry logic."""
    session = get_session()

    for attempt in range(max_retries):
        try:
            rate_limit()
            url = f"{BASE_URL}/a/{author_id}"
            logger.info(f"Fetching books: {url} (attempt {attempt + 1})")

            response = session.get(url, timeout=20)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            books = []
            seen_books = set()  # Prevent duplicates

            # Find all format tags
            for fmt_tag in soup.find_all("a", string=f"({file_format})"):
                href = fmt_tag.get("href", "")
                parts = href.split("/")

                if len(parts) > 2 and parts[1] == "b":
                    book_path = f"/{parts[1]}/{parts[2]}"

                    # Skip if we've already seen this book
                    if book_path in seen_books:
                        continue
                    seen_books.add(book_path)

                    # Find the title
                    title_tag = soup.find("a", href=book_path)
                    if title_tag:
                        title = title_tag.text.strip()
                        download_url = f"{BASE_URL}{href}"
                        books.append((title, download_url))

            logger.info(f"Found {len(books)} book(s) in {file_format} format")
            return books

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                logger.error(f"All attempts failed for author {author_id}")
                raise
            time.sleep(2 ** attempt)

    return []


def _fetch_book_bytes(title, link, max_retries=3):
    """Downloads a single book and returns its (title, bytes) with retry logic."""
    session = get_session()

    for attempt in range(max_retries):
        try:
            rate_limit()
            logger.info(f"Downloading: {title} (attempt {attempt + 1})")

            r = session.get(link, stream=True, timeout=30)
            r.raise_for_status()

            # Read content in chunks to handle large files
            content = b''
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    content += chunk

            logger.info(f"Successfully downloaded: {title} ({len(content)} bytes)")
            return title, content

        except requests.exceptions.RequestException as e:
            logger.warning(f"Download attempt {attempt + 1} failed for {title}: {str(e)}")
            if attempt == max_retries - 1:
                logger.error(f"All download attempts failed for: {title}")
                raise
            time.sleep(2 ** attempt)

    raise Exception(f"Failed to download {title}")


def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters"""
    # Replace invalid characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')

    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')

    # Limit length
    if len(filename) > 200:
        filename = filename[:200]

    return filename if filename else "untitled"


def download_books_in_memory(books, file_format, author_name=None):
    """
    Downloads books with progress tracking.
    - If 1 book: return that single file (filename, BytesIO, mimetype)
    - If multiple: return 7z archive (filename, BytesIO, mimetype)

    Args:
        books: List of (title, link) tuples
        file_format: Format of books (epub, fb2, mobi)
        author_name: Optional author name for archive filename
    """
    if not books:
        raise ValueError("No books to download")

    if len(books) == 1:
        title, link = books[0]
        logger.info(f"Downloading single book: {title}")

        _, data = _fetch_book_bytes(title, link)
        safe_title = sanitize_filename(title)
        filename = f"{safe_title}.{file_format}"

        # Get proper MIME type
        mime_types = {
            "epub": "application/epub+zip",
            "fb2": "application/xml",
            "mobi": "application/x-mobipocket-ebook"
        }
        mimetype = mime_types.get(file_format, f"application/{file_format}")

        return filename, io.BytesIO(data), mimetype

    # Multiple books → create .7z archive
    logger.info(f"Creating archive with {len(books)} books")

    # Create archive filename from author name or default
    if author_name:
        archive_name = f"{sanitize_filename(author_name)}_books.7z"
    else:
        archive_name = "books.7z"

    # Download all books first
    downloaded_books = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_book_bytes, title, link): (title, link)
                   for title, link in books}

        for future in as_completed(futures):
            try:
                title, data = future.result()
                safe_title = sanitize_filename(title)
                book_filename = f"{safe_title}.{file_format}"
                downloaded_books[book_filename] = data
                logger.info(f"Downloaded: {title} ({len(data)} bytes)")
            except Exception as e:
                title, link = futures[future]
                logger.error(f"Failed to download {title}: {str(e)}")

    # Create archive with downloaded books
    archive_buffer = io.BytesIO()
    with py7zr.SevenZipFile(archive_buffer, mode="w") as archive:
        for filename, data in downloaded_books.items():
            archive.writestr(data, filename)
            logger.info(f"Added to archive: {filename}")

    archive_buffer.seek(0)
    logger.info(f"Archive created successfully with {len(downloaded_books)} books")

    return archive_name, archive_buffer, "application/x-7z-compressed"