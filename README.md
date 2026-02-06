# n8n Custom Docker Compose

This project sets up a local environment with **n8n** and a custom **Whisper API** service (using `faster-whisper`) running in Docker containers.

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose installed on your machine.

## Quick Start

1. **Clone/Open** this repository.
2. **Start the services**:
   ```bash
   docker-compose up -d --build
   ```
   This will build the Whisper Python service and pull the n8n image.

3. **Access n8n**:
   Open [http://localhost:5678](http://localhost:5678) in your browser.

## Services

| Service | Address | Description |
|---------|---------|-------------|
| **n8n** | `http://localhost:5678` | Workflow automation tool. |
| **Whisper API** | `http://localhost:8082` | Custom API for OpenAI's Whisper model. |

> **Note**: Within the Docker network, n8n can access the Whisper service using the hostname `whisper:8082`.

## How to use Whisper in n8n

You can transcribe audio files directly within your n8n workflows using the **HTTP Request** node.

### Node Configuration

1. **Add an "HTTP Request" node**.
2. Configure it with the following settings:
   - **Method**: `POST`
   - **URL**: `http://whisper:8082/transcribe`
   - **Authentication**: `None`
   - **Send Body**: Toggle `On`
   - **Body Content Type**: `Multipart-form-data`
3. **Parameters** (under Body Parameters):
   - **Parameter Type**: `Form-Data`
   - **Name**: `file`
   - **Input Type**: `Binary File`
   - **Value**: Pick the binary property name from your previous node (usually `data`).

### Optional Parameters

You can add extra fields to the form data to customize the transcription:
- `model`: Model size (`tiny`, `base`, `small`, `medium`, `large`). Default: `base`.
- `language`: Language code (e.g., `es`, `en`). Defaults to auto-detection.
- `task`: `transcribe` or `translate`. Default: `transcribe`.

## API Endpoints

The Whisper service exposes the following endpoints:

- `POST /transcribe`: Transcribes an audio file.
- `GET /health`: Checks if the service is running.
- `GET /models`: Lists available Whisper models.
- `GET /info`: Service version and information.

## Notes
- **Model Storage**: Whisper models are downloaded automatically and stored in a Docker volume (`whisper_models`) to persist between restarts.
- **Performance**: The service uses `int8` quantization by default for better performance on CPUs.
