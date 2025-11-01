# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from flibusta_utils import (
    search_authors, find_books, download_books_to_disk, search_books,
    download_single_book # <-- Import the new function
)
from datetime import datetime, timedelta
import logging
import uuid
import threading
import tempfile
import os

app = Flask(__name__)

# ... (Logging, cache, JOBS, and lock setup are unchanged) ...
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
cache = {}
CACHE_DURATION = timedelta(hours=1)
JOBS = {}
JOBS_LOCK = threading.Lock()

def get_cached(key):
    if key in cache:
        value, timestamp = cache[key]
        if datetime.now() - timestamp < CACHE_DURATION:
            return value
        else:
            del cache[key]
    return None
def set_cached(key, value):
    cache[key] = (value, datetime.now())

# ... (The / route is unchanged) ...
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        if not query:
            return render_template("index.html", error="Please enter a search query.")
        try:
            author_cache_key = f"author_search:{query.lower()}"
            authors = get_cached(author_cache_key)
            if authors is None:
                authors = search_authors(query)
                set_cached(author_cache_key, authors)
            book_cache_key = f"book_search:{query.lower()}"
            books_found = get_cached(book_cache_key)
            if books_found is None:
                books_found = search_books(query)
                set_cached(book_cache_key, books_found)
            return render_template("results.html",
                                   authors=authors,
                                   books=books_found,
                                   search_query=query)
        except Exception as e:
            logger.error(f"Error during unified search for '{query}': {str(e)}", exc_info=True)
            return render_template("index.html", error="An error occurred during the search. Please try again.")
    return render_template("index.html")

# *** NEW ROUTE TO PROXY SINGLE BOOK DOWNLOADS ***
@app.route("/download-book/<book_id>/<file_format>")
def download_book_proxy(book_id, file_format):
    title = request.args.get('title', 'book') # Get title from query param
    if file_format not in ['epub', 'fb2', 'mobi']:
        return "Invalid format", 400
    try:
        filename, buffer, mimetype = download_single_book(book_id, file_format, title)
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype
        )
    except Exception as e:
        logger.error(f"Failed to serve single book download for {book_id}: {e}")
        return "Download failed.", 500

# ... (The rest of the routes: /books, /api/books, /start-download, etc., are unchanged) ...
@app.route("/books/<author_id>")
def books(author_id):
    file_format = request.args.get("format", "epub").lower()
    if file_format not in ["epub", "fb2", "mobi"]:
        file_format = "epub"
    try:
        cache_key = f"books:{author_id}:{file_format}"
        books_list = get_cached(cache_key)
        if books_list is None:
            books_list = find_books(author_id, file_format)
            set_cached(cache_key, books_list)
        author_name = None
        for key in cache.keys():
            if key.startswith("author_search:"):
                authors_list_cached, _ = cache[key]
                for name, aid in authors_list_cached:
                    if aid == author_id:
                        author_name = name
                        break
                if author_name:
                    break
        return render_template("books.html", books=books_list, author_id=author_id,
                               file_format=file_format, author_name=author_name)
    except Exception as e:
        logger.error(f"Error fetching books for author {author_id}: {str(e)}")
        return render_template("books.html", books=[], author_id=author_id,
                               file_format=file_format, error="Error loading books")
@app.route("/api/books/<author_id>")
def api_books(author_id):
    file_format = request.args.get("format", "epub").lower()
    if file_format not in ["epub", "fb2", "mobi"]:
        return jsonify({"error": "Invalid format", "books": []}), 400
    try:
        cache_key = f"books:{author_id}:{file_format}"
        books_list = get_cached(cache_key)
        if books_list is None:
            books_list = find_books(author_id, file_format)
            set_cached(cache_key, books_list)
        return jsonify({"books": books_list, "count": len(books_list)})
    except Exception as e:
        logger.error(f"API error fetching books for author {author_id}: {str(e)}")
        return jsonify({"error": "Failed to fetch books", "books": []}), 500

@app.route("/start-download", methods=["POST"])
def start_download_job():
    data = request.json
    book_links = data.get("book_links", [])
    book_titles = data.get("book_titles", [])
    file_format = data.get("format", "epub")
    author_name = data.get("author_name", "")
    if not book_links or len(book_links) != len(book_titles):
        return jsonify({"error": "Invalid book data"}), 400
    job_id = str(uuid.uuid4())
    books_to_download = list(zip(book_titles, book_links))
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", "progress": 0, "message": "Job received"}
    thread = threading.Thread(
        target=download_books_to_disk,
        args=(job_id, books_to_download, file_format, author_name, JOBS, JOBS_LOCK)
    )
    thread.start()
    return jsonify({"job_id": job_id})

@app.route("/job-status/<job_id>")
def get_job_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found"}), 404
    return jsonify(job)

@app.route("/fetch/<filename>")
def fetch_file(filename):
    if ".." in filename or filename.startswith("/"):
        return "Invalid filename", 400
    return send_from_directory(tempfile.gettempdir(), filename, as_attachment=True)

@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", error="Page not found"), 404

@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {str(e)}")
    return render_template("index.html", error="An internal error occurred"), 500

if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")