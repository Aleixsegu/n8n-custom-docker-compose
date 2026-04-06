from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import subprocess
import os
import re
import random
import tempfile
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = '/downloads'
TEMP_DIR = '/tmp/audioprocess'
os.makedirs(TEMP_DIR, exist_ok=True)

VALID_BLEND_MODES = {
    'normal', 'multiply', 'screen', 'overlay', 'darken', 'lighten',
    'hardlight', 'softlight', 'difference', 'exclusion', 'add', 'subtract',
    'divide', 'phoenix', 'negation', 'reflect', 'glow', 'freeze', 'heat'
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def get_video_duration(filepath):
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return float(result.stdout.strip())
    except Exception as e:
        logger.error(f"Error getting duration for {filepath}: {e}")
        return 0


def get_video_dimensions(filepath):
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height',
            '-of', 'csv=p=0',
            filepath
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        parts = result.stdout.strip().split(',')
        return int(parts[0]), int(parts[1])
    except Exception as e:
        logger.error(f"Error getting dimensions for {filepath}: {e}")
        return 1920, 1080


def needs_loop(filepath, audio_duration):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}:
        return False
    if ext == '.gif':
        return True
    dur = get_video_duration(filepath)
    if dur > 0 and dur < audio_duration:
        logger.info(f"Overlay {os.path.basename(filepath)} dur={dur:.1f}s < audio={audio_duration:.1f}s → loop")
        return True
    return False


def srt_time_to_ms(t):
    h, m, rest = t.strip().split(':')
    s, ms = rest.split(',')
    return int(h) * 3600000 + int(m) * 60000 + int(s) * 1000 + int(ms)


def ms_to_ass_time(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    cs = (ms % 1000) // 10
    return f"{h}:{m:02}:{s:02}.{cs:02}"


def build_atempo(factor):
    filters = []
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    while factor > 2.0:
        filters.append("atempo=2.0")
        factor /= 2.0
    filters.append(f"atempo={factor:.6f}")
    return ",".join(filters)


def convert_srt_to_ass(srt_path, ass_path, video_width=1920, video_height=1080, style_config=None):
    if style_config is None:
        style_config = {}

    font_name      = style_config.get('font_name', 'Arial')
    font_size      = int(style_config.get('font_size', 72))
    bold           = 1 if style_config.get('bold', True) else 0
    primary_colour = style_config.get('primary_colour', '&H00FFFFFF')
    outline_colour = style_config.get('outline_colour', '&H00000000')
    outline        = int(style_config.get('outline', 8))
    shadow         = int(style_config.get('shadow', 0))
    alignment      = int(style_config.get('alignment', 5))
    fade_ms        = int(style_config.get('fade_ms', 60))
    pop_scale      = int(style_config.get('pop_scale', 130))
    pop_dur        = int(style_config.get('pop_duration_ms', 150))

    pos_x_pct = style_config.get('pos_x_pct', None)
    pos_y_pct = style_config.get('pos_y_pct', None)
    use_pos   = pos_x_pct is not None and pos_y_pct is not None
    pos_x_px  = int(float(pos_x_pct) * video_width)  if use_pos else None
    pos_y_px  = int(float(pos_y_pct) * video_height) if use_pos else None

    margin_v = int(style_config.get('margin_v', 0))
    margin_l = int(style_config.get('margin_l', 50))
    margin_r = int(style_config.get('margin_r', 50))

    with open(srt_path, 'r', encoding='utf-8') as f:
        content = f.read()

    blocks = re.split(r'\n\s*\n', content.strip())
    events = []

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            start_str, end_str = lines[1].split(' --> ')
            start_ms = srt_time_to_ms(start_str)
            end_ms   = srt_time_to_ms(end_str)
            text     = ' '.join(lines[2:]).replace('\n', '\\N')
            events.append((start_ms, end_ms, text))
        except Exception as e:
            logger.warning(f"Could not parse SRT block: {e}")
            continue

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{primary_colour},&H000000FF,{outline_colour},&H00000000,{bold},0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},{margin_l},{margin_r},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    for start_ms, end_ms, text in events:
        start_ass = ms_to_ass_time(start_ms)
        end_ass   = ms_to_ass_time(end_ms)

        tags = f"\\fad({fade_ms},{fade_ms})"
        if use_pos:
            tags += f"\\an5\\pos({pos_x_px},{pos_y_px})"
        if pop_scale != 100:
            tags += (
                f"\\fscx{pop_scale}\\fscy{pop_scale}"
                f"\\t(0,{pop_dur},\\fscx100\\fscy100)"
            )

        animated_text = f"{{{tags}}}{text}"
        ass_content += f"Dialogue: 0,{start_ass},{end_ass},Default,,0,0,0,,{animated_text}\n"

    with open(ass_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

    logger.info(
        f"ASS written: {ass_path} — {len(events)} events | "
        f"align={alignment} pos={'({},{})'.format(pos_x_px,pos_y_px) if use_pos else 'margin'} "
        f"size={font_size} outline={outline} pop={pop_scale}%/{pop_dur}ms"
    )


# ─────────────────────────────────────────────
# AUDIO PROCESSING
# ─────────────────────────────────────────────

def run_audio_processing(input_path: str, output_path: str, config: dict):
    pitch_semitones    = float(config.get('pitch_semitones', 0.3))
    tempo_compensation = config.get('tempo_compensation', True)
    eq_low_hz          = float(config.get('eq_low_hz', 120))
    eq_low_gain        = float(config.get('eq_low_gain', 0.8))
    eq_hi_hz           = float(config.get('eq_hi_hz', 8000))
    eq_hi_gain         = float(config.get('eq_hi_gain', 0.8))
    noise_db           = float(config.get('noise_db', -75))
    bitrate            = config.get('bitrate', '192k')

    pitch_factor = 2 ** (pitch_semitones / 12)
    tempo_factor = round(1.0 / pitch_factor, 6)
    noise_amp    = 10 ** (noise_db / 20)

    filters = []
    filters.append(f"asetrate=44100*{pitch_factor:.6f}")
    filters.append("aresample=44100")
    if tempo_compensation:
        filters.append(build_atempo(tempo_factor))
    filters.append(f"equalizer=f={eq_low_hz}:width_type=o:width=2:g={eq_low_gain}")
    filters.append(f"equalizer=f={eq_hi_hz}:width_type=o:width=2:g={eq_hi_gain}")
    filters.append(
        f"aeval=val(0)+{noise_amp:.8f}*(random(0)-0.5)|"
        f"val(1)+{noise_amp:.8f}*(random(1)-0.5)"
    )

    cmd = [
        'ffmpeg', '-y',
        '-i', input_path,
        '-af', ",".join(filters),
        '-c:a', 'libmp3lame',
        '-b:a', bitrate,
        '-ar', '44100',
        output_path
    ]

    logger.info(f"Audio processing: pitch={pitch_semitones:+.2f}st noise={noise_db}dBFS")
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        logger.error(f"FFmpeg audio error: {result.stderr}")
        raise RuntimeError(result.stderr)


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'ffmpeg-processor'}), 200


