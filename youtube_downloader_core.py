import os
import uuid
import json
import time
import re
from flask import Flask, request, jsonify, send_file, Response
from yt_dlp import YoutubeDL

# --- Flask Application Setup ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "your-secret-key-here")

# Directory to store downloaded videos temporarily
DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

# Dictionary to store download progress and status
download_status = {}

# --- Helper Functions ---
def sanitize_filename(filename):
    """Sanitizes a string to be safe for use as a filename."""
    filename = re.sub(r"[\\/:*?"<>|]", "_", filename)  # Replace invalid characters with underscore
    filename = re.sub(r"\s+", " ", filename).strip()  # Replace multiple spaces with single space
    return filename

def get_video_info(url):
    """Fetches video information using yt-dlp."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "force_generic_extractor": True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title"),
                "duration": time.strftime("%H:%M:%S", time.gmtime(info.get("duration", 0))),
                "uploader": info.get("uploader"),
                "view_count": f"{info.get("view_count", 0):,}",
                "thumbnail": info.get("thumbnail"),
                "formats": info.get("formats", []),
            }
    except Exception as e:
        return {"error": str(e)}

class DownloadProgressHook:
    """Custom hook to update download progress."""
    def __init__(self, download_id):
        self.download_id = download_id

    def __call__(self, d):
        if d["status"] == "downloading":
            percent = d.get("downloaded_bytes", 0) / d.get("total_bytes", 1) * 100
            speed = d.get("speed")
            eta = d.get("eta")
            download_status[self.download_id] = {
                "status": "downloading",
                "progress": percent,
                "speed": f"{speed / 1024 / 1024:.2f} MiB/s" if speed else "N/A",
                "eta": f"{eta}s" if eta else "N/A",
                "status_text": d.get("_percent_str", "").strip() + " " + d.get("_eta_str", "").strip(),
                "title": download_status[self.download_id].get("title", ""),
            }
        elif d["status"] == "finished":
            download_status[self.download_id] = {
                "status": "completed",
                "progress": 100,
                "filepath": d["filename"],
                "title": download_status[self.download_id].get("title", ""),
            }
        elif d["status"] == "error":
            download_status[self.download_id] = {
                "status": "error",
                "error": d.get("error", "An unknown error occurred during download."),
                "title": download_status[self.download_id].get("title", ""),
            }

# --- API Endpoints ---
@app.route("/api/video-info", methods=["POST"])
def video_info():
    url = request.json.get("url")
    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    info = get_video_info(url)
    if "error" in info:
        return jsonify({"success": False, "error": info["error"]}), 500
    
    return jsonify({"success": True, "info": info})

@app.route("/api/download", methods=["POST"])
def download_video():
    url = request.json.get("url")
    quality = request.json.get("quality", "auto")

    if not url:
        return jsonify({"success": False, "error": "URL is required"}), 400

    download_id = str(uuid.uuid4())
    download_status[download_id] = {"status": "pending", "progress": 0, "title": ""}

    def download_thread():
        try:
            info = get_video_info(url)
            if "error" in info:
                download_status[download_id] = {"status": "error", "error": info["error"]}
                return
            
            download_status[download_id]["title"] = info.get("title", "Unknown Video")
            
            output_template = os.path.join(DOWNLOAD_DIR, f"{sanitize_filename(info['title'])}.%(ext)s")

            ydl_opts = {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best" if quality == "auto" else f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best",
                "outtmpl": output_template,
                "progress_hooks": [DownloadProgressHook(download_id)],
                "merge_output_format": "mp4",
                "retries": 5,
                "fragment_retries": 5,
                "concurrent_fragment_downloads": 5,
                "buffer_size": "1024KiB",
                "http_chunk_size": "10485760", # 10MB
                "no_warnings": True,
                "ignoreerrors": True,
                "external_downloader": "aria2c",
                "external_downloader_args": ["-x", "16", "-s", "16", "-k", "1M"],
            }
            if quality == "audio":
                ydl_opts["format"] = "bestaudio/best"
                ydl_opts["postprocessors"] = [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                    "preferredquality": "192",
                }]
                output_template = os.path.join(DOWNLOAD_DIR, f"{sanitize_filename(info['title'])}.%(ext)s")
                ydl_opts["outtmpl"] = output_template

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        except Exception as e:
            download_status[download_id] = {"status": "error", "error": str(e)}

    import threading
    threading.Thread(target=download_thread).start()

    return jsonify({"success": True, "download_id": download_id})

@app.route("/api/status/<download_id>")
def download_status_check(download_id):
    status = download_status.get(download_id)
    if not status:
        return jsonify({"status": "error", "error": "Download ID not found"}), 404
    return jsonify(status)

@app.route("/api/file/<download_id>")
def serve_downloaded_file(download_id):
    status = download_status.get(download_id)
    if not status or status["status"] != "completed":
        return jsonify({"error": "File not ready or download failed"}), 404

    filepath = status["filepath"]
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found on server"}), 404

    # Clean up after sending the file
    @app.after_request
    def remove_file(response):
        try:
            os.remove(filepath)
            del download_status[download_id]
        except Exception as e:
            print(f"Error removing downloaded file {filepath}: {e}")
        return response

    return send_file(filepath, as_attachment=True)

# --- Main Execution ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)


