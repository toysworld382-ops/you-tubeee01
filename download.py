import os
import tempfile
import uuid
import json
from flask import Blueprint, jsonify, request, send_file
import yt_dlp
import threading
import time
from urllib.parse import urlparse
import re

download_bp = Blueprint('download', __name__)

# Store download status and file paths
download_status = {}
download_files = {}

# Quality format mappings
QUALITY_FORMATS = {
    'highest': 'best[height<=2160]/best',
    'high': 'best[height<=1080]/best',
    'medium': 'best[height<=720]/best',
    'low': 'best[height<=480]/best',
    'audio': 'bestaudio[ext=m4a]/bestaudio/best',
    'auto': 'best[ext=mp4]/best'
}

def is_valid_youtube_url(url):
    """Check if the URL is a valid YouTube URL"""
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+',
        r'(?:https?://)?youtu\.be/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/[\w-]+',
        r'(?:https?://)?(?:m\.)?youtube\.com/watch\?v=[\w-]+',
    ]
    
    for pattern in youtube_patterns:
        if re.match(pattern, url):
            return True
    return False

def get_video_info(url):
    """Extract video information without downloading"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'socket_timeout': 30,
            'retries': 3,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract available formats
            formats = []
            if 'formats' in info:
                seen_qualities = set()
                for fmt in info['formats']:
                    if fmt.get('vcodec') != 'none' and fmt.get('height'):
                        height = fmt.get('height')
                        quality_label = f"{height}p"
                        if quality_label not in seen_qualities:
                            formats.append({
                                'quality': quality_label,
                                'height': height,
                                'format_id': fmt.get('format_id'),
                                'ext': fmt.get('ext', 'mp4'),
                                'filesize': fmt.get('filesize'),
                                'fps': fmt.get('fps')
                            })
                            seen_qualities.add(quality_label)
                
                # Sort by quality (highest first)
                formats.sort(key=lambda x: x['height'], reverse=True)
            
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail'),
                'formats': formats[:10]  # Limit to top 10 qualities
            }
    except Exception as e:
        raise Exception(f"Failed to extract video info: {str(e)}")

def download_video(download_id, url, output_dir, quality='auto', audio_only=False):
    """Download video using yt-dlp with enhanced error handling"""
    try:
        download_status[download_id] = {
            'status': 'downloading', 
            'progress': 0, 
            'message': 'Initializing download...',
            'speed': '',
            'eta': ''
        }
        
        def progress_hook(d):
            try:
                if d['status'] == 'downloading':
                    # Calculate progress
                    progress = 0
                    if 'total_bytes' in d and d['total_bytes']:
                        progress = int((d['downloaded_bytes'] / d['total_bytes']) * 100)
                    elif 'total_bytes_estimate' in d and d['total_bytes_estimate']:
                        progress = int((d['downloaded_bytes'] / d['total_bytes_estimate']) * 100)
                    elif '_percent_str' in d:
                        try:
                            progress = int(float(d['_percent_str'].replace('%', '')))
                        except:
                            progress = 0
                    
                    # Get speed and ETA
                    speed = d.get('_speed_str', '')
                    eta = d.get('_eta_str', '')
                    
                    download_status[download_id].update({
                        'progress': min(progress, 99),  # Cap at 99% until finished
                        'message': f'Downloading... {progress}%',
                        'speed': speed,
                        'eta': eta
                    })
                    
                elif d['status'] == 'finished':
                    download_status[download_id].update({
                        'progress': 99,
                        'message': 'Processing and finalizing...',
                        'speed': '',
                        'eta': ''
                    })
                    
            except Exception as e:
                print(f"Progress hook error: {e}")
        
        # Enhanced yt-dlp options
        format_selector = QUALITY_FORMATS.get(quality, QUALITY_FORMATS['auto'])
        if audio_only:
            format_selector = QUALITY_FORMATS['audio']
        
        ydl_opts = {
            'format': format_selector,
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [progress_hook],
            'noplaylist': True,
            'extract_flat': False,
            'writethumbnail': False,
            'writeinfojson': False,
            'ignoreerrors': False,
            'no_warnings': False,
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 30,
            'http_chunk_size': 10485760,  # 10MB chunks for better speed
            'concurrent_fragment_downloads': 4,  # Parallel downloads
            'extractor_retries': 3,
            'file_access_retries': 3,
            'sleep_interval_requests': 0,
            'sleep_interval_subtitles': 0,
            'sleep_interval': 0,
            'max_sleep_interval': 0,
            # Headers to avoid blocking
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip,deflate',
                'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                'Keep-Alive': '300',
                'Connection': 'keep-alive',
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract info first
            download_status[download_id]['message'] = 'Extracting video information...'
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'video')
            duration = info.get('duration', 0)
            
            download_status[download_id].update({
                'title': title,
                'duration': duration,
                'message': 'Starting download...'
            })
            
            # Download the video
            ydl.download([url])
            
            # Find the downloaded file
            downloaded_file = None
            for file in os.listdir(output_dir):
                if file.endswith(('.mp4', '.mkv', '.webm', '.avi', '.m4a', '.mp3')):
                    file_path = os.path.join(output_dir, file)
                    file_size = os.path.getsize(file_path)
                    downloaded_file = {
                        'path': file_path,
                        'filename': file,
                        'title': title,
                        'size': file_size,
                        'quality': quality,
                        'audio_only': audio_only
                    }
                    break
            
            if downloaded_file:
                download_files[download_id] = downloaded_file
                download_status[download_id] = {
                    'status': 'completed',
                    'progress': 100,
                    'message': 'Download completed successfully!',
                    'title': title,
                    'duration': duration,
                    'file_size': downloaded_file['size'],
                    'quality': quality
                }
            else:
                raise Exception("Downloaded file not found")
            
    except Exception as e:
        error_message = str(e)
        # Clean up error messages
        if "Remote end closed connection" in error_message:
            error_message = "Connection lost during download. Please try again with a different quality or check your internet connection."
        elif "HTTP Error 403" in error_message:
            error_message = "Access denied. This video might be restricted or require authentication."
        elif "Video unavailable" in error_message:
            error_message = "This video is not available for download."
        elif "Private video" in error_message:
            error_message = "This is a private video and cannot be downloaded."
        
        download_status[download_id] = {
            'status': 'error',
            'progress': 0,
            'message': error_message
        }

@download_bp.route('/video-info', methods=['POST'])
def get_video_info_route():
    """Get video information and available qualities"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Invalid YouTube URL'}), 400
        
        info = get_video_info(url)
        return jsonify(info), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@download_bp.route('/download', methods=['POST'])