@app.route('/process_audio', methods=['POST'])
def process_audio():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Empty filename'}), 400

    config = {
        'pitch_semitones':    float(request.form.get('pitch_semitones', 0.3)),
        'tempo_compensation': request.form.get('tempo_compensation', 'true').lower() == 'true',
        'eq_low_hz':          float(request.form.get('eq_low_hz', 120)),
        'eq_low_gain':        float(request.form.get('eq_low_gain', 0.8)),
        'eq_hi_hz':           float(request.form.get('eq_hi_hz', 8000)),
        'eq_hi_gain':         float(request.form.get('eq_hi_gain', 0.8)),
        'noise_db':           float(request.form.get('noise_db', -75)),
        'bitrate':            request.form.get('bitrate', '192k'),
    }

    suffix = os.path.splitext(file.filename)[1] or '.mp3'
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=TEMP_DIR) as tmp_in:
        file.save(tmp_in.name)
        input_path = tmp_in.name
    output_path = input_path.replace(suffix, '_processed.mp3')

    try:
        run_audio_processing(input_path, output_path, config)
        return send_file(
            output_path,
            mimetype='audio/mpeg',
            as_attachment=True,
            download_name=f"processed_{os.path.splitext(file.filename)[0]}.mp3"
        )
    except RuntimeError as e:
        return jsonify({'error': 'Processing failed', 'details': str(e)}), 500
    finally:
        for p in [input_path, output_path]:
            try:
                os.unlink(p)
            except Exception:
                pass


