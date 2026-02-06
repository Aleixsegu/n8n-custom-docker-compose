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

# Temp directory for processing
TEMP_DIR = '/tmp/whisper'
os.makedirs(TEMP_DIR, exist_ok=True)

# Global variables to cache model
current_model = None
current_model_name = None

# Supported file extensions
ALLOWED_EXTENSIONS = {'mp3', 'wav', 'm4a', 'ogg', 'flac', 'webm', 'mp4'}

def allowed_file(filename):
    """Check allowed file extension"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_whisper_model(model_name='base'):
    """Get or initialize Whisper model"""
    global current_model, current_model_name
    
    if current_model is None or current_model_name != model_name:
        try:
            logger.info(f"Loading Whisper model: {model_name}")
            # device="cpu" for CPU, change to "cuda" for GPU
            # compute_type="int8" to reduce memory usage
            current_model = WhisperModel(model_name, device="cpu", compute_type="int8")
            current_model_name = model_name
            logger.info(f"Model {model_name} loaded successfully")
        except Exception as e:
            logger.error(f"Error loading model: {str(e)}")
            raise
    
    return current_model

@app.route('/health', methods=['GET'])
def health():
    """Service health check"""
    return jsonify({
        'status': 'healthy',
        'service': 'faster-whisper',
        'model_loaded': current_model is not None,
        'current_model': current_model_name
    }), 200

@app.route('/transcribe', methods=['POST'])
def transcribe():
    """
    Transcribe an audio file

    Accepts:
    - file: MP3/WAV/M4A file (multipart/form-data)
    - model: model name (optional, default 'base')
      Available models: tiny, base, small, medium, large
    - language: language code (optional, auto-detect if not provided)
    - task: transcribe or translate (optional, default transcribe)

    Returns:
    - text: transcribed text
    - segments: list of segments with timestamps
    - language: detected language
    """
    try:
        # Check for file
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
        
        # Get parameters
        model_name = request.form.get('model', 'base')
        language = request.form.get('language', None)  # None for auto-detect
        task = request.form.get('task', 'transcribe')  # transcribe or translate

        # Save temp file
        temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=Path(file.filename).suffix,
            dir=TEMP_DIR
        )
        
        try:
            file.save(temp_file.name)
            temp_file.close()
            
            logger.info(f"File saved: {temp_file.name}")

            # Get model
            model = get_whisper_model(model_name)
            
            # Transcription
            logger.info(f"Starting transcription of '{file.filename}' with model {model_name}, language: {language or 'auto'}, task: {task}")

            segments, info = model.transcribe(
                temp_file.name,
                language=language,
                task=task,
                beam_size=5,
                vad_filter=True,  # Voice Activity Detection for better quality
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            
            # Build result
            result_segments = []
            full_text = []
            
            for segment in segments:
                result_segments.append({
                    'start': round(segment.start, 2),
                    'end': round(segment.end, 2),
                    'text': segment.text.strip()
                })
                full_text.append(segment.text.strip())
            
            response = {
                'text': ' '.join(full_text),
                'language': info.language,
                'language_probability': round(info.language_probability, 2),
                'duration': round(info.duration, 2),
                'segments': result_segments,
                'model': model_name
            }
            
            logger.info(f"Transcription completed successfully. Language: {info.language}, Duration: {info.duration:.2f}s")

            return jsonify(response), 200
            
        finally:
            # Remove temp file
            try:
                os.unlink(temp_file.name)
                logger.info(f"Temporary file removed: {temp_file.name}")
            except Exception as e:
                logger.warning(f"Failed to remove temporary file: {str(e)}")

    except Exception as e:
        logger.error(f"Error during transcription: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/models', methods=['GET'])
def list_models():
    """List available Whisper models"""
    return jsonify({
        'models': [
            {
                'name': 'tiny',
                'size': '~75 MB',
                'description': 'Fastest, least accurate'
            },
            {
                'name': 'base',
                'size': '~142 MB',
                'description': 'Base model (default)'
            },
            {
                'name': 'small',
                'size': '~466 MB',
                'description': 'Small model, good accuracy'
            },
            {
                'name': 'medium',
                'size': '~1.5 GB',
                'description': 'Medium model, high accuracy'
            },
            {
                'name': 'large',
                'size': '~2.9 GB',
                'description': 'Largest and most accurate model'
            }
        ]
    }), 200

@app.route('/info', methods=['GET'])
def info():
    """Service information"""
    return jsonify({
        'service': 'Whisper Audio Transcription Service (faster-whisper)',
        'version': '1.0.0',
        'description': 'API for transcribing audio files using faster-whisper',
        'supported_formats': list(ALLOWED_EXTENSIONS),
        'endpoints': {
            '/health': 'GET - Service health check',
            '/transcribe': 'POST - Transcribe an audio file',
            '/models': 'GET - List available models',
            '/info': 'GET - Service information'
        }
    }), 200

if __name__ == '__main__':
    logger.info("Starting Whisper Transcription Service on port 8082")
    app.run(host='0.0.0.0', port=8082, debug=False)
