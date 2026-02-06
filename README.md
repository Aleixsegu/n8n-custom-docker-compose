# n8n Custom Docker Compose

This project sets up a local environment with **n8n**, a custom **Whisper API** service (using `faster-whisper`), and a **YouTube Downloader** service (using `yt-dlp`), all running in Docker containers.

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose installed on your machine.

## Quick Start

1. **Clone/Open** this repository.
2. **Start the services**:
   ```bash
   docker-compose up -d --build
   ```
   This will build the services and pull the n8n image.

3. **Access n8n**:
   Open [http://localhost:5678](http://localhost:5678) in your browser.

## Services

| Service | Address | Description |
|---------|---------|-------------|
| **n8n** | `http://localhost:5678` | Workflow automation tool. |
| **Whisper API** | `http://localhost:8081` | Custom API for OpenAI's Whisper model. |
| **YtDlp API** | `http://localhost:8082` | YouTube downloader service. |

> **Note**: Within the Docker network, use the following hostnames:
> - Whisper: `whisper:8081`
> - YtDlp: `ytdlp:8082`

## How to use in n8n

### 1. YouTube Downloader (ytdlp)

Use the **HTTP Request** node to download audio or video.

*   **Method**: `POST`
*   **URL**: `http://ytdlp:8082/download`
*   **Body Content Type**: `JSON`
*   **Body Parameters**:
    *   `url`: `{{ $json.url }}` (YouTube link)
    *   `format`: `audio` or `video`
    *   `quality`: `best` (optional)

The file is saved to `/downloads`, which matches the configured volume in n8n.

### 2. Whisper Transcription

Use the **HTTP Request** node to transcribe the audio file.

*   **Method**: `POST`
*   **URL**: `http://whisper:8081/transcribe`
*   **Send Body**: `On`
*   **Body Content Type**: `Multipart-form-data`
*   **Parameters**:
    *   **Parameter Type**: `Form-Data`
    *   **Name**: `file`
    *   **Input Type**: `Binary File`
    *   **Value**: `data` (or your binary property name)

**Optional Parameters:**
- `model`: `tiny`, `base`, `small`, `medium`, `large`.
- `language`: e.g., `es`.
- `condition_on_previous_text`: `true`/`false`.

## API Endpoints

### Whisper Service (`:8081`)
- `POST /transcribe`: Transcribes an audio file.
- `GET /health`: Checks if the service is running.
- `GET /models`: Lists available Whisper models.

### YtDlp Service (`:8082`)
- `POST /download`: Downloads video/audio.
- `POST /info`: Gets video metadata without downloading.
- `POST /download-transcript`: Downloads subtitles/captions.
- `GET /health`: Checks if the service is running.

## Notes
- **Shared Storage**: The `/downloads` directory is shared between `ytdlp` and `n8n`.
- **Model Storage**: Whisper models are persisted in the `whisper_models` volume.
- **Performance**: The Whisper service uses `int8` quantization by default for better performance on CPUs.
