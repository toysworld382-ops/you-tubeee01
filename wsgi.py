"""
WSGI entry point for YouTube Downloader Flask application.
This file is used by production WSGI servers like Gunicorn.
"""

import os
import sys

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import app

if __name__ == "__main__":
    app.run()

