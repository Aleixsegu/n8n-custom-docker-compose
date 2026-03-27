from flask import Flask, request, jsonify
from flask_cors import CORS
import subprocess
import os
import re
import random
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

DOWNLOAD_DIR = '/downloads'


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


def convert_srt_to_ass(srt_path, ass_path, video_width=1920, video_height=1080, style_config=None):
    """
    Convert SRT to ASS with full style control from JSON.

    style_config keys (all optional):
        font_name       : "Arial"
        font_size       : 72
        bold            : true
        primary_colour  : "&H00FFFFFF"
        outline_colour  : "&H00000000"
        outline         : 8
        shadow          : 0
        alignment       : 5           ASS numpad (5=mid-center recommended)
        pos_x_pct       : 0.72        X position as fraction of video width (0.0–1.0)
        pos_y_pct       : 0.50        Y position as fraction of video height (0.0–1.0)
        margin_l        : 50
        margin_r        : 50
        fade_ms         : 60
        pop_scale       : 130         pop punch-in scale % (100=off)
        pop_duration_ms : 150
    """
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

    # pos_x_pct / pos_y_pct: position as fraction of video dimensions
    # If provided, \pos() tag overrides margin-based positioning
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

        # Build override tags
        tags = f"\\fad({fade_ms},{fade_ms})"

        # \an5 + \pos(x,y): anchor at center, placed at custom position
        # This makes pop grow symmetrically from the anchor point
        if use_pos:
            tags += f"\\an5\\pos({pos_x_px},{pos_y_px})"

        # Pop punch-in: start big, shrink to 100%
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
        f"align={alignment} pos={'({},{})'.format(pos_x_px, pos_y_px) if use_pos else 'margin'} "
        f"size={font_size} outline={outline} pop={pop_scale}%/{pop_dur}ms"
    )


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'service': 'ffmpeg-processor'}), 200


@app.route('/render', methods=['POST'])
def render_video():
    """
    JSON body:
    {
        "audio_path": "audio.mp3",
        "video_clips": ["/shared/clip1.mp4", "/shared/clip2.mp4"],
        "shuffle_clips": true,          // optional — randomize clip order each run
        "output_filename": "out.mp4",
        "output_resolution": "1920x1080",
        "overlays": [
            {
                "path": "/shared/overlay.png",      // single image (existing behaviour)
                "paths": [                           // OR multiple — one picked randomly
                    "/shared/overlay_a.png",
                    "/shared/overlay_b.png"
                ],
                "priority": 1,
                "width": 1920,
                "height": 1080
            }
        ],
        "subtitles": {
            "path": "/shared/subs.srt",
            "font_name": "Arial",
            "font_size": 72,
            "bold": true,
            "primary_colour": "&H00FFFFFF",
            "outline_colour": "&H00000000",
            "outline": 8,
            "shadow": 0,
            "alignment": 5,
            "pos_x_pct": 0.72,
            "pos_y_pct": 0.50,
            "fade_ms": 60,
            "pop_scale": 130,
            "pop_duration_ms": 150
        }
    }
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

        # Resolve and validate clips
        valid_clips = [resolve_path(c) for c in video_clips if os.path.exists(resolve_path(c))]
        invalid     = [c for c in video_clips if not os.path.exists(resolve_path(c))]
        if invalid:
            logger.warning(f"Clips not found: {invalid}")
        if not valid_clips:
            return jsonify({'error': 'No valid video clips found'}), 404

        # Shuffle clips if requested — randomizes starting clip and concatenation order
        if shuffle_clips:
            random.shuffle(valid_clips)
            logger.info(f"Shuffled clip order: {[os.path.basename(c) for c in valid_clips]}")

        # Build concat list (loop until audio duration is covered)
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

        # Resolve overlay paths — supports single "path" or random pick from "paths"
        resolved_overlays = []
        for overlay in overlays:
            paths_list = overlay.get('paths')   # array of options
            single     = overlay.get('path')    # single path (legacy)

            if paths_list:
                # Filter to existing files, then pick one at random
                existing = [resolve_path(p) for p in paths_list if os.path.exists(resolve_path(p))]
                if existing:
                    chosen = random.choice(existing)
                    logger.info(f"Random overlay chosen: {os.path.basename(chosen)} from {len(existing)} options")
                    resolved_overlays.append({**overlay, 'path': chosen})
                else:
                    logger.warning(f"No valid paths found in overlay paths list: {paths_list}")
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

        # Build FFmpeg filter chain
        cmd = ['ffmpeg', '-y']
        cmd.extend(['-f', 'concat', '-safe', '0', '-i', concat_list_path])
        cmd.extend(['-i', audio_path])

        sorted_overlays = sorted(resolved_overlays, key=lambda k: k.get('priority', 5), reverse=True)

        filter_complex  = []
        input_map_index = 2
        last_stream     = "[base]"

        # Scale + format base video
        filter_complex.append(
            f"[0:v]scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h},format=yuv420p[base]"
        )

        for overlay in sorted_overlays:
            full_overlay_path = overlay['path']
            cmd.extend(['-i', full_overlay_path])

            x     = overlay.get('x')
            y     = overlay.get('y')
            pos_x = str(x) if x is not None else "(main_w-overlay_w)/2"
            pos_y = str(y) if y is not None else "(main_h-overlay_h)/2"

            next_stream    = f"[v{input_map_index}]"
            scale_w        = overlay.get('width', -1)
            scale_h        = overlay.get('height', -1)
            overlay_source = f"[{input_map_index}:v]"

            rgba_source = f"[rgba{input_map_index}]"
            filter_complex.append(f"{overlay_source}format=rgba{rgba_source}")
            overlay_source = rgba_source

            if scale_w != -1 or scale_h != -1:
                scaled_source = f"[scaled{input_map_index}]"
                filter_complex.append(f"{overlay_source}scale={scale_w}:{scale_h}{scaled_source}")
                overlay_source = scaled_source

            filter_complex.append(
                f"{last_stream}{overlay_source}overlay={pos_x}:{pos_y}:eof_action=repeat{next_stream}"
            )
            last_stream = next_stream
            input_map_index += 1

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