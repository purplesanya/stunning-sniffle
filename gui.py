import os
import sys
import requests
import py7zr
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QProgressBar,
    QComboBox,
)
from concurrent.futures import ThreadPoolExecutor, as_completed


class AuthorSearchApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Author Search and Download")
        self.setGeometry(100, 100, 400, 300)

        # Initialize download directory path
        self.download_path = ""
        self.author_id = None

        # Create layout
        self.layout = QVBoxLayout()

        # Create widgets
        self.label = QLabel("Enter Author Name:")
        self.layout.addWidget(self.label)

        self.input_name = QLineEdit()
        self.layout.addWidget(self.input_name)

        self.browse_button = QPushButton("Choose Download Directory")
        self.browse_button.clicked.connect(self.choose_directory)
        self.layout.addWidget(self.browse_button)

        self.search_button = QPushButton("Search Authors")
        self.search_button.clicked.connect(self.search_authors)
        self.layout.addWidget(self.search_button)

        self.author_combo_box = QComboBox()
        self.layout.addWidget(self.author_combo_box)

        self.download_button = QPushButton("Download Books")
        self.download_button.clicked.connect(self.download_books)
        self.layout.addWidget(self.download_button)

        self.result_label = QLabel("")
        self.layout.addWidget(self.result_label)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.layout.addWidget(self.progress_bar)

        self.setLayout(self.layout)

    def choose_directory(self):
        """ Open a dialog to choose the download directory. """
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if directory:
            self.download_path = directory
            QMessageBox.information(self, "Directory Selected", f"Download path set to: {self.download_path}")

    def search_authors(self):
        """ Search for authors based on the input name and populate the combo box with results. """
        author_name = self.input_name.text().strip()
        if not author_name:
            QMessageBox.warning(self, "Input Error", "Please enter an author name.")
            return

        url = f"https://flibusta.is/booksearch?ask={author_name}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find the list of authors
            author_section = soup.find("h3", string=lambda x: x and "Найденные писатели" in x)
            if not author_section:
                self.result_label.setText("No authors found.")
                return

            author_links = author_section.find_next_sibling("ul").find_all("a")
            self.author_combo_box.clear()
            self.author_combo_box.addItem("Select an Author", None)

            # Populate combo box with author names and their IDs
            for link in author_links:
                author_id = link["href"].split('/')[-1]
                author_name = self.get_author_name(author_id)
                self.author_combo_box.addItem(author_name, author_id)

        except requests.RequestException as e:
            QMessageBox.warning(self, "Request Error", f"Error fetching author list: {str(e)}")

    def get_author_name(self, author_id):
        """ Get the author's name from their page. """
        url = f"https://flibusta.is/a/{author_id}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title_tag = soup.find("h1", class_="title")
            if title_tag:
                return title_tag.text.strip()
        except requests.RequestException:
            return "Unknown Author"
        return "Unknown Author"

    def find_epub_links(self, author_id):
        """ Fetch the author's page and parse for all EPUB links. """
        url = f"https://flibusta.is/a/{author_id}"
        epub_links = []

        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            # Find all <a> tags with '(epub)' text
            for epub_tag in soup.find_all("a", string="(epub)"):
                if 'href' in epub_tag.attrs:
                    epub_link = f"https://flibusta.is{epub_tag['href']}"
                    epub_links.append(epub_link)
        except requests.RequestException as e:
            QMessageBox.warning(self, "Request Error", f"Error fetching page: {str(e)}")

        return epub_links

    def download_books(self):
        """ Download EPUB books for the selected author. """
        author_id = self.author_combo_box.currentData()
        if not author_id:
            QMessageBox.warning(self, "Selection Error", "Please select an author.")
            return

        if not self.download_path:
            QMessageBox.warning(self, "Directory Error", "Please choose a download directory.")
            return

        epub_links = self.find_epub_links(author_id)
        if not epub_links:
            self.result_label.setText("No EPUB links found.")
            return

        # Reset progress bar and download status
        self.progress_bar.setValue(0)
        self.result_label.setText("Downloading EPUB files...")

        temp_dir = os.path.join(self.download_path, "temp_epubs")
        os.makedirs(temp_dir, exist_ok=True)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(self.download_epub, epub_link, temp_dir): epub_link for epub_link in epub_links}
            total_files = len(futures)

            for i, future in enumerate(as_completed(futures), 1):
                try:
                    future.result()  # Wait for the download to finish
                    self.progress_bar.setValue(int((i / total_files) * 100))
                except Exception as e:
                    self.result_label.setText(f"Error during download: {str(e)}")
                    return

        self.create_7z_archive(temp_dir, self.get_author_name(author_id))
        self.clean_temp_directory(temp_dir)
        self.result_label.setText("Finished downloading EPUB files.")

    def download_epub(self, epub_link, temp_dir):
        """ Download an EPUB file and save it in the temporary directory. """
        book_id = epub_link.split('/')[-2]
        book_title = self.get_book_title(book_id)

        if book_title:
            filename = f"{book_title}.epub".replace("/", "-")
            file_path = os.path.join(temp_dir, filename)
            response = requests.get(epub_link)

            if response.status_code == 200:
                with open(file_path, 'wb') as file:
                    file.write(response.content)

    def get_book_title(self, book_id):
        """ Fetch the book title using the book ID. """
        url = f"https://flibusta.is/b/{book_id}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

            title_tag = soup.find("h1", class_="title")
            if title_tag:
                return title_tag.text.strip()
        except requests.RequestException:
            return "Untitled"
        return "Untitled"

    def create_7z_archive(self, temp_dir, author_name):
        """ Create a 7z archive of the downloaded EPUB files. """
        archive_name = f"{author_name}.7z"
        archive_path = os.path.join(self.download_path, archive_name)

        with py7zr.SevenZipFile(archive_path, 'w') as archive:
            for file_name in os.listdir(temp_dir):
                archive.write(os.path.join(temp_dir, file_name), file_name)

    def clean_temp_directory(self, temp_dir):
        """ Remove the temporary directory after archiving. """
        for file_name in os.listdir(temp_dir):
            os.remove(os.path.join(temp_dir, file_name))
        os.rmdir(temp_dir)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AuthorSearchApp()
    window.show()
    sys.exit(app.exec())