@app.route('/render', methods=['POST'])
def render_video():
    """
    JSON body:
    {
        "audio_path": "audio.mp3",
        "video_clips": ["/shared/clip1.mp4"],
        "shuffle_clips": true,
        "output_filename": "out.mp4",
        "output_resolution": "1920x1080",
        "overlays": [
            {
                "path":  "/shared/overlay.png",
                "paths": ["/shared/a.png", "/shared/b.png"],
                "priority": 1,
                "width": 400,
                "height": 200,
                "x": 760,
                "y": 800,
                "blend_mode": "screen",
                "opacity": 1.0
            }
        ],
        "subtitles": { ... }
    }

    Notes:
    - GIFs and videos shorter than audio are looped automatically
    - blend_mode uses gbrp colorspace internally to avoid YUV color artifacts
    - Without blend_mode: standard overlay (alpha-aware, positioned)
    - With blend_mode: blend filter in RGB space (correct colors)
    """
    try:
        data = request.get_json()

        audio_filename    = data.get('audio_path')
        video_clips       = data.get('video_clips', [])
        shuffle_clips     = data.get('shuffle_clips', False)
        output_filename   = data.get('output_filename', 'output.mp4')
        output_resolution = data.get('output_resolution', '1920x1080')
        overlays          = data.get('overlays', [])
        subtitles_config  = data.get('subtitles')

        if not audio_filename or not video_clips:
            return jsonify({'error': 'Missing audio_path or video_clips'}), 400

        try:
            out_w, out_h = [int(x) for x in output_resolution.split('x')]
        except Exception:
            out_w, out_h = 1920, 1080

        def resolve_path(p):
            if p.startswith('/'):
                return p
            down_path = os.path.join(DOWNLOAD_DIR, p)
            if os.path.exists(down_path):
                return down_path
            shared_path = os.path.join('/shared', p)
            if os.path.exists(shared_path):
                return shared_path
            return down_path

        audio_path  = resolve_path(audio_filename)
        output_path = resolve_path(output_filename)

        if not os.path.exists(audio_path):
            return jsonify({'error': f'Audio file not found: {audio_path}'}), 404

        audio_duration = get_video_duration(audio_path)
        if audio_duration == 0:
            return jsonify({'error': 'Could not determine audio duration'}), 500

        logger.info(f"Audio Duration: {audio_duration}s | Output: {out_w}x{out_h}")

        valid_clips = [resolve_path(c) for c in video_clips if os.path.exists(resolve_path(c))]
        if not valid_clips:
            return jsonify({'error': 'No valid video clips found'}), 404
        if shuffle_clips:
            random.shuffle(valid_clips)
            logger.info(f"Shuffled clips: {[os.path.basename(c) for c in valid_clips]}")

        concat_list_path = os.path.join(DOWNLOAD_DIR, 'concat_list.txt')
        total_video_duration = 0
        with open(concat_list_path, 'w') as f:
            while total_video_duration < audio_duration:
                for clip_path in valid_clips:
                    clip_dur = get_video_duration(clip_path)
                    f.write(f"file '{clip_path}'\n")
                    total_video_duration += clip_dur
                    if total_video_duration >= audio_duration:
                        break

        # Resolve overlays
        resolved_overlays = []
        for overlay in overlays:
            paths_list = overlay.get('paths')
            single     = overlay.get('path')
            if paths_list:
                existing = [resolve_path(p) for p in paths_list if os.path.exists(resolve_path(p))]
                if existing:
                    chosen = random.choice(existing)
                    logger.info(f"Random overlay: {os.path.basename(chosen)}")
                    resolved_overlays.append({**overlay, 'path': chosen})
                else:
                    logger.warning(f"No valid paths in overlay list: {paths_list}")
            elif single:
                full = resolve_path(single)
                if os.path.exists(full):
                    resolved_overlays.append({**overlay, 'path': full})
                else:
                    logger.warning(f"Overlay not found: {full}")

        # Convert SRT → ASS
        ass_path = None
        if subtitles_config:
            full_sub_path = resolve_path(subtitles_config.get('path', ''))
            if os.path.exists(full_sub_path):
                ass_path = os.path.join(DOWNLOAD_DIR, 'subtitles.ass')
                convert_srt_to_ass(
                    srt_path=full_sub_path,
                    ass_path=ass_path,
                    video_width=out_w,
                    video_height=out_h,
                    style_config=subtitles_config
                )
            else:
                logger.warning(f"Subtitle file not found: {full_sub_path}")

        # ── Build FFmpeg command ───────────────────────────────────────────
        cmd = ['ffmpeg', '-y']
        cmd.extend(['-f', 'concat', '-safe', '0', '-i', concat_list_path])
        cmd.extend(['-i', audio_path])

        sorted_overlays = sorted(resolved_overlays, key=lambda k: k.get('priority', 5), reverse=True)

        for overlay in sorted_overlays:
            path = overlay['path']
            if needs_loop(path, audio_duration):
                cmd.extend(['-stream_loop', '-1', '-i', path])
                logger.info(f"Loop enabled: {os.path.basename(path)}")
            else:
                cmd.extend(['-i', path])

        filter_complex  = []
        input_map_index = 2
        last_stream     = "[base]"

        # Base video: scale to output resolution, convert to yuv420p
        filter_complex.append(
            f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},format=yuv420p[base]"
        )

        for overlay in sorted_overlays:
            full_overlay_path = overlay['path']

            x       = overlay.get('x')
            y       = overlay.get('y')
            scale_w = overlay.get('width', -1)
            scale_h = overlay.get('height', -1)

            blend_mode = overlay.get('blend_mode', None)
            opacity    = float(overlay.get('opacity', 1.0))

            if blend_mode and blend_mode not in VALID_BLEND_MODES:
                logger.warning(f"Invalid blend_mode '{blend_mode}', falling back to normal overlay")
                blend_mode = None

            next_stream    = f"[v{input_map_index}]"
            overlay_source = f"[{input_map_index}:v]"

            # Scale overlay if requested
            if scale_w != -1 or scale_h != -1:
                scaled_source = f"[scaled{input_map_index}]"
                filter_complex.append(f"{overlay_source}scale={scale_w}:{scale_h}{scaled_source}")
                overlay_source = scaled_source

            pos_x = str(x) if x is not None else "(main_w-overlay_w)/2"
            pos_y = str(y) if y is not None else "(main_h-overlay_h)/2"

            if blend_mode:
                # ── BLEND MODE ────────────────────────────────────────────
                # FIX: Convert BOTH streams to gbrp before blend.
                # blend filter in yuv420p misinterprets the neutral UV values
                # (128,128) as color, producing magenta/purple artifacts.
                # gbrp is a planar RGB format — blend operates in true RGB space.
                # After blend, convert back to yuv420p for the encoder.

                pad_x = str(x) if x is not None else f"({out_w}-iw)/2"
                pad_y = str(y) if y is not None else f"({out_h}-ih)/2"

                # Pad overlay to full frame at position on transparent canvas
                padded_source = f"[padded{input_map_index}]"
                filter_complex.append(
                    f"{overlay_source}"
                    f"pad={out_w}:{out_h}:{pad_x}:{pad_y}:color=black@0,"
                    f"format=gbrp"
                    f"{padded_source}"
                )

                # Convert base to gbrp for this blend step
                base_gbrp = f"[basegbrp{input_map_index}]"
                filter_complex.append(f"{last_stream}format=gbrp{base_gbrp}")

                # Blend in gbrp space, then convert result back to yuv420p
                filter_complex.append(
                    f"{base_gbrp}{padded_source}"
                    f"blend=all_mode={blend_mode}:all_opacity={opacity:.2f},"
                    f"format=yuv420p"
                    f"{next_stream}"
                )

                logger.info(
                    f"Overlay [{input_map_index}] {os.path.basename(full_overlay_path)} "
                    f"blend={blend_mode} opacity={opacity} pos=({pad_x},{pad_y}) [gbrp]"
                )
            else:
                # ── STANDARD OVERLAY ─────────────────────────────────────
                # Convert to rgba to preserve alpha channel (PNG transparency)
                rgba_source = f"[rgba{input_map_index}]"
                filter_complex.append(f"{overlay_source}format=rgba{rgba_source}")

                filter_complex.append(
                    f"{last_stream}{rgba_source}"
                    f"overlay={pos_x}:{pos_y}:eof_action=repeat"
                    f"{next_stream}"
                )

                logger.info(
                    f"Overlay [{input_map_index}] {os.path.basename(full_overlay_path)} "
                    f"mode=normal pos=({pos_x},{pos_y})"
                )

            last_stream = next_stream
            input_map_index += 1

        # Subtitles
        if ass_path and os.path.exists(ass_path):
            escaped = ass_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
            next_stream = "[with_subs]"
            filter_complex.append(f"{last_stream}ass='{escaped}'{next_stream}")
            last_stream = next_stream

        cmd.extend(['-filter_complex', ";".join(filter_complex)])
        cmd.extend(['-map', last_stream])
        cmd.extend(['-map', '1:a'])
        cmd.extend(['-shortest'])
        cmd.extend(['-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23'])
        cmd.extend(['-c:a', 'aac', '-b:a', '128k'])
        cmd.extend([output_path])

        logger.info(f"Running FFmpeg: {' '.join(cmd)}")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"FFmpeg Error: {stderr}")
            return jsonify({'error': 'Rendering failed', 'details': stderr}), 500

        return jsonify({
            'status': 'success',
            'output_file': output_filename,
            'path': output_path
        }), 200

    except Exception as e:
        logger.error(f"Server Error: {str(e)}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("Starting FFmpeg Service on port 8084")
    app.run(host='0.0.0.0', port=8084, debug=False)