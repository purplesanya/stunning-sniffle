# flibusta_utils.py
import io
import time
import requests
import py7zr
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
import os
import tempfile
import shutil

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


def _fetch_book_bytes(title, link):
    """Downloads a single book and returns its (title, bytes)."""
    session = get_session()
    logger.info(f"Downloading: {title}")
    try:
        r = session.get(link, stream=True, timeout=60) # Increased timeout for slow downloads
        r.raise_for_status()
        content = b''
        for chunk in r.iter_content(chunk_size=8192):
            content += chunk
        logger.info(f"Successfully downloaded: {title} ({len(content)} bytes)")
        return title, content
    except requests.exceptions.RequestException as e:
        logger.error(f"Download failed for {title}: {str(e)}")
        raise


def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')

    # Remove leading/trailing spaces and dots
    filename = filename.strip('. ')

    # Limit length
    if len(filename) > 200:
        filename = filename[:200]

    return filename if filename else "untitled"


def download_books_to_disk(job_id, books, file_format, author_name, jobs_dict):
    """
    Downloads books to a temporary directory on disk, creates a 7z archive,
    and updates a shared dictionary with progress.
    """
    if not books:
        jobs_dict[job_id] = {"status": "error", "message": "No books selected"}
        return

    # Use a unique directory in the system's temp location
    download_dir = tempfile.mkdtemp()
    total_books = len(books)
    books_downloaded = 0

    try:
        # Step 1: Download all books to the temporary directory
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_book = {executor.submit(_fetch_book_bytes, title, link): title for title, link in books}
            for future in as_completed(future_to_book):
                try:
                    title, data = future.result()
                    safe_title = sanitize_filename(title)
                    book_filename = f"{safe_title}.{file_format}"
                    
                    with open(os.path.join(download_dir, book_filename), "wb") as f:
                        f.write(data)
                    
                    books_downloaded += 1
                    progress = int((books_downloaded / total_books) * 90) # Downloading is 90% of the work
                    jobs_dict[job_id] = {"status": "processing", "progress": progress, "message": f"Downloaded {books_downloaded}/{total_books}"}
                
                except Exception as e:
                    title = future_to_book[future]
                    logger.error(f"Skipping book {title} due to download error: {e}")

        # Step 2: Create the archive from the downloaded files
        jobs_dict[job_id] = {"status": "processing", "progress": 95, "message": "Creating archive..."}
        if author_name:
            archive_name_base = f"{sanitize_filename(author_name)}_books"
        else:
            archive_name_base = "flibusta_books"
        
        archive_name = f"{archive_name_base}_{job_id[:8]}.7z"
        archive_path = os.path.join(tempfile.gettempdir(), archive_name)

        with py7zr.SevenZipFile(archive_path, 'w') as archive:
            archive.writeall(download_dir, arcname='') # arcname='' puts files in the root of the archive

        # Step 3: Finalize the job status
        jobs_dict[job_id] = {"status": "complete", "progress": 100, "filename": archive_name}
        logger.info(f"Archive created successfully: {archive_path}")

    except Exception as e:
        logger.error(f"Error during job {job_id}: {e}")
        jobs_dict[job_id] = {"status": "error", "message": "An unexpected error occurred."}
    
    finally:
        # Clean up the directory with downloaded books
        shutil.rmtree(download_dir)
