from flask import Flask, request, jsonify
from flask_cors import CORS
from faster_whisper import WhisperModel
import os
import tempfile
import logging
from pathlib import Path

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

TEMP_DIR = '/tmp/whisper'
os.makedirs(TEMP_DIR, exist_ok=True)

current_model = None
current_model_name = None

ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'flac', 'webm', 'mp4'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_whisper_model(model_name='base'):
    global current_model, current_model_name
    
    if current_model is None or current_model_name != model_name:
        try:
            logger.info(f"Loading Whisper model: {model_name}")
            current_model = WhisperModel(model_name, device="cpu", compute_type="int8")
            current_model_name = model_name
            logger.info(f"Model {model_name} loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            raise
    
    return current_model


def format_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp format HH:MM:SS,mmm"""
    x = int(seconds)
    msecs = int((seconds - x) * 1000)
    hours = x // 3600
    mins = (x % 3600) // 60
    secs = x % 60
    return f"{hours:02}:{mins:02}:{secs:02},{msecs:03}"


def split_segment_into_chunks(segment, max_words=5):
    """
    Split a single Whisper segment into smaller chunks of max_words words.
    Interpolates timestamps proportionally based on word count.
    """
    text = segment['text'].strip()
    words = text.split()
    
    if len(words) <= max_words:
        return [segment]
    
    start = segment['start']
    end = segment['end']
    duration = end - start
    total_words = len(words)
    
    chunks = []
    i = 0
    while i < total_words:
        chunk_words = words[i:i + max_words]
        chunk_text = ' '.join(chunk_words)
        
        # Interpolate timestamps proportionally
        chunk_start = start + (i / total_words) * duration
        chunk_end = start + (min(i + max_words, total_words) / total_words) * duration
        
        chunks.append({
            'start': round(chunk_start, 3),
            'end': round(chunk_end, 3),
            'text': chunk_text
        })
        i += max_words
    
    return chunks


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'faster-whisper',
        'model_loaded': current_model is not None,
        'current_model': current_model_name
    }), 200


@app.route('/transcribe', methods=['POST'])
def transcribe():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'File not provided'}), 400

        file = request.files['file']
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not allowed_file(file.filename):
            return jsonify({
                'error': 'Unsupported file format',
                'allowed_formats': list(ALLOWED_EXTENSIONS)
            }), 400
        
        model_name = request.form.get('model', 'base')
        language = request.form.get('language', None)
        task = request.form.get('task', 'transcribe')
        # Max words per subtitle chunk (default 5, range 3-6 recommended)
        max_words = int(request.form.get('max_words', 5))

        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=Path(file.filename).suffix,
            dir=TEMP_DIR
        )
        
        try:
            file.save(temp_file.name)
            temp_file.close()
            
            logger.info(f"File saved: {temp_file.name}")

            model = get_whisper_model(model_name)
            
            logger.info(f"Starting transcription with model {model_name}, language: {language or 'auto'}, task: {task}, max_words: {max_words}")

            segments, info = model.transcribe(
                temp_file.name,
                language=language,
                task=task,
                beam_size=5,
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Build raw segments first
            raw_segments = []
            for segment in segments:
                raw_segments.append({
                    'start': round(segment.start, 3),
                    'end': round(segment.end, 3),
                    'text': segment.text.strip()
                })

            # Re-split all segments into short chunks
            short_segments = []
            for seg in raw_segments:
                chunks = split_segment_into_chunks(seg, max_words=max_words)
                short_segments.extend(chunks)

            # Build SRT and full text from short segments
            full_text = []
            result_segments = []
            srt_content = []

            for i, seg in enumerate(short_segments, start=1):
                start = seg['start']
                end = seg['end']
                text = seg['text']

                result_segments.append({'start': start, 'end': end, 'text': text})
                full_text.append(text)

                srt_content.append(f"{i}")
                srt_content.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
                srt_content.append(f"{text}\n")

            response = {
                'text': ' '.join(full_text),
                'language': info.language,
                'language_probability': round(info.language_probability, 2),
                'duration': round(info.duration, 2),
                'segments': result_segments,
                'model': model_name,
                'srt': '\n'.join(srt_content)
            }
            
            logger.info(f"Transcription done. Language: {info.language}, Duration: {info.duration:.2f}s, Chunks: {len(short_segments)}")

            return jsonify(response), 200
            
        finally:
            try:
                os.unlink(temp_file.name)
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {str(e)}")

    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/models', methods=['GET'])
def list_models():
    return jsonify({
        'models': [
            {'name': 'tiny',   'size': '~75 MB',  'description': 'Fastest, least accurate'},
            {'name': 'base',   'size': '~142 MB', 'description': 'Base model (default)'},
            {'name': 'small',  'size': '~466 MB', 'description': 'Small model, good accuracy'},
            {'name': 'medium', 'size': '~1.5 GB', 'description': 'Medium model, high accuracy'},
            {'name': 'large',  'size': '~2.9 GB', 'description': 'Largest and most accurate model'}
        ]
    }), 200


@app.route('/info', methods=['GET'])
def info():
    return jsonify({
        'service': 'Whisper Audio Transcription Service (faster-whisper)',
        'version': '1.1.0',
        'description': 'API for transcribing audio files using faster-whisper with short subtitle chunks',
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'endpoints': {
            '/health':     'GET - Service health check',
            '/transcribe': 'POST - Transcribe an audio file',
            '/models':     'GET - List available models',
            '/info':       'GET - Service information'
        }
    }), 200


if __name__ == '__main__':
    logger.info("Starting Whisper Transcription Service on port 8081")
    app.run(host='0.0.0.0', port=8081, debug=False)