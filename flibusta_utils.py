# flibusta_utils.py
import time
import requests
import zipfile
import io
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

# ... (rate_limit, get_session, search_authors, download_single_book are unchanged) ...
last_request_time = 0
MIN_REQUEST_INTERVAL = 0.2


def rate_limit():
    global last_request_time
    current_time = time.time()
    time_since_last = current_time - last_request_time
    if time_since_last < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
    last_request_time = time.time()


def get_session():
    session = requests.Session()
    retry = Retry(
        total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504],
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


def download_single_book(book_id, file_format, title):
    session = get_session()
    url = f"{BASE_URL}/b/{book_id}/{file_format}"
    if file_format in ['pdf', 'docx']:
        url = f"{BASE_URL}/b/{book_id}/download"
    logger.info(f"Proxy downloading book: {title} from {url}")
    try:
        rate_limit()
        response = session.get(url, timeout=60)
        response.raise_for_status()
        sanitized_title = sanitize_filename(title)
        filename = f"{sanitized_title}.{file_format}"
        mime_types = {
            "epub": "application/epub+zip", "fb2": "application/x-fictionbook+xml",
            "mobi": "application/x-mobipocket-ebook", "pdf": "application/pdf",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
        mimetype = mime_types.get(file_format, "application/octet-stream")
        return filename, io.BytesIO(response.content), mimetype
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to proxy download book {book_id}: {e}")
        raise


def _get_download_links_from_book_page(book_page_url):
    logger.debug(f"      Fetching details from book page: {book_page_url}")
    session = get_session()
    try:
        rate_limit()
        response = session.get(book_page_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        download_links = {}
        book_id = book_page_url.split('/b/')[1].split('?')[0]
        for link in soup.find_all("a", href=lambda href: href and f"/b/{book_id}" in href):
            link_text = link.text.strip().lower()
            if 'fb2' in link_text:
                download_links['fb2'] = f"{BASE_URL}{link['href']}"
            elif 'epub' in link_text:
                download_links['epub'] = f"{BASE_URL}{link['href']}"
            elif 'mobi' in link_text:
                download_links['mobi'] = f"{BASE_URL}{link['href']}"
            elif 'pdf' in link_text:
                download_links['pdf'] = f"{BASE_URL}{link['href']}"
            elif 'docx' in link_text:
                download_links['docx'] = f"{BASE_URL}{link['href']}"
        logger.debug(f"      Found formats on page: {list(download_links.keys())}")
        return download_links
    except requests.exceptions.RequestException as e:
        logger.warning(f"      Failed to fetch book page {book_page_url}: {e}")
        return {}


def search_books(book_title, max_retries=3):
    # This function is correct and remains unchanged
    logger.debug("--- STARTING 2-STEP BOOK SEARCH DEBUG ---")
    session = get_session()
    search_url = f"{BASE_URL}/booksearch?ask={book_title}"
    logger.debug(f"Step 1: Fetching search results from {search_url}")
    try:
        rate_limit()
        response = session.get(search_url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        book_section_header = soup.find("h3", string=lambda text: text and "Найденные книги" in text)
        if not book_section_header: return []
        results_list = book_section_header.find_next_sibling("ul")
        if not results_list: return []
        potential_books = []
        for item in results_list.find_all("li", recursive=False):
            main_book_link = item.find("a", href=lambda href: href and href.startswith('/b/'))
            if not main_book_link: continue
            author_link = item.find("a", href=lambda href: href and href.startswith('/a/'))
            book_id = main_book_link['href'].split('/')[2]
            potential_books.append({
                "title": main_book_link.text.strip(),
                "book_page_url": f"{BASE_URL}{main_book_link['href']}",
                "author_name": author_link.text.strip() if author_link else "Unknown Author",
                "author_id": author_link['href'].split('/')[-1] if author_link else None, "book_id": book_id
            })
        if not potential_books: return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch initial search page: {e}", exc_info=True)
        return []
    logger.debug("Step 2: Fetching download links from each book's page...")
    final_books = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_book = {executor.submit(_get_download_links_from_book_page, book["book_page_url"]): book for book in
                          potential_books}
        for future in as_completed(future_to_book):
            book_data = future_to_book[future]
            try:
                download_links = future.result()
                if download_links:
                    book_data["links"] = download_links
                    del book_data["book_page_url"]
                    final_books.append(book_data)
            except Exception as e:
                logger.error(f"An error occurred while processing details for '{book_data['title']}': {e}",
                             exc_info=True)
    logger.info(f"Final result: Found {len(final_books)} books with download links.")
    return final_books


# *** REWRITTEN find_books FUNCTION ***
def find_books(author_id, max_retries=3):
    """
    Finds all books by an author and ALL available download formats for each book.
    """
    session = get_session()
    for attempt in range(max_retries):
        try:
            rate_limit()
            url = f"{BASE_URL}/a/{author_id}"
            logger.info(f"Fetching all books and formats for author {author_id}")
            response = session.get(url, timeout=20)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            books = []

            # Find all main book links on the author page
            main_book_links = soup.select("a[href^='/b/']")
            seen_book_ids = set()

            for link in main_book_links:
                book_id = link['href'].split('/')[2]
                if book_id in seen_book_ids:
                    continue
                seen_book_ids.add(book_id)

                title = link.text.strip()

                # Find the container of this link to find sibling format links
                # This is a bit fragile, as it assumes structure. A common parent is often 'div' or 'li'.
                parent = link.find_parent(['div', 'li'])
                if not parent:
                    parent = soup  # Fallback to the whole page if no close parent found

                download_links = {}
                for format_link in parent.find_all("a", href=lambda href: href and f"/b/{book_id}" in href):
                    link_text = format_link.text.strip().lower()
                    if 'fb2' in link_text:
                        download_links['fb2'] = f"{BASE_URL}{format_link['href']}"
                    elif 'epub' in link_text:
                        download_links['epub'] = f"{BASE_URL}{format_link['href']}"
                    elif 'mobi' in link_text:
                        download_links['mobi'] = f"{BASE_URL}{format_link['href']}"
                    elif 'pdf' in link_text:
                        download_links['pdf'] = f"{BASE_URL}{format_link['href']}"
                    elif 'docx' in link_text:
                        download_links['docx'] = f"{BASE_URL}{format_link['href']}"

                if title and download_links:
                    books.append({
                        "title": title,
                        "links": download_links
                    })

            logger.info(f"Found {len(books)} unique books for author {author_id}")
            return books

        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                logger.error(f"All attempts failed for author {author_id}")
                raise
            time.sleep(2 ** attempt)
    return []


# ... (sanitize_filename, _fetch_book_to_file, download_books_to_disk are unchanged) ...
def sanitize_filename(filename):
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    filename = filename.strip('. ')
    if len(filename) > 200:
        filename = filename[:200]
    return filename if filename else "untitled"


def _fetch_book_to_file(title, link, destination_path):
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
        if author_name:
            archive_name_base = f"{sanitize_filename(author_name)}_books"
        else:
            archive_name_base = "flibusta_books"
        archive_name = f"{archive_name_base}_{job_id[:8]}.zip"
        archive_path = os.path.join(tempfile.gettempdir(), archive_name)
        files_to_archive = os.listdir(download_dir)
        total_files_to_archive = len(files_to_archive)
        archived_count = 0
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for filename in files_to_archive:
                file_path = os.path.join(download_dir, filename)
                zipf.write(file_path, arcname=filename)
                archived_count += 1
                progress = 80 + (archived_count / total_files_to_archive) * 20
                update_status(progress, f"Archiving {archived_count}/{total_files_to_archive}")
        with lock:
            jobs_dict[job_id] = {"status": "complete", "progress": 100, "filename": archive_name}
        logger.info(f"Archive created successfully: {archive_path}")
    except Exception as e:
        logger.error(f"Error during job {job_id}: {e}", exc_info=True)
        with lock:
            jobs_dict[job_id] = {"status": "error", "message": "An unexpected error occurred."}
    finally:
        shutil.rmtree(download_dir)