def start_download():
    """Start a YouTube video download with quality options"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        quality = data.get('quality', 'auto')
        audio_only = data.get('audio_only', False)
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        if not is_valid_youtube_url(url):
            return jsonify({'error': 'Invalid YouTube URL. Please provide a valid YouTube video URL.'}), 400
        
        if quality not in QUALITY_FORMATS:
            quality = 'auto'
        
        # Generate unique download ID
        download_id = str(uuid.uuid4())
        
        # Create temporary directory for this download
        temp_dir = tempfile.mkdtemp(prefix='ytdl_')
        
        # Start download in background thread
        thread = threading.Thread(
            target=download_video, 
            args=(download_id, url, temp_dir, quality, audio_only)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'download_id': download_id,
            'message': 'Download started',
            'status': 'started',
            'quality': quality,
            'audio_only': audio_only
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Failed to start download: {str(e)}'}), 500

@download_bp.route('/status/<download_id>', methods=['GET'])
def get_download_status(download_id):
    """Get download status with enhanced information"""
    if download_id not in download_status:
        return jsonify({'error': 'Download not found'}), 404
    
    status = download_status[download_id].copy()
    
    # Add file info if available
    if download_id in download_files:
        file_info = download_files[download_id]
        status['file_ready'] = True
        status['file_size'] = file_info.get('size', 0)
        status['filename'] = file_info.get('filename', '')
    else:
        status['file_ready'] = False
    
    return jsonify(status), 200

@download_bp.route('/file/<download_id>', methods=['GET'])
def download_file(download_id):
    """Download the completed file"""
    if download_id not in download_files:
        return jsonify({'error': 'File not found or download not completed'}), 404
    
    file_info = download_files[download_id]
    file_path = file_info['path']
    
    if not os.path.exists(file_path):
        return jsonify({'error': 'File no longer exists'}), 404
    
    # Clean up after sending file (delayed)
    def cleanup():
        time.sleep(30)  # Wait 30 seconds before cleanup
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            temp_dir = os.path.dirname(file_path)
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
            # Clean up status tracking
            if download_id in download_status:
                del download_status[download_id]
            if download_id in download_files:
                del download_files[download_id]
        except Exception as e:
            print(f"Cleanup error: {e}")
    
    cleanup_thread = threading.Thread(target=cleanup)
    cleanup_thread.daemon = True
    cleanup_thread.start()
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=file_info['filename']
    )

@download_bp.route('/cleanup/<download_id>', methods=['DELETE'])
def cleanup_download(download_id):
    """Manually cleanup download files and status"""
    try:
        if download_id in download_files:
            file_path = download_files[download_id]['path']
            if os.path.exists(file_path):
                os.remove(file_path)
            temp_dir = os.path.dirname(file_path)
            if os.path.exists(temp_dir) and not os.listdir(temp_dir):
                os.rmdir(temp_dir)
            del download_files[download_id]
        
        if download_id in download_status:
            del download_status[download_id]
        
        return jsonify({'message': 'Cleanup completed'}), 200
    except Exception as e:
        return jsonify({'error': f'Cleanup failed: {str(e)}'}), 500

@download_bp.route('/qualities', methods=['GET'])
def get_available_qualities():
    """Get list of available quality options"""
    qualities = [
        {'value': 'highest', 'label': '4K (2160p)', 'description': 'Highest available quality'},
        {'value': 'high', 'label': 'Full HD (1080p)', 'description': 'High quality, good for most uses'},
        {'value': 'medium', 'label': 'HD (720p)', 'description': 'Medium quality, smaller file size'},
        {'value': 'low', 'label': 'SD (480p)', 'description': 'Lower quality, fastest download'},
        {'value': 'audio', 'label': 'Audio Only', 'description': 'Extract audio only (M4A format)'},
        {'value': 'auto', 'label': 'Auto (Best)', 'description': 'Automatically select best quality'}
    ]
    
    return jsonify({'qualities': qualities}), 200

