from __future__ import annotations

import argparse
import http.client
import socket
import json
import math
import mimetypes
import queue
import re
import sys
import threading
import time
import uuid
import wave
import zipfile
from array import array
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse, urlsplit
from urllib.request import Request, urlopen

from .config import base_url_hint as _base_url_hint, env_base_url as _env_base_url, env_token as _env_token

ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS = {'.wav', '.mp3', '.flac', '.m4a', '.ogg'}


def emit(**values):
    print(json.dumps(values, ensure_ascii=False), flush=True)


def config(name):
    payload = json.loads((ROOT / 'references' / name).read_text(encoding='utf-8-sig'))
    if name == 'index_tts.json':
        if not (payload.get('base_url') and payload.get('token')):
            fallback = Path.home() / '.lstest' / 'tts.json'
            if fallback.is_file():
                local = json.loads(fallback.read_text(encoding='utf-8-sig'))
                for key in ('base_url', 'token', 'request_timeout'):
                    if local.get(key) and not payload.get(key):
                        payload[key] = local[key]
        url = _env_base_url()
        if url:
            payload['base_url'] = url
        token = _env_token()
        if token:
            payload['token'] = token
    return payload


DEFAULT_VOICES = {'male': ('付小春',), 'female': ('小宁',), 'both': ('付小春', '小宁')}


def default_cloud(job):
    scope = job.get('gender', 'male')
    if scope not in DEFAULT_VOICES:
        raise ValueError('gender 必须是 male/female/both。')
    return [{'name': voice} for voice in DEFAULT_VOICES[scope]]


def clean(value):
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(value)).strip(' .')[:100]
    if not result or re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', result, re.I):
        result = '_' + result
    return result


def split_text(value):
    return [part.strip() for part in re.split(r'[\r\n、；;]+', str(value)) if part.strip()]


CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
WORDS = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
SENTENCE = re.compile(r'(?<=[，。！？；：、,.!?;:])\s*')


def estimate_tokens(text):
    """粗略估算 IndexTTS 文本 token：中文约 1 字 1 token，西文按词折算。"""
    return len(CJK.findall(text)) + round(len(WORDS.findall(text)) * 1.3) + 1


