# flibusta_utils.py
import time
import requests
import zipfile  # <-- IMPORT ZIPFILE
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
MIN_REQUEST_INTERVAL = 0.2


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
            time.sleep(2 ** attempt)
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
            seen_books = set()
            for fmt_tag in soup.find_all("a", string=f"({file_format})"):
                href = fmt_tag.get("href", "")
                parts = href.split("/")
                if len(parts) > 2 and parts[1] == "b":
                    book_path = f"/{parts[1]}/{parts[2]}"
                    if book_path in seen_books:
                        continue
                    seen_books.add(book_path)
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


def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    filename = filename.strip('. ')
    if len(filename) > 200:
        filename = filename[:200]
    return filename if filename else "untitled"


def _fetch_book_to_file(title, link, destination_path):
    """
    Downloads a single book and streams it directly to a file on disk.
    This uses minimal memory.
    """
    session = get_session()
    logger.info(f"Downloading '{title}' to '{destination_path}'")
    try:
        with session.get(link, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(destination_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logger.info(f"Successfully downloaded: {title}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Download failed for {title}: {str(e)}")
        return False


def download_books_to_disk(job_id, books, file_format, author_name, jobs_dict, lock):
    """
    Downloads books to a temporary directory on disk, creates a zip archive,
    and updates a shared dictionary with progress using a lock.
    """
    if not books:
        with lock:
            jobs_dict[job_id] = {"status": "error", "message": "No books selected"}
        return

    download_dir = tempfile.mkdtemp()
    total_books = len(books)
    books_downloaded = 0
    
    def update_status(progress, message):
        with lock:
            jobs_dict[job_id] = {"status": "processing", "progress": int(progress), "message": message}

    try:
        # Step 1: Download all books (0% -> 80% of progress)
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_book = {}
            for title, link in books:
                safe_title = sanitize_filename(title)
                book_filename = f"{safe_title}.{file_format}"
                destination_path = os.path.join(download_dir, book_filename)
                future = executor.submit(_fetch_book_to_file, title, link, destination_path)
                future_to_book[future] = title
            
            for future in as_completed(future_to_book):
                title = future_to_book[future]
                if future.result():
                    books_downloaded += 1
                else:
                    logger.warning(f"Skipping book '{title}' due to download failure.")
                
                progress = (books_downloaded / total_books) * 80
                update_status(progress, f"Downloaded {books_downloaded}/{total_books}")

        # Step 2: Create the zip archive with granular progress (80% -> 100% of progress)
        if author_name:
            archive_name_base = f"{sanitize_filename(author_name)}_books"
        else:
            archive_name_base = "flibusta_books"
        
        archive_name = f"{archive_name_base}_{job_id[:8]}.zip" # <-- CHANGED to .zip
        archive_path = os.path.join(tempfile.gettempdir(), archive_name)
        
        files_to_archive = os.listdir(download_dir)
        total_files_to_archive = len(files_to_archive)
        archived_count = 0

        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in files_to_archive:
                file_path = os.path.join(download_dir, filename)
                zipf.write(file_path, arcname=filename)
                archived_count += 1
                # Archiving will take up the last 20% of the progress bar
                progress = 80 + (archived_count / total_files_to_archive) * 20
                update_status(progress, f"Archiving {archived_count}/{total_files_to_archive}")

        # Step 3: Finalize
        with lock:
            jobs_dict[job_id] = {"status": "complete", "progress": 100, "filename": archive_name}
        logger.info(f"Archive created successfully: {archive_path}")

    except Exception as e:
        logger.error(f"Error during job {job_id}: {e}", exc_info=True)
        with lock:
            jobs_dict[job_id] = {"status": "error", "message": "An unexpected error occurred."}
    
    finally:
        # Clean up the directory with downloaded books
        shutil.rmtree(download_dir)
