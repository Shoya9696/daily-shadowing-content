#!/usr/bin/env python3
"""Unit tests for post-deployment Pages validation (no network, sleep mocked)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / '.github' / 'scripts'
sys.path.insert(0, str(SCRIPT_DIR))

import validate_pages_deployment as v  # noqa: E402

BASE_URL = 'https://shoya9696.github.io/daily-shadowing-content'


def _manifest(lesson_date: str = '2026-07-20') -> dict:
    return {
        'lessonDate': lesson_date,
        'version': 1,
        'lessons': [
            {
                'levelGroup': 'beginner',
                'audioUrl': f'{BASE_URL}/audio/{lesson_date}/beginner.m4a',
                'sentences': [
                    {
                        'text': 'Hello.',
                        'sentenceAudioUrl': f'{BASE_URL}/audio/{lesson_date}/beginner-s01.m4a',
                    }
                ],
            },
            {
                'levelGroup': 'intermediate',
                'audioUrl': f'{BASE_URL}/audio/{lesson_date}/intermediate.m4a',
                'sentences': [
                    {
                        'text': 'Hello again.',
                        'sentenceAudioUrl': f'{BASE_URL}/audio/{lesson_date}/intermediate-s01.m4a',
                    }
                ],
            },
            {
                'levelGroup': 'advanced',
                'audioUrl': f'{BASE_URL}/audio/{lesson_date}/advanced.m4a',
                'sentences': [
                    {
                        'text': 'Hello once more.',
                        'sentenceAudioUrl': f'{BASE_URL}/audio/{lesson_date}/advanced-s01.m4a',
                    }
                ],
            },
        ],
    }


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


class RecordingUrlOpen:
    def __init__(self, responses: dict[str, list[v.HttpResult]]) -> None:
        self.responses = responses
        self.requests: list[Request] = []

    def __call__(self, request: Request, timeout: float) -> v.HttpResult:
        self.requests.append(request)
        key = request.full_url.split('?', 1)[0]
        queue = self.responses.get(key)
        if not queue:
            raise AssertionError(f'unexpected URL: {request.full_url}')
        return queue.pop(0)


def _json_result(url: str, payload: dict, status: int = 200) -> v.HttpResult:
    body = json.dumps(payload).encode('utf-8')
    return v.HttpResult(
        url=url,
        status=status,
        headers={'content-type': 'application/json', 'content-length': str(len(body))},
        body=body,
    )


def _audio_result(url: str, status: int = 200, content_type: str = 'audio/mp4') -> v.HttpResult:
    return v.HttpResult(
        url=url,
        status=status,
        headers={'content-type': content_type, 'content-length': '128'},
        body=b'\x00\x01\x02\x03',
    )


def _ok_responses(manifest: dict) -> dict[str, list[v.HttpResult]]:
    lesson_date = manifest['lessonDate']
    latest = f'{BASE_URL}/latest.json'
    lesson = f'{BASE_URL}/lessons/{lesson_date}.json'
    index = f'{BASE_URL}/index.json'
    responses: dict[str, list[v.HttpResult]] = {
        latest: [_json_result(latest, manifest)],
        lesson: [_json_result(lesson, manifest)],
        index: [
            _json_result(
                index,
                {
                    'schemaVersion': 1,
                    'generatedAtUtc': '2026-07-20T00:00:00Z',
                    'latestLessonDate': lesson_date,
                    'days': [],
                },
            )
        ],
    }
    for lesson in manifest['lessons']:
        responses[lesson['audioUrl']] = [_audio_result(lesson['audioUrl'])]
        for sentence in lesson['sentences']:
            url = sentence['sentenceAudioUrl']
            responses[url] = [_audio_result(url)]
    return responses


class AllowlistTests(unittest.TestCase):
    def test_allows_expected_origin(self) -> None:
        self.assertTrue(v.is_allowed_pages_url(f'{BASE_URL}/latest.json', base_url=BASE_URL))

    def test_rejects_other_domain(self) -> None:
        self.assertFalse(
            v.is_allowed_pages_url('https://evil.example/latest.json', base_url=BASE_URL)
        )

    def test_rejects_http(self) -> None:
        self.assertFalse(
            v.is_allowed_pages_url(
                'http://shoya9696.github.io/daily-shadowing-content/latest.json',
                base_url=BASE_URL,
            )
        )

    def test_build_url_checks_rejects_off_origin_audio(self) -> None:
        manifest = _manifest()
        manifest['lessons'][0]['audioUrl'] = 'https://evil.example/a.m4a'
        with self.assertRaises(v.PagesValidationError):
            v.build_url_checks(
                base_url=BASE_URL,
                lesson_date='2026-07-20',
                manifest=manifest,
                check_index=True,
            )


class CacheBustTests(unittest.TestCase):
    def test_adds_query_param(self) -> None:
        url = v.with_cache_bust(f'{BASE_URL}/latest.json', token='123')
        self.assertEqual(url, f'{BASE_URL}/latest.json?v=123')

    def test_appends_to_existing_query(self) -> None:
        url = v.with_cache_bust(f'{BASE_URL}/latest.json?x=1', token='9')
        self.assertEqual(url, f'{BASE_URL}/latest.json?x=1&v=9')


class ValidationFlowTests(unittest.TestCase):
    def test_immediate_success(self) -> None:
        manifest = _manifest()
        opener = RecordingUrlOpen(_ok_responses(manifest))
        clock = FakeClock()
        summary = v.validate_pages_deployment(
            base_url=BASE_URL,
            lesson_date='2026-07-20',
            manifest=manifest,
            expected_latest_date='2026-07-20',
            max_wait_seconds=300,
            retry_interval=15,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            urlopen_fn=opener,
            cache_bust_token='t',
        )
        self.assertTrue(summary['ok'])
        self.assertEqual(summary['attempts'], 1)
        self.assertEqual(clock.sleeps, [])
        self.assertTrue(any('v=t-1' in req.full_url for req in opener.requests))

    def test_retry_then_success(self) -> None:
        manifest = _manifest()
        ok = _ok_responses(manifest)
        responses: dict[str, list[v.HttpResult]] = {}
        latest = f'{BASE_URL}/latest.json'
        for key, queue in ok.items():
            first = queue[0]
            if key == latest:
                responses[key] = [
                    v.HttpResult(latest, 404, {'content-type': 'text/plain'}, b'missing'),
                    first,
                ]
            else:
                responses[key] = [first, first]

        opener = RecordingUrlOpen(responses)
        clock = FakeClock()
        summary = v.validate_pages_deployment(
            base_url=BASE_URL,
            lesson_date='2026-07-20',
            manifest=manifest,
            expected_latest_date='2026-07-20',
            max_wait_seconds=300,
            retry_interval=15,
            sleep_fn=clock.sleep,
            monotonic_fn=clock.monotonic,
            urlopen_fn=opener,
            cache_bust_token='t',
        )
        self.assertEqual(summary['attempts'], 2)
        self.assertEqual(clock.sleeps, [15])

    def test_max_wait_failure_without_fixed_300_sleep(self) -> None:
        manifest = _manifest()
        responses = {
            f'{BASE_URL}/latest.json': [
                v.HttpResult(
                    f'{BASE_URL}/latest.json',
                    404,
                    {'content-type': 'text/plain'},
                    b'missing',
                )
                for _ in range(30)
            ],
            f'{BASE_URL}/lessons/2026-07-20.json': [
                v.HttpResult(
                    f'{BASE_URL}/lessons/2026-07-20.json',
                    404,
                    {'content-type': 'text/plain'},
                    b'missing',
                )
                for _ in range(30)
            ],
            f'{BASE_URL}/index.json': [
                v.HttpResult(
                    f'{BASE_URL}/index.json',
                    404,
                    {'content-type': 'text/plain'},
                    b'missing',
                )
                for _ in range(30)
            ],
        }
        for lesson in manifest['lessons']:
            responses[lesson['audioUrl']] = [
                v.HttpResult(lesson['audioUrl'], 404, {}, b'') for _ in range(30)
            ]
            for sentence in lesson['sentences']:
                url = sentence['sentenceAudioUrl']
                responses[url] = [v.HttpResult(url, 404, {}, b'') for _ in range(30)]

        opener = RecordingUrlOpen(responses)
        clock = FakeClock()
        with self.assertRaises(v.PagesValidationError):
            v.validate_pages_deployment(
                base_url=BASE_URL,
                lesson_date='2026-07-20',
                manifest=manifest,
                expected_latest_date='2026-07-20',
                max_wait_seconds=300,
                retry_interval=15,
                sleep_fn=clock.sleep,
                monotonic_fn=clock.monotonic,
                urlopen_fn=opener,
                cache_bust_token='t',
            )
        self.assertTrue(clock.sleeps)
        self.assertNotIn(300, clock.sleeps)
        self.assertLessEqual(sum(clock.sleeps), 300)
        self.assertGreaterEqual(clock.now, 300)

    def test_lesson_date_mismatch(self) -> None:
        manifest = _manifest('2026-07-20')
        remote = _manifest('2026-07-19')
        responses = _ok_responses(remote)
        opener = RecordingUrlOpen(responses)
        with self.assertRaises(v.PagesValidationError):
            v.validate_pages_deployment(
                base_url=BASE_URL,
                lesson_date='2026-07-20',
                manifest=manifest,
                expected_latest_date='2026-07-20',
                max_wait_seconds=0,
                retry_interval=15,
                urlopen_fn=opener,
                cache_bust_token='t',
            )

    def test_missing_level_fails(self) -> None:
        manifest = _manifest()
        manifest['lessons'] = manifest['lessons'][:2]
        with self.assertRaises(v.PagesValidationError):
            v.validate_pages_deployment(
                base_url=BASE_URL,
                lesson_date='2026-07-20',
                manifest=manifest,
                expected_latest_date='2026-07-20',
                max_wait_seconds=0,
                retry_interval=15,
                urlopen_fn=RecordingUrlOpen({}),
                cache_bust_token='t',
            )

    def test_invalid_audio_content_type(self) -> None:
        manifest = _manifest()
        responses = _ok_responses(manifest)
        bad_url = manifest['lessons'][0]['audioUrl']
        responses[bad_url] = [
            _audio_result(bad_url, content_type='text/html'),
            _audio_result(bad_url, content_type='text/html'),
        ]
        opener = RecordingUrlOpen(responses)
        with self.assertRaises(v.PagesValidationError) as ctx:
            v.validate_pages_deployment(
                base_url=BASE_URL,
                lesson_date='2026-07-20',
                manifest=manifest,
                expected_latest_date='2026-07-20',
                max_wait_seconds=0,
                retry_interval=15,
                urlopen_fn=opener,
                cache_bust_token='t',
            )
        self.assertTrue(any('content-type not allowed' in msg for msg in ctx.exception.failures))

    def test_idempotent_repeated_success(self) -> None:
        manifest = _manifest()
        for _ in range(2):
            opener = RecordingUrlOpen(_ok_responses(manifest))
            summary = v.validate_pages_deployment(
                base_url=BASE_URL,
                lesson_date='2026-07-20',
                manifest=manifest,
                expected_latest_date='2026-07-20',
                max_wait_seconds=300,
                retry_interval=15,
                urlopen_fn=opener,
                cache_bust_token='t',
            )
            self.assertTrue(summary['ok'])


class MainCliTests(unittest.TestCase):
    def test_main_reads_repo_latest_json(self) -> None:
        manifest = _manifest()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / 'latest.json').write_text(json.dumps(manifest), encoding='utf-8')
            opener = RecordingUrlOpen(_ok_responses(manifest))
            with mock.patch.object(v, 'default_urlopen_factory', return_value=opener):
                code = v.main(
                    [
                        '--repo-root',
                        str(root),
                        '--base-url',
                        BASE_URL,
                        '--max-wait-seconds',
                        '0',
                    ]
                )
            self.assertEqual(code, 0)

    def test_require_today_jst_mismatch(self) -> None:
        manifest = _manifest('2026-01-01')
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / 'latest.json').write_text(json.dumps(manifest), encoding='utf-8')
            with mock.patch.object(v, 'today_jst', return_value='2026-07-20'):
                code = v.main(
                    [
                        '--repo-root',
                        str(root),
                        '--require-today-jst',
                        '--max-wait-seconds',
                        '0',
                    ]
                )
            self.assertEqual(code, 1)


class RedirectHandlerTests(unittest.TestCase):
    def test_redirect_handler_allows_same_origin(self) -> None:
        handler = v._OriginBoundRedirectHandler(base_url=BASE_URL)
        req = Request(f'{BASE_URL}/latest.json')
        redirected = handler.redirect_request(
            req,
            fp=None,
            code=302,
            msg='Found',
            headers={'Location': f'{BASE_URL}/lessons/2026-07-20.json'},
            newurl=f'{BASE_URL}/lessons/2026-07-20.json',
        )
        self.assertIsNotNone(redirected)
        self.assertEqual(redirected.full_url, f'{BASE_URL}/lessons/2026-07-20.json')

    def test_redirect_handler_rejects_off_origin(self) -> None:
        handler = v._OriginBoundRedirectHandler(base_url=BASE_URL)
        req = Request(f'{BASE_URL}/latest.json')
        with self.assertRaises(v.PagesValidationError):
            handler.redirect_request(
                req,
                fp=None,
                code=302,
                msg='Found',
                headers={'Location': 'https://evil.example/steal'},
                newurl='https://evil.example/steal',
            )

    def test_default_urlopen_factory_refuses_off_origin_request(self) -> None:
        opener = v.default_urlopen_factory(BASE_URL)
        request = Request('https://evil.example/latest.json')
        with self.assertRaises(v.PagesValidationError):
            opener(request, timeout=1)


class IndexValidationTests(unittest.TestCase):
    def test_index_latest_lesson_date_must_match_expected(self) -> None:
        error = v._validate_json_payload(
            url=f'{BASE_URL}/index.json',
            kind='index',
            payload={
                'schemaVersion': 1,
                'generatedAtUtc': '2026-07-20T00:00:00Z',
                'latestLessonDate': '2026-07-19',
                'days': [],
            },
            lesson_date='2026-07-20',
            expected_latest_date='2026-07-20',
        )
        self.assertIsNotNone(error)
        self.assertIn('latestLessonDate mismatch', error or '')


class EventFilterDocumentationTests(unittest.TestCase):
    def test_workflow_yaml_filters_success_github_pages_main(self) -> None:
        workflow = (ROOT / '.github' / 'workflows' / 'validate_pages_deployment.yml').read_text(
            encoding='utf-8'
        )
        self.assertIn('deployment_status', workflow)
        self.assertIn("github.event.deployment.environment == 'github-pages'", workflow)
        self.assertIn("github.event.deployment_status.state == 'success'", workflow)
        self.assertIn("github.event.deployment.ref == 'main'", workflow)
        self.assertIn('report-pages-failure', workflow)
        self.assertNotIn('sleep 300', workflow)
        self.assertIn('ubuntu-latest', workflow)
        self.assertIn('timeout-minutes: 15', workflow)
        self.assertIn('01:00 JST', workflow)


if __name__ == '__main__':
    unittest.main()