def split_long(text, limit):
    """仅当单条文本超过安全长度时，按句读标点切成多段，避免单段音频过长导致对齐坍塌。"""
    if limit <= 0 or estimate_tokens(text) <= limit:
        return [text]
    parts, buffer = [], ''
    for piece in SENTENCE.split(text):
        if not piece:
            continue
        if buffer and estimate_tokens(buffer + piece) > limit:
            parts.append(buffer)
            buffer = piece
        else:
            buffer += piece
        while estimate_tokens(buffer) > limit:
            cut = max(1, len(buffer) * limit // max(1, estimate_tokens(buffer)))
            space = buffer.rfind(' ', 1, cut + 1)
            if space > 0:
                cut = space
            parts.append(buffer[:cut])
            buffer = buffer[cut:]
    if buffer:
        parts.append(buffer)
    return [part.strip() for part in parts if part.strip()]


def read_text_file(path):
    for encoding in ('utf-8-sig', 'gb18030', 'utf-16'):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('TXT 编码无法识别，请另存为 UTF-8。')


def inspect_audio(path, deep=True):
    """返回 (时长秒, 峰值dBFS, 致命问题, 提示列表)。deep=False 只读头部。"""
    try:
        with wave.open(str(path), 'rb') as handle:
            rate = handle.getframerate()
            frames = handle.getnframes()
            width = handle.getsampwidth()
            data = handle.readframes(frames) if deep else b''
    except Exception:
        return None, None, 'WAV 无法解析', []
    seconds = frames / rate if rate else 0.0
    notes = []
    if seconds < .05:
        return seconds, None, '音频过短', notes
    if not deep:
        return seconds, None, None, notes
    peak = None
    if width == 2 and data:
        samples = array('h')
        samples.frombytes(data[:len(data) - len(data) % 2])
        if sys.byteorder == 'big':
            samples.byteswap()
        if not samples:
            return seconds, None, '音频过短', notes
        top = max(abs(min(samples)), abs(max(samples)))
        peak = 20 * math.log10(top / 32768) if top else -120.0
        if not top:
            return seconds, peak, '音频为静音', notes
        if (samples.count(32767) + samples.count(-32768)) / len(samples) > .02:
            notes.append('疑似削波')
    elif width == 1 and data:
        top = max(abs(min(data) - 128), abs(max(data) - 128))
        peak = 20 * math.log10(top / 128) if top else -120.0
        if not top:
            return seconds, peak, '音频为静音', notes
    if seconds > 90:
        notes.append('疑似过长')
    return seconds, peak, None, notes


def unique_label(base, used):
    name, number = base, 2
    while name.casefold() in used:
        name = f'{base}_{number}'
        number += 1
    used.add(name.casefold())
    return name


def texts_from(job):
    limit = job.get('max_text_tokens', 70)
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError('max_text_tokens 必须为非负整数。')
    if ('text' in job) == ('text_file' in job):
        raise ValueError('text 与 text_file 必须二选一。')
    if 'text' in job:
        if not isinstance(job['text'], str):
            raise ValueError('text 必须是字符串。')
        raw = split_text(job['text'])
        name = '直接文本'
    else:
        path = Path(job['text_file']).resolve()
        name = path.stem
        suffix = path.suffix.lower()
        if suffix == '.txt':
            value = read_text_file(path)
            if '\t' in value:
                raise ValueError('TXT 不能包含制表符多列。')
            raw = split_text(value)
        elif suffix in {'.xlsx', '.xls'}:
            if suffix == '.xlsx':
                from openpyxl import load_workbook
                book = load_workbook(path, read_only=True, data_only=True)
                try:
                    rows = list(book.worksheets[0].iter_rows(values_only=True))
                finally:
                    book.close()
            else:
                import xlrd
                book = xlrd.open_workbook(str(path))
                try:
                    sheet = book.sheet_by_index(0)
                    rows = [sheet.row_values(i) for i in range(sheet.nrows)]
                finally:
                    book.release_resources()
            headers = [str(v).strip() if v is not None else '' for v in (rows[0] if rows else [])]
            if '文本' not in headers:
                raise ValueError('Excel 第一工作表缺少“文本”列。')
            ti = headers.index('文本')
            qi = headers.index('合成数量') if '合成数量' in headers else None
            raw = []
            for number, row in enumerate(rows[1:], 2):
                value = row[ti] if ti < len(row) else None
                if qi is not None and qi < len(row) and row[qi] is not None and str(row[qi]).strip():
                    raise ValueError(f'第{number}行填写了合成数量，IndexTTS 暂不支持，请清空该值。')
                if value is None or not str(value).strip():
                    continue
                raw.extend(split_text(value))
        else:
            raise ValueError('文本文件仅支持 TXT/XLSX/XLS。')
    texts, segmented = [], 0
    for item in raw:
        parts = split_long(item, limit)
        if len(parts) > 1:
            segmented += 1
        texts.extend(parts)
    if not texts:
        raise ValueError('没有有效文本。')
    return texts, name, segmented


def audio_file(value):
    path = Path(value).resolve()
    if not path.is_file():
        bundled = ROOT / 'scripts' / 'lstts_core' / 'voices' / (str(value) + '.wav')
        if bundled.is_file():
            path = bundled.resolve()
    if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
        raise ValueError(f'不是支持的音频文件：{path}')
    return path


def natural(path):
    return [(0, int(p)) if p.isdigit() else (1, p) for p in re.split(r'(\d+)', path.as_posix().casefold())]


def local_records(value):
    path = Path(value).resolve()
    if path.is_dir():
        files = sorted((p for p in path.rglob('*') if not p.is_symlink() and p.is_file() and p.suffix.lower() in EXTENSIONS), key=natural)
    else:
        files = [audio_file(path)]
    if not files:
        raise ValueError('音色目录没有支持的音频。')
    return [{'path': p, 'label': p.relative_to(path).as_posix() if path.is_dir() else p.name, 'meta': {}} for p in files]


def gender(value):
    text = str(value).strip()
    if text in ('男', '男性', '1', '1.0'):
        return 'male'
    if text in ('女', '女性', '2', '2.0'):
        return 'female'
    return None


def age_group(value):
    try:
        age = float(value)
        if not math.isfinite(age):
            return None
        return 'adult' if 18 <= age <= 55 else 'elder' if age >= 56 else None
    except (ValueError, TypeError):
        return None


def cloud_records(selections):
    import oss2
    from openpyxl import load_workbook
    cfg = config('oss.json')
    for key in ('access_key_id', 'access_key_secret', 'endpoint', 'bucket', 'prefix'):
        if not cfg.get(key):
            raise ValueError(f'OSS 配置缺少 {key}')
    endpoint = cfg['endpoint']
    if not endpoint.startswith(('http://', 'https://')):
        endpoint = 'https://' + endpoint
    bucket = oss2.Bucket(oss2.Auth(cfg['access_key_id'], cfg['access_key_secret']), endpoint, cfg['bucket'], connect_timeout=60)
    prefix = cfg['prefix'].strip('/') + '/'
    try:
        data = bucket.get_object(prefix + cfg.get('metadata_file', '音频文本信息表.xlsx')).read()
    except Exception as exc:
        raise RuntimeError(f'读取云端信息表失败（{type(exc).__name__}）。') from None
    book = load_workbook(BytesIO(data), read_only=True, data_only=True)
    records = []
    try:
        rows = book.active.iter_rows(values_only=True)
        headers = [str(v).strip() if v is not None else '' for v in next(rows, ())]
        if not {'音频', '性别', '年龄', '省份'}.issubset(headers):
            raise ValueError('云端信息表缺少音频/性别/年龄/省份列。')
        for row in rows:
            meta = dict(zip(headers, row))
            audio = str(meta.get('音频') or '').strip()
            if not audio:
                continue
            key = audio.replace('\\', '/')
            if key.startswith('oss://'):
                key = key[6:].partition('/')[2]
            elif key.startswith(('http://', 'https://')):
                key = unquote(urlparse(key).path).lstrip('/')
                if key.startswith(cfg['bucket'] + '/'):
                    key = key[len(cfg['bucket']) + 1:]
            key = key.lstrip('/')
            if not key.startswith(prefix):
                key = prefix + key
            records.append({'key': key, 'label': audio, 'meta': meta})
    finally:
        book.close()
    if not isinstance(selections, list) or not selections:
        raise ValueError('cloud 必须是非空筛选条件列表。')
    selected, used = [], set()
    for selection in selections:
        if not isinstance(selection, dict):
            raise ValueError('cloud 每个筛选项必须是对象。')
        if 'name' in selection:
            wanted = str(selection['name']).strip()
            matches = [r for r in records if str(r['meta'].get('姓名') or '').strip() == wanted]
            if len(matches) != 1:
                raise ValueError(f'姓名“{wanted}”匹配 {len(matches)} 条音色，无法唯一定位。')
            if matches[0]['key'] in used:
                raise ValueError('筛选组或信息表存在重复音色，请调整条件或信息表。')
            used.add(matches[0]['key'])
            selected.append(matches[0])
            continue
        g, a = selection.get('gender', 'male'), selection.get('age', 'adult')
        provinces = selection.get('provinces')
        if g not in ('male', 'female', 'all') or a not in ('adult', 'elder', 'all'):
            raise ValueError('无效的性别或年龄筛选条件。')
        if provinces is not None and (not isinstance(provinces, list) or not provinces or not all(isinstance(p, str) for p in provinces)):
            raise ValueError('provinces 必须为非空省份列表或省略。')
        candidates = [r for r in records if (g == 'all' or gender(r['meta'].get('性别')) == g) and (a == 'all' or age_group(r['meta'].get('年龄')) == a) and (provinces is None or str(r['meta'].get('省份') or '').strip() in provinces)]
        amount = selection.get('count')
        if amount == '全部':
            amount = len(candidates)
        elif isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise ValueError('音色数量必须为正整数或“全部”。')
        if amount > len(candidates) or not amount:
            raise ValueError(f'人数不足：{g}/{a} 请求 {amount} 条，符合条件仅 {len(candidates)} 条，请调整人数或筛选条件。')
        for record in candidates[:amount]:
            if record['key'] in used:
                raise ValueError('筛选组或信息表存在重复音色，请调整条件或信息表。')
            used.add(record['key'])
            selected.append(record)
    return selected, bucket


def request_audio(cfg, speaker, emotion, text_path):
    base_url = str(cfg.get('base_url') or '').strip()
    if not base_url:
        raise ValueError(_base_url_hint())
    deadline = time.monotonic() + cfg['request_timeout']
    boundary = '----IndexTTS' + uuid.uuid4().hex
    fields = [('spk_audio_prompt', speaker), ('text', text_path)]
    if emotion:
        fields.append(('emo_audio_prompt', emotion))
    chunks = []
    for field, path in fields:
        filename = clean(path.name)
        header = f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{filename}"\r\nContent-Type: {mimetypes.guess_type(path.name)[0] or "application/octet-stream"}\r\n\r\n'
        chunks.extend([header.encode('utf-8'), path.read_bytes(), b'\r\n'])
    chunks.append(f'--{boundary}--\r\n'.encode())
    body = b''.join(chunks)
    url = urlsplit(base_url.rstrip('/') + ('/v1/emotion' if emotion else '/v1/clone'))
    if url.scheme not in ('http', 'https') or not url.hostname:
        raise ValueError('无效的服务地址：请检查 LSTTS_TTS_URL 或配置文件 base_url 是否为 http(s) 地址。')
    results = queue.Queue(maxsize=1)
    lock = threading.Lock()
    sockets = []
    aborted = threading.Event()

    def register(connection):
        with lock:
            if connection.sock is not None:
                sockets.append(connection.sock)
                if aborted.is_set():
                    connection.sock.close()
                    raise TimeoutError('请求已断开。')

    class HTTPConnection(http.client.HTTPConnection):
        def connect(self):
            super().connect()
            register(self)

    class HTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            super().connect()
            register(self)

    def disconnect():
        aborted.set()
        with lock:
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

    def perform():
        connection = None
        try:
            if aborted.is_set():
                return
            cls = HTTPSConnection if url.scheme == 'https' else HTTPConnection
            connection = cls(url.hostname, url.port, timeout=max(.001, deadline-time.monotonic()))
            connection.request('POST', url.path + (('?' + url.query) if url.query else ''), body=body, headers={'Authorization': 'Bearer ' + cfg['token'], 'Content-Type': 'multipart/form-data; boundary=' + boundary, 'Content-Length': str(len(body)), 'Connection': 'close'})
            response = connection.getresponse()
            if response.status != 200:
                raise RuntimeError(f'合成服务 HTTP {response.status}。')
            if response.headers.get_content_type() != 'application/zip':
                raise RuntimeError('服务返回的不是 ZIP。')
            results.put((True, response.read()))
        except (socket.timeout, TimeoutError):
            results.put((False, TimeoutError(f'请求超过 {cfg["request_timeout"]} 秒，已主动断开。')))
        except Exception as exc:
            results.put((False, RuntimeError(f'合成请求失败（{type(exc).__name__}）。')))
        finally:
            if connection is not None:
                connection.close()

    threading.Thread(target=perform, daemon=True).start()
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'请求超过 {cfg["request_timeout"]} 秒，已主动断开。')
            try:
                ok, value = results.get(timeout=min(.2, remaining))
            except queue.Empty:
                continue
            if not ok:
                raise value
            return value
    finally:
        disconnect()


