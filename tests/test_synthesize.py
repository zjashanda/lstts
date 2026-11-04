import importlib.util
import json
import socket
import struct
import threading
import time
import sys
import tempfile
import unittest
import wave
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, MagicMock

from openpyxl import Workbook, load_workbook

SPEC = importlib.util.spec_from_file_location('synthesize', Path(__file__).resolve().parents[1] / 'scripts' / 'synthesize.py')
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


def archive_payload(entries):
    data = BytesIO()
    with zipfile.ZipFile(data, 'w') as z:
        for name, payload in entries:
            z.writestr(name, payload)
    return data.getvalue()


def archive(names):
    return archive_payload([(name, b'RIFF-test') for name in names])


def wav_payload(seconds=1.0, rate=16000, value=3000):
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(struct.pack('<h', value) * int(seconds * rate))
    return buffer.getvalue()


class SkillTests(unittest.TestCase):
    def test_split_and_excel_quantity(self):
        self.assertEqual(s.texts_from({'text': '你好，朋友、再见；下次;角色A：你好。\n尾句'})[0], ['你好，朋友', '再见', '下次', '角色A：你好。', '尾句'])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'text.xlsx'
            book = Workbook()
            book.active.append(['文本', '合成数量'])
            book.active.append(['一、二；三', None])
            book.save(path)
            self.assertEqual(s.texts_from({'text_file': str(path)})[0], ['一', '二', '三'])
            book.active['B2'] = 0
            book.save(path)
            with self.assertRaisesRegex(ValueError, '合成数量'):
                s.texts_from({'text_file': str(path)})
            book.close()

    def test_long_text_segmented(self):
        texts, name, segmented = s.texts_from({'text': '中' * 200})
        self.assertEqual(segmented, 1)
        self.assertGreater(len(texts), 1)
        self.assertEqual(''.join(texts), '中' * 200)
        self.assertTrue(all(s.estimate_tokens(t) <= 70 for t in texts))
        self.assertEqual(s.texts_from({'text': '中' * 200, 'max_text_tokens': 0})[2], 0)
        with self.assertRaisesRegex(ValueError, 'max_text_tokens'):
            s.texts_from({'text': '你好', 'max_text_tokens': -1})

    def test_txt_encoding_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 't.txt'
            path.write_bytes('第一句\n第二句'.encode('gb18030'))
            self.assertEqual(s.texts_from({'text_file': str(path)})[0], ['第一句', '第二句'])

    def test_default_voices(self):
        self.assertEqual(s.default_cloud({}), [{'name': '付小春'}])
        self.assertEqual(s.default_cloud({'gender': 'female'}), [{'name': '小宁'}])
        self.assertEqual(s.default_cloud({'gender': 'both'}), [{'name': '付小春'}, {'name': '小宁'}])
        with self.assertRaisesRegex(ValueError, 'gender'):
            s.default_cloud({'gender': 'other'})

    def test_cloud_name_selection(self):
        book = Workbook()
        book.active.append(['音频', '姓名', '性别', '年龄', '省份'])
        book.active.append(['m1.wav', '付小春', '男', 39, '四川'])
        book.active.append(['f1.wav', '小宁', '女', 35, '内蒙古'])
        book.active.append(['d1.wav', '曾慧虹', '女', 20, '江西'])
        book.active.append(['d2.wav', '曾慧虹', '女', 21, '江西'])
        buffer = BytesIO()
        book.save(buffer)
        book.close()
        bucket = MagicMock()
        bucket.get_object.return_value.read.return_value = buffer.getvalue()
        with patch('oss2.Bucket', return_value=bucket), patch.object(s, 'config', return_value={'access_key_id': 'k', 'access_key_secret': 's', 'endpoint': 'e', 'bucket': 'b', 'prefix': 'p', 'metadata_file': 'm.xlsx'}):
            records, _ = s.cloud_records([{'name': '付小春'}, {'name': '小宁'}])
            self.assertEqual([r['label'] for r in records], ['m1.wav', 'f1.wav'])
            with self.assertRaisesRegex(ValueError, '无法唯一定位'):
                s.cloud_records([{'name': '曾慧虹'}])
            with self.assertRaisesRegex(ValueError, '无法唯一定位'):
                s.cloud_records([{'name': '不存在'}])

    def test_run_uses_default_voice_when_unspecified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            job = {'text': '打开空调', 'output': str(root / 'out')}
            calls = {}
            def fake_cloud(selections):
                calls['selections'] = selections
                return [{'key': 'k', 'label': '付小春.wav', 'meta': {'姓名': '付小春'}, 'path': root / 'ref.wav'}], None
            with patch.object(s, 'cloud_records', side_effect=fake_cloud), patch.object(s, 'request_audio', return_value=archive_payload([('a.wav', wav_payload())])), patch.object(s, 'emit'):
                self.assertEqual(s.run(job), 0)
            self.assertEqual(calls['selections'], [{'name': '付小春'}])
            task = next((root / 'out').iterdir())
            self.assertEqual([p.name for p in task.iterdir() if p.is_dir()], ['0001_付小春'])

    def test_directory_recursive_natural_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sub').mkdir()
            for name in ('10.wav', '2.wav', 'sub/1.MP3', 'ignore.txt'):
                (root / name).touch()
            self.assertEqual([r['label'] for r in s.local_records(root)], ['2.wav', '10.wav', 'sub/1.MP3'])

    def test_zip_validation_and_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, '不安全'):
                s.save_audio(archive(['../escape.wav']), root / 'bad', 1)
            with self.assertRaisesRegex(ValueError, '预期'):
                s.save_audio(archive(['1.wav']), root / 'bad', 2)
            files = s.save_audio(archive(['nested/1.wav', 'nested/2.wav']), root / 'voice', 2)
            self.assertEqual(len(files), 2)
            self.assertTrue(all(p.is_file() for p in files))

    def test_audio_inspection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            good = root / 'good.wav'
            good.write_bytes(wav_payload())
            seconds, peak, fatal, notes = s.inspect_audio(good)
            self.assertAlmostEqual(seconds, 1.0, places=2)
            self.assertLess(peak, 0)
            self.assertIsNone(fatal)
            self.assertEqual(notes, [])
            silent = root / 'silent.wav'
            silent.write_bytes(wav_payload(value=0))
            self.assertEqual(s.inspect_audio(silent)[2], '音频为静音')
            broken = root / 'broken.wav'
            broken.write_bytes(b'RIFF-test')
            self.assertEqual(s.inspect_audio(broken)[2], 'WAV 无法解析')

    def test_unique_label(self):
        used = set()
        self.assertEqual(s.unique_label('voice', used), 'voice')
        self.assertEqual(s.unique_label('voice', used), 'voice_2')
        self.assertEqual(s.unique_label('Voice', used), 'Voice_3')

    def test_cloud_defaults_shortage_and_groups(self):
        book = Workbook()
        book.active.append(['音频', '性别', '年龄', '省份'])
        book.active.append(['m.wav', '男', 30, '广东'])
        book.active.append(['f.wav', '女', 40, '广东'])
        book.active.append(['old.wav', '男', 70, '北京'])
        buffer = BytesIO()
        book.save(buffer)
        book.close()
        bucket = MagicMock()
        bucket.get_object.return_value.read.return_value = buffer.getvalue()
        with patch('oss2.Bucket', return_value=bucket), patch.object(s, 'config', return_value={'access_key_id': 'k', 'access_key_secret': 's', 'endpoint': 'e', 'bucket': 'b', 'prefix': 'p', 'metadata_file': 'm.xlsx'}):
            records, _ = s.cloud_records([{'count': 1}])
            self.assertEqual(records[0]['label'], 'm.wav')
            records, _ = s.cloud_records([{'count': 1, 'gender': 'female'}, {'count': 1, 'age': 'elder'}])
            self.assertEqual([r['label'] for r in records], ['f.wav', 'old.wav'])
            with self.assertRaisesRegex(ValueError, '人数不足'):
                s.cloud_records([{'count': 2}])
            with self.assertRaisesRegex(ValueError, '重复'):
                s.cloud_records([{'count': 1}, {'count': 1}])

    def test_partial_failure_continues_and_xlsx_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voices = root / 'voices'
            voices.mkdir()
            (voices / '1.wav').write_bytes(wav_payload())
            (voices / '2.wav').write_bytes(wav_payload())
            job = {'text': '=公式、第二句', 'speaker': str(voices), 'output': str(root / 'output')}
            submitted = []
            def synthesize(cfg, speaker, emotion, text_path):
                submitted.append(text_path.read_text(encoding='utf-8'))
                if len(submitted) == 1:
                    raise TimeoutError('超时')
                return archive_payload([('a.wav', wav_payload())])
            with patch.object(s, 'request_audio', side_effect=synthesize) as request, patch.object(s, 'emit'):
                self.assertEqual(s.run(job), 2)
                self.assertEqual(request.call_count, 4)
            self.assertEqual(submitted, ['=公式\n', '第二句\n', '=公式\n', '第二句\n'])
            task = next((root / 'output').iterdir())
            self.assertFalse((task / '.request.txt').exists())
            self.assertEqual(len(list(task.rglob('*.wav'))), 3)
            self.assertFalse(list(task.rglob('*.json')))
            self.assertFalse(list(task.rglob('*.txt')))
            book = load_workbook(task / '合成结果.xlsx')
            self.assertEqual(book.active.max_row, 5)
            self.assertEqual(book.active['L2'].value, '超时')
            self.assertEqual(book.active['L4'].value, '成功')
            self.assertEqual(book.active['D4'].data_type, 's')
            self.assertEqual(book.active['P4'].value, '通过')
            book.close()

    def test_invalid_audio_marks_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voices = root / 'voices'
            voices.mkdir()
            (voices / '1.wav').write_bytes(wav_payload())
            job = {'text': '你好', 'speaker': str(voices), 'output': str(root / 'output')}
            with patch.object(s, 'request_audio', return_value=archive(['a.wav'])), patch.object(s, 'emit'):
                self.assertEqual(s.run(job), 2)
            task = next((root / 'output').iterdir())
            book = load_workbook(task / '合成结果.xlsx')
            self.assertEqual(book.active['L2'].value, '合成失败')
            self.assertIn('音频校验失败', book.active['M2'].value)
            self.assertEqual(book.active['P2'].value, '不通过：WAV 无法解析')
            book.close()

    def test_stop_breaks_immediately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            voices = root / 'voices'
            voices.mkdir()
            for name in ('1.wav', '2.wav', '3.wav'):
                (voices / name).write_bytes(wav_payload())
            job = {'text': '、'.join(f'第{i}句' for i in range(1, 6)), 'speaker': str(voices), 'output': str(root / 'output')}
            calls = []
            def synthesize(*args, **kwargs):
                calls.append(1)
                raise KeyboardInterrupt
            with patch.object(s, 'request_audio', side_effect=synthesize), patch.object(s, 'emit'):
                self.assertEqual(s.run(job), 130)
            self.assertEqual(len(calls), 1)
            task = next((root / 'output').iterdir())
            book = load_workbook(task / '合成结果.xlsx')
            self.assertEqual(book.active.max_row, 2)
            self.assertEqual(book.active['L2'].value, '已中止')
            book.close()

    def test_http_protocol(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            speaker, emotion, text = root / 's.wav', root / 'e.wav', root / 't.txt'
            for path in (speaker, emotion, text):
                path.write_bytes(b'test')
            response = MagicMock()
            response.status = 200
            response.headers.get_content_type.return_value = 'application/zip'
            response.read.return_value = b'zip'
            cfg = {'base_url': 'https://example.test', 'token': 'test', 'request_timeout': 1}
            with patch.object(s.http.client.HTTPSConnection, 'request') as call, patch.object(s.http.client.HTTPSConnection, 'getresponse', return_value=response):
                self.assertEqual(s.request_audio(cfg, speaker, emotion, text), b'zip')
                self.assertEqual(call.call_args.args, ('POST', '/v1/emotion'))
                for field in ('spk_audio_prompt', 'emo_audio_prompt', 'text'):
                    self.assertIn(f'name="{field}"'.encode(), call.call_args.kwargs['body'])

    def test_timeout_actively_disconnects(self):
        for partial_response in (False, True):
            with self.subTest(partial_response=partial_response), tempfile.TemporaryDirectory() as directory, socket.socket() as server:
                server.bind(('127.0.0.1', 0))
                server.listen()
                server.settimeout(3)
                disconnected = threading.Event()
                def serve():
                    with server.accept()[0] as client:
                        client.settimeout(3)
                        data = b''
                        while b'\r\n\r\n' not in data:
                            data += client.recv(4096)
                        headers, body = data.split(b'\r\n\r\n', 1)
                        length = int(next(line.split(b':', 1)[1] for line in headers.split(b'\r\n') if line.lower().startswith(b'content-length:')))
                        while len(body) < length:
                            body += client.recv(4096)
                        if partial_response:
                            client.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/zip\r\nContent-Length: 1000\r\nConnection: close\r\n\r\npartial')
                        try:
                            if client.recv(1) == b'':
                                disconnected.set()
                        except ConnectionResetError:
                            disconnected.set()
                thread = threading.Thread(target=serve, daemon=True)
                thread.start()
                root = Path(directory)
                speaker, text = root / 's.wav', root / 't.txt'
                speaker.write_bytes(b'audio')
                text.write_text('hello')
                cfg = {'base_url': f'http://127.0.0.1:{server.getsockname()[1]}', 'token': 'test', 'request_timeout': .3}
                with self.assertRaises(TimeoutError):
                    s.request_audio(cfg, speaker, None, text)
                self.assertTrue(disconnected.wait(1), '服务端未观察到断连')
                thread.join(1)

    def test_interrupt_closes_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audio, text = root / 's.wav', root / 't.txt'
            audio.write_bytes(b'audio')
            text.write_text('hello')
            connected = threading.Event()
            sock = MagicMock()
            def connect(connection):
                connection.sock = sock
            def response(connection):
                connected.set()
                time.sleep(.1)
                raise OSError('closed')
            def interrupt(*args, **kwargs):
                self.assertTrue(connected.wait(1))
                raise KeyboardInterrupt
            cfg = {'base_url': 'http://example.test', 'token': 'test', 'request_timeout': 10}
            with patch.object(s.http.client.HTTPConnection, 'connect', connect), patch.object(s.http.client.HTTPConnection, 'getresponse', response), patch.object(s.queue.Queue, 'get', side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    s.request_audio(cfg, audio, None, text)
            sock.shutdown.assert_called_with(socket.SHUT_RDWR)
            self.assertTrue(sock.close.called)


if __name__ == '__main__':
    unittest.main()
