from flask import Flask, request, jsonify
from flask_cors import CORS
from llama_cpp import Llama
from huggingface_hub import hf_hub_download
import os
import logging

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
# Using Llama-3-8B-Instruct-GGUF (Quantized 8-bit or 4-bit)
# We default to Q4_K_M (4-bit medium) which balances speed/quality and RAM usage (~5GB RAM)
REPO_ID = "QuantFactory/Meta-Llama-3-8B-Instruct-GGUF"
FILENAME = "Meta-Llama-3-8B-Instruct.Q4_K_M.gguf"
MODEL_PATH = f"/root/.cache/huggingface/{FILENAME}"

# Global model variable
llm = None

def load_model():
    """Load the model if not already loaded"""
    global llm
    if llm is None:
        try:
            logger.info("Checking for model file...")
            if not os.path.exists(MODEL_PATH):
                logger.info(f"Downloading {FILENAME} from {REPO_ID}...")
                hf_hub_download(
                    repo_id=REPO_ID,
                    filename=FILENAME,
                    local_dir="/root/.cache/huggingface",
                    local_dir_use_symlinks=False
                )
                logger.info("Download complete.")
            else:
                logger.info(f"Model found locally at {MODEL_PATH}")
            
            logger.info("Loading Llama model to memory...")
            # n_ctx=2048 or 4096 (context window)
            # n_threads=None (defaults to cpu count)
            llm = Llama(
                model_path=MODEL_PATH,
                n_ctx=4096,
                n_gpu_layers=0, # 0 for CPU only
                verbose=False
            )
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model: {str(e)}")
            raise e
            
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'llm-service',
        'model_loaded': llm is not None,
        'model_name': FILENAME
    }), 200

@app.route('/generate', methods=['POST'])
def generate():
    """
    Simple completion endpoint.
    Body: { "prompt": "Why is the sky blue?", "max_tokens": 128, ... }
    """
    try:
        if llm is None:
            load_model()

        logger.info("Starting generation.")
   
        data = request.get_json()
        prompt = data.get('prompt', '')
        max_tokens = data.get('max_tokens', 256)
        temperature = data.get('temperature', 0.7)
        stop = data.get('stop', ["<|eot_id|>"]) # Llama 3 specific stop token
        
        output = llm(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            echo=False
        )

        logger.info("Generation completed successfully.")
        
        return jsonify({
            'text': output['choices'][0]['text'],
            'usage': output['usage']
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/chat', methods=['POST'])
def chat():
    """
    Chat completion endpoint compatible with Llama 3 chat format.
    Body: { 
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"}
        ],
        ... 
    }
    """
    try:
        if llm is None:
            load_model()

        logger.info("Starting chat.")

        data = request.get_json()
        messages = data.get('messages', [])
        max_tokens = data.get('max_tokens', 512)
        temperature = data.get('temperature', 0.7)
        
        # Llama-cpp-python has a create_chat_completion method that handles formatting automatically
        response = llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        logger.info("Chat completed successfully.")

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Pre-load on start if possible, or lazy load
    try:
        load_model()
    except Exception as e:
        logger.warning(f"Could not preload model on startup: {e}")
        
    logger.info("Starting LLM Service on port 8083")
    app.run(host='0.0.0.0', port=8083, debug=False)