def save_audio(data, directory, count, start_index=1):
    with zipfile.ZipFile(BytesIO(data)) as archive:
        entries = []
        for item in archive.infolist():
            name = item.filename.replace('\\', '/')
            if name.startswith('/') or '..' in name.split('/') or ':' in name or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('ZIP 包含不安全路径。')
            if not item.is_dir() and Path(name).suffix.lower() == '.wav':
                entries.append(item)
        if len(entries) != count:
            raise ValueError(f'服务返回 {len(entries)} 个 WAV，预期 {count} 个。')
        directory.mkdir(parents=True, exist_ok=True)
        written = []
        try:
            for index, entry in enumerate(entries, start_index):
                target = directory / f'{directory.name}_{index:04d}.wav'
                if target.exists():
                    raise FileExistsError(f'输出音频已存在：{target.name}')
                written.append(target)
                target.write_bytes(archive.read(entry))
        except BaseException:
            for target in written:
                target.unlink(missing_ok=True)
            if not any(directory.iterdir()):
                directory.rmdir()
            raise
    return written


HEADERS = ['音频', '音频路径', '文本序号', '文本', '音色参考音频', '情感参考音频', '姓名', '性别', '年龄', '地区', '省份', '合成状态', '错误信息', '音频时长(秒)', '峰值(dBFS)', '校验结论']


