"""RetroCast: a portable, standard-library local video and HackTV controller.

Run: python app.py   (Python 3.10 or newer)
YouTube needs optional yt-dlp; HackRF TX needs external HackTV and explicit opt-in.
"""
from __future__ import annotations

import atexit
from collections import deque
from datetime import datetime, timezone
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse, urlsplit
from uuid import uuid4

ROOT = Path(__file__).resolve().parent


def load_local_env(path: Path):
    """Read an uncomplicated .env file without a pip dependency."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key.strip()):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env(ROOT / '.env')


def env_bool(name: str, default: bool = False):
    return os.environ.get(name, str(int(default))).lower() in ('1', 'true', 'yes', 'on')


HOST = os.environ.get('RETROCAST_HOST', '127.0.0.1')
PORT = int(os.environ.get('RETROCAST_PORT', '8765'))
TX_ENABLED = env_bool('RETROCAST_RF_ENABLED')
HACKTV_BIN = os.environ.get('RETROCAST_HACKTV_BIN', 'hacktv')
MEDIA_DIR_RAW = Path(os.environ.get('RETROCAST_MEDIA_DIR', 'media')).expanduser()
MEDIA_DIR = (MEDIA_DIR_RAW if MEDIA_DIR_RAW.is_absolute() else ROOT / MEDIA_DIR_RAW).resolve()
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_MB = min(max(int(os.environ.get('RETROCAST_MAX_UPLOAD_MB', '1024')), 1), 8192)
ALLOWED_EXT = {'.mp4', '.mkv', '.mov', '.webm', '.avi', '.m4v', '.mpeg', '.mpg', '.ts'}
CHANNELS = {'3': 61_250_000, '4': 67_250_000}
MIME = {'js': 'text/javascript', 'css': 'text/css'}

_lock = threading.RLock()
_process: subprocess.Popen | None = None
_active: dict | None = None
_error = ''
_log = deque(maxlen=150)
_jobs: dict[str, dict] = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def log(message: str):
    with _lock:
        _log.append(f'{datetime.now().strftime("%H:%M:%S")}  {message}')


def binary_found(name: str) -> bool:
    p = Path(name)
    return p.is_file() if p.parent != Path('.') else shutil.which(name) is not None


def media_path(name: str) -> Path:
    if (not isinstance(name, str) or name in ('', '.', '..') or Path(name).name != name
            or '/' in name or '\\' in name or Path(name).suffix.lower() not in ALLOWED_EXT):
        raise ValueError('Invalid media filename')
    path = MEDIA_DIR / name
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(name)
    return path


def media_info(p: Path):
    stat = p.stat()
    return {'name': p.name, 'size': stat.st_size,
            'url': '/media/' + p.name,
            'modified': datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(timespec='seconds')}


def yt_dlp_available():
    try:
        import yt_dlp  # noqa: F401
        return True
    except ImportError:
        return False


def state_snapshot():
    global _active, _process, _error
    with _lock:
        if _process is not None and _process.poll() is not None:
            rc = _process.returncode
            _error = f'HackTV exited with code {rc}. See console log.' if rc else ''
            log(_error if _error else 'HackTV completed playback')
            _process = None
            _active = None
        return {'status': 'playing' if _active else 'idle',
                'active': dict(_active) if _active else None,
                'error': _error, 'rf_enabled': TX_ENABLED,
                'hacktv_found': binary_found(HACKTV_BIN),
                'ffmpeg_found': binary_found('ffmpeg'),
                'yt_dlp_found': yt_dlp_available(),
                'host': HOST, 'port': PORT,
                'jobs': list(_jobs.values())[-8:],
                'recent_logs': list(_log)[-20:]}


def stop_process():
    global _process, _active
    with _lock:
        proc = _process
        _process = None
        _active = None
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == 'nt':
            proc.terminate()
        else:
            os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=3)
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        try:
            if os.name == 'nt':
                proc.kill()
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
        except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
            pass
    log('Stopped playback')


def drain_process(proc: subprocess.Popen):
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                if line.strip():
                    log('hacktv: ' + line.strip()[:500])
    except Exception as e:
        log(f'HackTV log reader stopped: {e}')


def valid_youtube_url(url: str) -> bool:
    try:
        p = urlparse(url)
        hostname = (p.hostname or '').lower()
        permitted = hostname in ('youtube.com', 'youtu.be') or hostname.endswith('.youtube.com')
        if not (p.scheme == 'https' and permitted and p.username is None
                and p.password is None and p.port in (None, 443)):
            return False
        if hostname == 'youtu.be':
            return bool(p.path.strip('/'))
        return ((p.path == '/watch' and bool(parse_qs(p.query).get('v')))
                or p.path.startswith(('/shorts/', '/live/', '/embed/')))
    except ValueError:
        return False


def download_video(job_id: str, url: str):
    import yt_dlp
    prefix = 'youtube_' + job_id[:10]
    outtmpl = str(MEDIA_DIR / (prefix + '.%(ext)s'))
    try:
        with _lock:
            _jobs[job_id]['state'] = 'downloading'
        log('Downloading YouTube video, job ' + job_id[:8])
        opts = {'format': 'bv*[height<=480]+ba/b[height<=480]/b',
                'outtmpl': outtmpl,
                'merge_output_format': 'mp4',
                'noplaylist': True, 'max_downloads': 1,
                'quiet': True, 'no_warnings': True,
                'socket_timeout': 25, 'retries': 3, 'fragment_retries': 3,
                'ignoreerrors': False, 'overwrites': False}
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = sorted((p for p in MEDIA_DIR.glob(prefix + '.*')
                        if p.suffix.lower() in ALLOWED_EXT and p.is_file()),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise RuntimeError('Download completed without a playable video file')
        with _lock:
            _jobs[job_id].update(state='done', name=files[0].name)
        log('YouTube ready: ' + files[0].name)
    except Exception as e:
        with _lock:
            _jobs[job_id].update(state='failed', error=str(e)[:350])
        log('YouTube download failed: ' + str(e)[:250])


def play_command(data):
    """Validate request and construct the optional HackTV argument vector."""
    mode = str(data.get('mode', 'preview'))
    source = str(data.get('source', 'file'))
    channel = str(data.get('channel', '3'))
    repeat = data.get('repeat', True) is True
    if mode not in ('preview', 'rf'):
        raise ValueError('Choose preview or RF output')
    if channel not in CHANNELS:
        raise ValueError('Only channels 3 and 4 are supported')
    if source not in ('file', 'test'):
        raise ValueError('Choose a library video or the built-in test pattern')
    if source == 'file':
        try:
            selected = media_path(data.get('name'))
        except (ValueError, FileNotFoundError):
            raise ValueError('Choose an existing video from the library') from None
        name = selected.name
        source_arg = str(selected)
    else:
        name = source_arg = 'test:colourbars'
        repeat = True
    if mode == 'rf':
        if not TX_ENABLED:
            raise PermissionError('RF output is locked. Set RETROCAST_RF_ENABLED=1 in .env after preparing a lawful, isolated RF test setup.')
        if data.get('bench_confirmed') is not True:
            raise ValueError('Confirm your lawful, attenuated, isolated RF test setup first')
        if not binary_found(HACKTV_BIN):
            raise FileNotFoundError('HackTV executable missing. Install HackTV and set RETROCAST_HACKTV_BIN if needed.')
    info = {'mode': mode, 'source': source, 'name': name,
            'channel': channel, 'frequency_hz': CHANNELS[channel],
            'repeat': repeat, 'started_at': now_iso()}
    cmd = None
    if mode == 'rf':
        # -m m = complex/modulated NTSC-M; -s 13.5M is documented NTSC sample rate.
        # Fixed minimum TX VGA gain; DO NOT engage the optional RF amplifier (-a).
        cmd = [HACKTV_BIN, '-o', 'hackrf', '-m', 'm', '-s', '13500000',
               '-f', str(CHANNELS[channel]), '-g', '0']
        if repeat:
            cmd.append('-r')
        cmd.append(source_arg)
    return info, cmd


def start_playback(data):
    global _process, _active, _error
    info, cmd = play_command(data)
    stop_process()
    with _lock:
        _error = ''
    if info['mode'] == 'preview':
        with _lock:
            _active = info
        log(f"Browser preview: {info['name']} (no radio signal)")
        return info
    log(f"Starting HackTV on channel {info['channel']}, 0 dB TX gain, amplifier OFF")
    kwargs = {'cwd': ROOT, 'stdout': subprocess.PIPE, 'stderr': subprocess.STDOUT,
              'text': True, 'bufsize': 1}
    if os.name == 'nt':
        kwargs['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs['start_new_session'] = True
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except (OSError, ValueError) as e:
        with _lock:
            _error = str(e)
        raise RuntimeError('Failed to launch HackTV: ' + str(e)) from e
    with _lock:
        _process = proc
        _active = info
    threading.Thread(target=drain_process, args=(proc,), daemon=True).start()
    time.sleep(.16)
    if proc.poll() is not None:
        state_snapshot()
        raise RuntimeError('HackTV exited immediately. Check the console log.')
    return info


class RetroCastHandler(BaseHTTPRequestHandler):
    server_version = 'RetroCast/1.0'

    def log_message(self, format, *args):
        # Keep video Range/GET polling from spamming the terminal.
        if not self.path.startswith(('/api/status', '/media/')):
            log(f'HTTP {self.address_string()} {format % args}')

    def response(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def respond_error(self, message, status=400):
        self.response({'error': str(message)}, status)

    def raw_body(self, max_bytes=65536):
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise ValueError('Invalid Content-Length') from None
        if length < 0 or length > max_bytes:
            raise ValueError('Invalid or oversized request body')
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError('Incomplete request body')
        return data

    def json_body(self):
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            raise ValueError('Send JSON with Content-Type: application/json')
        try:
            obj = json.loads(self.raw_body().decode('utf-8'))
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError('Invalid JSON request') from None
        if not isinstance(obj, dict):
            raise ValueError('Expected a JSON object')
        return obj

    def file_response(self, path: Path, mime: str, *, allow_range=False):
        if not path.is_file():
            return self.respond_error('Not found', 404)
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        range_header = self.headers.get('Range') if allow_range else None
        if range_header:
            m = re.fullmatch(r'bytes=(\d*)-(\d*)', range_header.strip())
            if not m or (not m.group(1) and not m.group(2)):
                return self.respond_error('Unsupported byte range', 416)
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                count = int(m.group(2))
                start, end = max(0, size-count), size-1
            if start >= size or start > end or size == 0:
                return self.respond_error('Requested byte range unavailable', 416)
            end = min(end, size-1)
            status = 206
        length = max(end-start+1, 0)
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'private, max-age=0')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if allow_range:
            self.send_header('Accept-Ranges', 'bytes')
        if status == 206:
            self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(256*1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        path = urlsplit(self.path).path
        try:
            if path == '/':
                return self.file_response(ROOT/'templates'/'index.html', 'text/html; charset=utf-8')
            if path in ('/static/style.css', '/static/app.js'):
                return self.file_response(ROOT/path.lstrip('/'),
                                          'text/css; charset=utf-8' if path.endswith('css') else 'text/javascript; charset=utf-8')
            if path.startswith('/media/'):
                try:
                    media = media_path(unquote(path[len('/media/'):]))
                except (FileNotFoundError, ValueError):
                    return self.respond_error('File not found', 404)
                mime = mimetypes.guess_type(media.name)[0] or 'application/octet-stream'
                return self.file_response(media, mime, allow_range=True)
            if path == '/api/status':
                return self.response(state_snapshot())
            if path == '/api/health':
                return self.response({'ok': True, 'service':'retrocast', 'utc':now_iso()})
            if path == '/api/media':
                files = sorted((p for p in MEDIA_DIR.iterdir() if p.is_file() and not p.is_symlink()
                                and p.suffix.lower() in ALLOWED_EXT),
                               key=lambda p: p.stat().st_mtime, reverse=True)
                return self.response({'items': [media_info(p) for p in files]})
            if path == '/api/logs':
                with _lock:
                    return self.response({'lines': list(_log)})
            self.respond_error('Endpoint not found', 404)
        except Exception as e:
            log(f'GET error: {type(e).__name__}: {e}')
            self.respond_error('Internal server error; see log', 500)

    def do_POST(self):
        global _jobs
        parsed = urlsplit(self.path)
        try:
            if parsed.path == '/api/upload':
                return self.upload(parsed.query)
            if parsed.path == '/api/play':
                try:
                    return self.response({'ok': True, 'active': start_playback(self.json_body())})
                except PermissionError as e:
                    return self.respond_error(e, 403)
                except FileNotFoundError as e:
                    return self.respond_error(e, 503)
                except RuntimeError as e:
                    return self.respond_error(e, 502)
            if parsed.path == '/api/stop':
                self.json_body()
                stop_process()
                return self.response({'ok':True})
            if parsed.path == '/api/youtube':
                if not yt_dlp_available():
                    return self.respond_error('yt-dlp is missing. Run setup-youtube for optional YouTube support.', 503)
                data = self.json_body()
                url = str(data.get('url') or '').strip()
                if not valid_youtube_url(url):
                    return self.respond_error('Use a valid HTTPS YouTube watch, shorts or youtu.be video link')
                with _lock:
                    if sum(j['state'] in ('queued','downloading') for j in _jobs.values()) >= 2:
                        return self.respond_error('Two videos are already downloading', 429)
                    job_id = uuid4().hex
                    _jobs[job_id] = {'id':job_id, 'state':'queued', 'created_at':now_iso()}
                    if len(_jobs) > 30:
                        oldest = next(iter(_jobs))
                        if _jobs[oldest]['state'] not in ('queued','downloading'):
                            _jobs.pop(oldest, None)
                threading.Thread(target=download_video, args=(job_id,url),daemon=True).start()
                return self.response({'job':dict(_jobs[job_id])}, 202)
            self.respond_error('Endpoint not found', 404)
        except ValueError as e:
            self.respond_error(e, 400)
        except Exception as e:
            log(f'POST error: {type(e).__name__}: {e}')
            self.respond_error('Internal server error; see log', 500)

    def upload(self, query):
        params = parse_qs(query)
        original = params.get('filename', [''])[0]
        stem = re.sub(r'[^a-zA-Z0-9_.-]+', '_', Path(original).stem)[:72].strip('._') or 'video'
        ext = Path(original).suffix.lower()
        if ext not in ALLOWED_EXT or '\\' in original or '/' in original:
            return self.respond_error('Choose a supported video file (MP4, MKV, MOV, AVI, WebM, etc.)')
        try:
            length = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            return self.respond_error('Invalid Content-Length')
        if length <= 0 or length > MAX_UPLOAD_MB*1024*1024:
            return self.respond_error(f'Video must be 1 byte to {MAX_UPLOAD_MB} MB', 413)
        dst = MEDIA_DIR/f'{stem}_{uuid4().hex[:8]}{ext}'
        temp = MEDIA_DIR/(dst.name+'.uploading')
        try:
            remaining=length
            with temp.open('wb') as f:
                while remaining > 0:
                    chunk=self.rfile.read(min(256*1024, remaining))
                    if not chunk:
                        raise ValueError('Upload stopped before file was complete')
                    f.write(chunk)
                    remaining -= len(chunk)
            temp.replace(dst)
        finally:
            temp.unlink(missing_ok=True)
        log(f'Uploaded {dst.name} ({length//1024} KB)')
        return self.response({'item':media_info(dst)},201)

    def do_DELETE(self):
        path = urlsplit(self.path).path
        if path.startswith('/api/media/'):
            try:
                filename=unquote(path[len('/api/media/'):])
                p=media_path(filename)
                with _lock:
                    if _active and _active.get('name') == filename:
                        return self.respond_error('Stop playback before deleting the active video',409)
                    p.unlink()
                log('Deleted '+filename)
                return self.response({'ok':True})
            except (ValueError,FileNotFoundError):
                return self.respond_error('File not found',404)
            except Exception as e:
                log('Delete error: '+str(e))
                return self.respond_error('Internal server error; see log',500)
        self.respond_error('Endpoint not found',404)


def create_server(host=HOST, port=PORT):
    server = ThreadingHTTPServer((host, port), RetroCastHandler)
    server.daemon_threads = True
    return server


atexit.register(stop_process)

if __name__ == '__main__':
    log(f'RetroCast started, RF enabled={TX_ENABLED}')
    server = create_server()
    print('\n  RETROCAST // ANALOG VIDEO LAB')
    print(f'  Web UI: http://127.0.0.1:{server.server_port}' if HOST == '0.0.0.0'
          else f'  Web UI: http://{HOST}:{server.server_port}')
    print('  RF output: ' + ('ENABLED (confirmation required)' if TX_ENABLED else 'LOCKED / preview only'))
    print('  Python core has zero pip dependencies. Press Ctrl+C to stop.\n')
    try:
        server.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        stop_process()
