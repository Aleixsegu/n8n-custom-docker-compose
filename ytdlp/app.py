from flask import Flask, request, jsonify
from flask_cors import CORS
import yt_dlp
import os

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = '/downloads'

@app.route('/health', methods=['GET'])
def health():
    """Service health check"""
    return jsonify({'status': 'healthy', 'service': 'yt-dlp'}), 200

@app.route('/info', methods=['POST'])
def get_video_info():
    """Get video info without downloading"""
    try:
        data = request.get_json()
        url = data.get('url')
        
        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            # Add options to bypass some YouTube restrictions
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            },
            # Add User-Agent
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract main information
            video_info = {
                'title': info.get('title'),
                'description': info.get('description'),
                'duration': info.get('duration'),
                'uploader': info.get('uploader'),
                'upload_date': info.get('upload_date'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'thumbnail': info.get('thumbnail'),
                'formats': [
                    {
                        'format_id': f.get('format_id'),
                        'ext': f.get('ext'),
                        'resolution': f.get('resolution'),
                        'filesize': f.get('filesize'),
                    }
                    for f in info.get('formats', [])
                ]
            }
            
        return jsonify(video_info), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download_video():
    """Download video or audio"""
    try:
        data = request.get_json()
        url = data.get('url')
        format_type = data.get('format', 'video')  # 'video', 'audio', or 'best'
        quality = data.get('quality', 'best')  # 'best', '1080p', '720p', etc.

        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        # First get video info without downloading
        info_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }
        
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_id = info.get('id')
            video_title = info.get('title')
        
        # Determine expected filename and extension
        if format_type == 'audio':
            expected_ext = '.mp3'
        else:
            expected_ext = '.webm'  # default extension for video

        expected_filename = f"{video_id}{expected_ext}"
        expected_path = os.path.join(DOWNLOAD_DIR, expected_filename)
        
        # Check if file exists on disk
        file_exists = os.path.exists(expected_path)
        
        if file_exists:
            # File already exists, return info without downloading
            return jsonify({
                'status': 'success',
                'filename': expected_filename,
                'path': expected_path,
                'title': video_title,
                'downloaded': False,
            }), 200
        
        # File doesn't exist, proceed to download
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'quiet': False,
            'no_warnings': False,
            # Add options to bypass some YouTube restrictions
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web']
                    # Avoid 'skip' to not block available formats
                }
            },
            # Add User-Agent
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            },
            # Fail on errors for more stable behavior
            'ignoreerrors': False,
            # Allow using available formats
            'allow_unplayable_formats': False,
        }
        
        # Format selection depending on type
        if format_type == 'audio':
            ydl_opts.update({
                # Simple and reliable audio option
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        elif format_type == 'video':
            # Use the simplest reliable selector
            ydl_opts['format'] = 'best'
            # Optionally limit height if quality specified
            if quality != 'best':
                height = quality.replace("p", "")
                ydl_opts['format'] = f'best[height<={height}]/best'
        else:
            ydl_opts['format'] = 'best'
        
        # Download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # If audio, filename changes after postprocessing
            if format_type == 'audio':
                filename = os.path.splitext(filename)[0] + '.mp3'
            
        return jsonify({
            'status': 'success',
            'filename': os.path.basename(filename),
            'path': filename,
            'title': info.get('title'),
            'downloaded': True,
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download-transcript', methods=['POST'])
def download_transcript():
    """Download video subtitles/transcript"""
    try:
        data = request.get_json()
        url = data.get('url')
        lang = data.get('lang', 'en')  # subtitle language

        if not url:
            return jsonify({'error': 'URL is required'}), 400
        
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': [lang],
            'subtitlesformat': 'json3',
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Get subtitles
            subtitles = info.get('subtitles', {})
            automatic_captions = info.get('automatic_captions', {})
            
            available_subs = {}
            if lang in subtitles:
                available_subs['manual'] = subtitles[lang]
            if lang in automatic_captions:
                available_subs['automatic'] = automatic_captions[lang]
            
            if not available_subs:
                return jsonify({
                    'error': f'No subtitles available for language: {lang}',
                    'available_languages': list(subtitles.keys()) + list(automatic_captions.keys())
                }), 404
            
        return jsonify({
            'status': 'success',
            'subtitles': available_subs,
            'title': info.get('title'),
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create downloads directory if missing
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    
    # Start server
    app.run(host='0.0.0.0', port=8082, debug=False)