def write_report(path, rows):
    from openpyxl import Workbook
    from openpyxl.styles import Font
    book = Workbook()
    sheet = book.active
    sheet.title = '合成结果'
    sheet.append(HEADERS)
    for row in rows:
        sheet.append(row)
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value, str):
                cell.data_type = 's'
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    sheet.freeze_panes = 'A2'
    sheet.auto_filter.ref = sheet.dimensions
    for column in 'ABCDEFGHIJKLMNOP':
        sheet.column_dimensions[column].width = 24
    sheet.column_dimensions['B'].width = 65
    sheet.column_dimensions['D'].width = 60
    temporary = path.with_suffix('.tmp.xlsx')
    book.save(temporary)
    book.close()
    temporary.replace(path)


def run(job, preview=False):
    texts, name, segmented = texts_from(job)
    if 'speaker' in job and 'cloud' in job:
        raise ValueError('speaker 与 cloud 必须二选一。')
    if 'speaker' not in job and 'cloud' not in job:
        job = dict(job, cloud=default_cloud(job))
    emotion = audio_file(job['emotion']) if job.get('emotion') else None
    cfg = config('index_tts.json')
    base_url = str(cfg.get('base_url') or '').strip()
    if not base_url:
        raise ValueError(_base_url_hint())
    if not base_url.startswith(('http://', 'https://')):
        raise ValueError('IndexTTS 服务地址必须以 http:// 或 https:// 开头：请检查 LSTTS_TTS_URL 或配置文件 base_url。')
    if not cfg.get('token'):
        raise ValueError('缺少 IndexTTS token：请设置环境变量 LSTTS_TTS_TOKEN（兼容旧名 LSTEST_TTS_TOKEN），或在配置文件中写入 token。')
    timeout = cfg.get('request_timeout', 10)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('request_timeout 必须为正数。')
    cfg['request_timeout'] = timeout
    validate = job.get('validate_audio', True)
    if not isinstance(validate, bool):
        raise ValueError('validate_audio 必须为 true 或 false。')
    bucket = None
    if 'cloud' in job:
        records, bucket = cloud_records(job['cloud'])
    else:
        records = local_records(job['speaker'])
    long_references = []
    for record in records:
        reference = record.get('path')
        if reference and Path(reference).suffix.lower() == '.wav':
            seconds = inspect_audio(reference, deep=False)[0]
            if seconds and seconds > 15:
                long_references.append(record['label'])
    root = Path(job.get('output') or Path.cwd() / 'index_tts_output').resolve()
    emit(event='preview', texts=len(texts), speakers=len(records), expected_wav=len(texts)*len(records), mode='emotion' if emotion else 'clone', output=str(root), selections=job.get('cloud'), segmented_texts=segmented, validate_audio=validate, long_references=long_references)
    if preview:
        return 0
    from openpyxl import Workbook  # dependency check before requests
    output = root / (datetime.now().strftime('%Y%m%d_%H%M%S_%f') + '_' + clean(name))
    output.mkdir(parents=True, exist_ok=False)
    text_path = output / '.request.txt'
    report = output / '合成结果.xlsx'
    rows = []
    stopped = False
    successes = failures = suspects = 0
    used, pending = set(), 0
    try:
        for index, record in enumerate(records, 1):
            meta = record['meta']
            voice = str(meta.get('姓名') or '').strip() or Path(record['label'].replace('\\', '/')).stem
            label = f'{index:04d}_' + unique_label(clean(voice), used)
            if len(str(output)) + len(label) * 2 + 24 > 250:
                raise ValueError('输出路径过长，请缩短输出目录、音色名或改用更浅的输出目录。')
            error, status = '', '成功'
            stage = '下载'
            try:
                if bucket is not None:
                    ref_dir = output / '参考音频'
                    ref_dir.mkdir(exist_ok=True)
                    suffix = Path(record['key']).suffix.lower()
                    if suffix not in EXTENSIONS:
                        raise ValueError('云端音色格式不支持。')
                    target = ref_dir / (label + suffix)
                    part = target.with_suffix(target.suffix + '.part')
                    try:
                        bucket.get_object_to_file(record['key'], str(part))
                        part.replace(target)
                    finally:
                        part.unlink(missing_ok=True)
                    record['path'] = target
            except KeyboardInterrupt:
                stopped, status, error = True, '已中止', '用户停止了本地任务。'
            except Exception as exc:
                status = stage + '失败'
                error = str(exc) if stage == '合成' else f'下载失败（{type(exc).__name__}）。'
            for ti, text in enumerate(texts, 1):
                if stopped:
                    break
                audio, seconds, peak, verdict = None, None, None, ''
                item_status, item_error = status, error
                current = (index-1)*len(texts)+ti
                if status == '成功':
                    try:
                        text_path.write_text(text + '\n', encoding='utf-8')
                        emit(event='progress', current=current, total=len(records)*len(texts), speaker=record['label'], text_index=ti)
                        data = request_audio(cfg, record['path'], emotion, text_path)
                        audio = save_audio(data, output / label, 1, start_index=ti)[0]
                        if validate:
                            seconds, peak, fatal, notes = inspect_audio(audio)
                            if fatal:
                                item_status, item_error = '合成失败', f'音频校验失败：{fatal}'
                                verdict = '不通过：' + fatal
                            elif notes:
                                suspects += 1
                                verdict = '疑似：' + '、'.join(notes)
                            else:
                                verdict = '通过'
                    except KeyboardInterrupt:
                        stopped = True
                        item_status, item_error = '已中止', '用户停止并断开当前请求。'
                    except TimeoutError as exc:
                        item_status, item_error = '超时', str(exc)
                    except Exception as exc:
                        item_status, item_error = '合成失败', str(exc)
                if audio and item_status == '成功':
                    successes += 1
                else:
                    failures += 1
                rows.append([audio.name if audio else '', str(audio) if audio else '', ti, text, str(record.get('path', record['label'])), str(emotion or ''), *[meta.get(k) for k in ('姓名', '性别', '年龄', '地区', '省份')], item_status, item_error, round(seconds, 2) if seconds is not None else '', round(peak, 1) if peak is not None else '', verdict])
                pending += 1
                if pending >= 25:
                    write_report(report, rows)
                    pending = 0
                emit(event='item_result', current=current, status=item_status, error=item_error, wav=int(audio is not None))
            if stopped:
                break
    finally:
        text_path.unlink(missing_ok=True)
        if rows:
            write_report(report, rows)
    emit(event='complete', successful_audio=successes, failed_or_stopped_audio=failures, suspect_audio=suspects, segmented_texts=segmented, wav=successes, output=str(output), xlsx=str(report), stopped=stopped)
    return 130 if stopped else 2 if failures else 0


def main():
    parser = argparse.ArgumentParser(description='独立 IndexTTS 合成客户端')
    parser.add_argument('--job', required=True, type=Path)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    try:
        job = json.loads(args.job.read_text(encoding='utf-8-sig'))
        if not isinstance(job, dict):
            raise ValueError('任务 JSON 必须为对象。')
        return run(job, args.preview)
    except KeyboardInterrupt:
        emit(event='error', message='任务已中止。')
        return 130
    except Exception as exc:
        emit(event='error', message=str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
