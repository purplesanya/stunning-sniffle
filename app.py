# app.py
from flask import Flask, render_template, request, jsonify, send_from_directory
from flibusta_utils import search_authors, find_books, download_books_to_disk
from functools import lru_cache
from datetime import datetime, timedelta
import logging
import uuid
import threading
import tempfile
import os

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple in-memory cache with expiration
cache = {}
CACHE_DURATION = timedelta(hours=1)

# This dictionary will hold the status of our background jobs.
# In a real multi-worker setup, you'd use Redis or a database for this.
# For Render's single-worker free tier, this is okay.
JOBS = {}


def get_cached(key):
    """Get value from cache if not expired"""
    if key in cache:
        value, timestamp = cache[key]
        if datetime.now() - timestamp < CACHE_DURATION:
            return value
        else:
            del cache[key]
    return None


def set_cached(key, value):
    """Set value in cache with timestamp"""
    cache[key] = (value, datetime.now())


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        author = request.form.get("author", "").strip()

        if not author:
            return render_template("index.html", authors=None, error="Please enter an author name")

        try:
            # Check cache first
            cache_key = f"author_search:{author.lower()}"
            authors = get_cached(cache_key)

            if authors is None:
                logger.info(f"Searching for author: {author}")
                authors = search_authors(author)
                set_cached(cache_key, authors)
            else:
                logger.info(f"Using cached results for: {author}")

            if not authors:
                return render_template("index.html", authors=None, author_query=author,
                                       error=f"No authors found for '{author}'")

            return render_template("index.html", authors=authors, author_query=author)

        except Exception as e:
            logger.error(f"Error searching for author '{author}': {str(e)}")
            return render_template("index.html", authors=None,
                                   error="An error occurred while searching. Please try again.")

    return render_template("index.html", authors=None)


@app.route("/books/<author_id>")
def books(author_id):
    file_format = request.args.get("format", "epub").lower()

    # Validate format
    if file_format not in ["epub", "fb2", "mobi"]:
        file_format = "epub"

    try:
        # Check cache first
        cache_key = f"books:{author_id}:{file_format}"
        books = get_cached(cache_key)

        if books is None:
            logger.info(f"Fetching books for author {author_id} in format {file_format}")
            books = find_books(author_id, file_format)
            set_cached(cache_key, books)
        else:
            logger.info(f"Using cached books for author {author_id}")

        # Try to get author name from cache
        author_name = None
        for key in cache.keys():
            if key.startswith("author_search:"):
                authors, _ = cache[key]
                for name, aid in authors:
                    if aid == author_id:
                        author_name = name
                        break
                if author_name:
                    break

        return render_template("books.html", books=books, author_id=author_id,
                               file_format=file_format, author_name=author_name)

    except Exception as e:
        logger.error(f"Error fetching books for author {author_id}: {str(e)}")
        return render_template("books.html", books=[], author_id=author_id,
                               file_format=file_format, error="Error loading books")


@app.route("/api/books/<author_id>")
def api_books(author_id):
    """AJAX endpoint to fetch book list for a format."""
    file_format = request.args.get("format", "epub").lower()

    # Validate format
    if file_format not in ["epub", "fb2", "mobi"]:
        return jsonify({"error": "Invalid format", "books": []}), 400

    try:
        # Check cache first
        cache_key = f"books:{author_id}:{file_format}"
        books = get_cached(cache_key)

        if books is None:
            logger.info(f"API: Fetching books for author {author_id} in format {file_format}")
            books = find_books(author_id, file_format)
            set_cached(cache_key, books)
        else:
            logger.info(f"API: Using cached books for author {author_id}")

        return jsonify({"books": books, "count": len(books)})

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
    books = list(zip(book_titles, book_links))

    # Set initial status
    JOBS[job_id] = {"status": "pending", "progress": 0, "message": "Job received"}

    # Start the download process in a background thread
    thread = threading.Thread(
        target=download_books_to_disk,
        args=(job_id, books, file_format, author_name, JOBS)
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.route("/job-status/<job_id>")
def get_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found"}), 404
    return jsonify(job)


@app.route("/fetch/<filename>")
def fetch_file(filename):
    # Security: Ensure filename is safe
    if ".." in filename or filename.startswith("/"):
        return "Invalid filename", 400
    
    # Serve the file from the system's temporary directory
    return send_from_directory(tempfile.gettempdir(), filename, as_attachment=True)


@app.route("/api/cache/clear", methods=["POST"])
def clear_cache():
    """Admin endpoint to clear cache"""
    global cache
    cache = {}
    logger.info("Cache cleared")
    return jsonify({"message": "Cache cleared successfully"})


@app.route("/api/cache/stats")
def cache_stats():
    """Get cache statistics"""
    total_entries = len(cache)
    cache_keys = list(cache.keys())
    return jsonify({
        "total_entries": total_entries,
        "keys": cache_keys
    })


@app.errorhandler(404)
def not_found(e):
    return render_template("index.html", error="Page not found"), 404


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Server error: {str(e)}")
    return render_template("index.html", error="An internal error occurred"), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000, host="0.0.0.0")
