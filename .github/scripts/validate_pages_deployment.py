#!/usr/bin/env python3
"""Validate public GitHub Pages content after deployment (no Secrets required)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from zoneinfo import ZoneInfo

DEFAULT_PAGES_BASE_URL = 'https://shoya9696.github.io/daily-shadowing-content'
DEFAULT_MAX_WAIT_SECONDS = 300
DEFAULT_RETRY_INTERVAL_SECONDS = 15
DEFAULT_REQUEST_TIMEOUT_SECONDS = 20
REQUIRED_LEVELS = ('beginner', 'intermediate', 'advanced')
AUDIO_CONTENT_TYPE_PREFIXES = ('audio/',)
AUDIO_CONTENT_TYPES = frozenset(
    {
        'application/octet-stream',
        'application/mp4',
        'binary/octet-stream',
    }
)
RANGE_READ_BYTES = 4096
JST = ZoneInfo('Asia/Tokyo')


@dataclass(frozen=True)
class HttpResult:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class UrlCheck:
    url: str
    kind: str


@dataclass(frozen=True)
class UrlValidationFailure:
    check: UrlCheck
    message: str


@dataclass(frozen=True)
class ValidationRoundResult:
    failures: list[UrlValidationFailure]
    latest_status: int | None = None
    latest_lesson_date: str | None = None
    lesson_status: int | None = None
    index_status: int | None = None


class PagesValidationError(Exception):
    def __init__(
        self,
        message: str,
        failures: list[str] | None = None,
        categories: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.failures = failures or []
        self.categories = categories or []


UrlOpenFn = Callable[[Request, float], HttpResult]
SleepFn = Callable[[float], None]
MonotonicFn = Callable[[], float]


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip('/')


def expected_origin_and_path(base_url: str) -> tuple[str, str]:
    parsed = urlparse(normalize_base_url(base_url))
    if parsed.scheme != 'https' or not parsed.netloc:
        raise ValueError(f'PAGES_BASE_URL must be https with a host: {base_url!r}')
    path = parsed.path.rstrip('/') or ''
    return f'{parsed.scheme}://{parsed.netloc}'.lower(), path


def is_allowed_pages_url(url: str, *, base_url: str) -> bool:
    try:
        expected_origin, expected_path = expected_origin_and_path(base_url)
    except ValueError:
        return False
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        return False
    origin = f'{parsed.scheme}://{parsed.netloc}'.lower()
    if origin != expected_origin:
        return False
    path = parsed.path or '/'
    if expected_path:
        return path == expected_path or path.startswith(expected_path + '/')
    return True


def assert_allowed_pages_url(url: str, *, base_url: str) -> None:
    if not is_allowed_pages_url(url, base_url=base_url):
        raise PagesValidationError(
            f'refused URL outside expected Pages origin: {url} '
            f'(allowed under {normalize_base_url(base_url)}/)'
        )


def with_cache_bust(url: str, *, token: str) -> str:
    parsed = urlparse(url)
    query = parsed.query
    bust = f'v={token}'
    new_query = f'{query}&{bust}' if query else bust
    return urlunparse(parsed._replace(query=new_query))


def _normalize_headers(raw_headers: Any) -> dict[str, str]:
    if hasattr(raw_headers, 'items'):
        return {str(key).lower(): str(value) for key, value in raw_headers.items()}
    return {}


class _OriginBoundRedirectHandler(HTTPRedirectHandler):
    def __init__(self, *, base_url: str) -> None:
        super().__init__()
        self._base_url = base_url

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        assert_allowed_pages_url(newurl, base_url=self._base_url)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_urlopen_factory(base_url: str) -> UrlOpenFn:
    opener = build_opener(_OriginBoundRedirectHandler(base_url=base_url))

    def _open(request: Request, timeout: float) -> HttpResult:
        assert_allowed_pages_url(request.full_url, base_url=base_url)
        try:
            with opener.open(request, timeout=timeout) as response:
                body = response.read()
                return HttpResult(
                    url=request.full_url,
                    status=getattr(response, 'status', 200),
                    headers=_normalize_headers(response.headers),
                    body=body,
                )
        except HTTPError as exc:
            body = exc.read() if hasattr(exc, 'read') else b''
            return HttpResult(
                url=request.full_url,
                status=exc.code,
                headers=_normalize_headers(exc.headers),
                body=body,
            )

    return _open


def read_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise PagesValidationError(f'{path} root must be a JSON object')
    return payload


def require_three_levels(manifest: dict) -> None:
    lessons = manifest.get('lessons')
    if not isinstance(lessons, list):
        raise PagesValidationError('manifest.lessons must be a list')
    levels = {
        lesson.get('levelGroup')
        for lesson in lessons
        if isinstance(lesson, dict) and isinstance(lesson.get('levelGroup'), str)
    }
    missing = [level for level in REQUIRED_LEVELS if level not in levels]
    if missing:
        raise PagesValidationError(f'manifest missing required levelGroup(s): {missing}')


def build_url_checks(
    *,
    base_url: str,
    lesson_date: str,
    manifest: dict,
    check_index: bool,
) -> list[UrlCheck]:
    normalized_base = normalize_base_url(base_url)
    checks = [
        UrlCheck(f'{normalized_base}/latest.json', 'latest'),
        UrlCheck(f'{normalized_base}/lessons/{lesson_date}.json', 'lesson'),
    ]
    if check_index:
        checks.append(UrlCheck(f'{normalized_base}/index.json', 'index'))

    lessons = manifest.get('lessons')
    if isinstance(lessons, list):
        for lesson_index, lesson in enumerate(lessons):
            if not isinstance(lesson, dict):
                continue
            audio_url = lesson.get('audioUrl')
            if isinstance(audio_url, str) and audio_url.strip():
                checks.append(UrlCheck(audio_url.strip(), f'audio[{lesson_index}]'))
            sentences = lesson.get('sentences')
            if not isinstance(sentences, list):
                continue
            for sentence_index, sentence in enumerate(sentences):
                if not isinstance(sentence, dict):
                    continue
                sentence_audio_url = sentence.get('sentenceAudioUrl')
                if isinstance(sentence_audio_url, str) and sentence_audio_url.strip():
                    checks.append(
                        UrlCheck(
                            sentence_audio_url.strip(),
                            f'sentenceAudio[{lesson_index}][{sentence_index}]',
                        )
                    )

    for check in checks:
        assert_allowed_pages_url(check.url, base_url=base_url)
    return checks


def _content_length(headers: dict[str, str]) -> int | None:
    raw = headers.get('content-length')
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _content_type(headers: dict[str, str]) -> str:
    raw = headers.get('content-type', '')
    return raw.split(';', 1)[0].strip().lower()


def is_allowed_audio_content_type(content_type: str) -> bool:
    if not content_type:
        return False
    if content_type in AUDIO_CONTENT_TYPES:
        return True
    return any(content_type.startswith(prefix) for prefix in AUDIO_CONTENT_TYPE_PREFIXES)


def _fetch(
    url: str,
    *,
    method: str,
    timeout: float,
    urlopen_fn: UrlOpenFn,
    cache_bust_token: str | None,
    range_header: str | None = None,
) -> HttpResult:
    target = with_cache_bust(url, token=cache_bust_token) if cache_bust_token else url
    headers = {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
    }
    if range_header is not None:
        headers['Range'] = range_header
    request = Request(target, method=method, headers=headers)
    return urlopen_fn(request, timeout)


def _validate_json_payload(
    *,
    url: str,
    kind: str,
    payload: object,
    lesson_date: str,
    expected_latest_date: str,
) -> str | None:
    if not isinstance(payload, dict):
        return f'{kind} JSON root must be an object'

    if kind == 'latest':
        for key in ('lessonDate', 'version', 'lessons'):
            if key not in payload:
                return f'latest.json missing required key: {key}'
        lesson_date_value = payload.get('lessonDate')
        if lesson_date_value != expected_latest_date:
            return (
                f'latest.json lessonDate mismatch: expected {expected_latest_date!r}, '
                f'got {lesson_date_value!r}'
            )
        try:
            require_three_levels(payload)
        except PagesValidationError as exc:
            return str(exc)
        return None

    if kind == 'lesson':
        for key in ('lessonDate', 'version', 'lessons'):
            if key not in payload:
                return f'lesson JSON missing required key: {key}'
        lesson_date_value = payload.get('lessonDate')
        if lesson_date_value != lesson_date:
            return (
                f'lesson JSON lessonDate mismatch: expected {lesson_date!r}, '
                f'got {lesson_date_value!r}'
            )
        try:
            require_three_levels(payload)
        except PagesValidationError as exc:
            return str(exc)
        return None

    if kind == 'index':
        schema_version = payload.get('schemaVersion')
        if schema_version != 1:
            return (
                f'index.json schemaVersion mismatch: expected 1, got {schema_version!r} '
                f'({url})'
            )
        generated_at = payload.get('generatedAtUtc')
        if not isinstance(generated_at, str) or not generated_at.strip():
            return f'index.json missing or invalid generatedAtUtc ({url})'
        latest_lesson_date = payload.get('latestLessonDate')
        if not isinstance(latest_lesson_date, str) or not latest_lesson_date.strip():
            return f'index.json missing or invalid latestLessonDate ({url})'
        if 'days' not in payload:
            return f'index.json missing required key: days ({url})'
        if not isinstance(payload.get('days'), list):
            return f'index.json days must be a list ({url})'
        return None

    return f'unsupported JSON kind: {kind}'


def _validate_json_url(
    check: UrlCheck,
    *,
    lesson_date: str,
    expected_latest_date: str,
    timeout: float,
    urlopen_fn: UrlOpenFn,
    cache_bust_token: str,
) -> tuple[str | None, int | None, str | None]:
    result = _fetch(
        check.url,
        method='GET',
        timeout=timeout,
        urlopen_fn=urlopen_fn,
        cache_bust_token=cache_bust_token,
    )
    if result.status != 200:
        return (
            (
                f'{check.kind} URL failed: {check.url} '
                f'(status={result.status}, content-type={_content_type(result.headers)!r}, '
                f'content-length={_content_length(result.headers)!r})'
            ),
            result.status,
            None,
        )
    try:
        payload = json.loads(result.body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return (
            f'{check.kind} URL JSON parse failed: {check.url} ({exc})',
            result.status,
            None,
        )
    lesson_date_value = payload.get('lessonDate') if isinstance(payload, dict) else None
    parsed_lesson_date = lesson_date_value if isinstance(lesson_date_value, str) else None
    payload_error = _validate_json_payload(
        url=check.url,
        kind=check.kind,
        payload=payload,
        lesson_date=lesson_date,
        expected_latest_date=expected_latest_date,
    )
    return payload_error, result.status, parsed_lesson_date


def _validate_audio_url(
    check: UrlCheck,
    *,
    timeout: float,
    urlopen_fn: UrlOpenFn,
    cache_bust_token: str,
) -> str | None:
    head_result = _fetch(
        check.url,
        method='HEAD',
        timeout=timeout,
        urlopen_fn=urlopen_fn,
        cache_bust_token=cache_bust_token,
    )
    if head_result.status == 200:
        content_type = _content_type(head_result.headers)
        if not is_allowed_audio_content_type(content_type):
            return (
                f'{check.kind} URL content-type not allowed: {check.url} '
                f'(content-type={content_type!r})'
            )
        content_length = _content_length(head_result.headers)
        if content_length is not None:
            if content_length <= 0:
                return (
                    f'{check.kind} URL empty audio payload: {check.url} '
                    f'(content-length={content_length})'
                )
            return None

    get_result = _fetch(
        check.url,
        method='GET',
        timeout=timeout,
        urlopen_fn=urlopen_fn,
        cache_bust_token=cache_bust_token,
        range_header=f'bytes=0-{RANGE_READ_BYTES - 1}',
    )
    if get_result.status not in {200, 206}:
        return (
            f'{check.kind} URL failed: {check.url} '
            f'(status={get_result.status}, content-type={_content_type(get_result.headers)!r}, '
            f'content-length={_content_length(get_result.headers)!r})'
        )
    content_type = _content_type(get_result.headers)
    if not is_allowed_audio_content_type(content_type):
        return (
            f'{check.kind} URL content-type not allowed: {check.url} '
            f'(content-type={content_type!r})'
        )
    content_length = _content_length(get_result.headers)
    if content_length is not None and content_length <= 0:
        return (
            f'{check.kind} URL empty audio payload: {check.url} '
            f'(content-length={content_length})'
        )
    if not get_result.body:
        return f'{check.kind} URL empty audio payload after range read: {check.url}'
    return None


def validate_published_url_failures(
    checks: list[UrlCheck],
    *,
    lesson_date: str,
    expected_latest_date: str,
    timeout: float,
    urlopen_fn: UrlOpenFn,
    cache_bust_token: str,
) -> ValidationRoundResult:
    failures: list[UrlValidationFailure] = []
    latest_status: int | None = None
    latest_lesson_date: str | None = None
    lesson_status: int | None = None
    index_status: int | None = None
    for check in checks:
        try:
            if check.kind in {'latest', 'lesson', 'index'}:
                error, status, parsed_lesson_date = _validate_json_url(
                    check,
                    lesson_date=lesson_date,
                    expected_latest_date=expected_latest_date,
                    timeout=timeout,
                    urlopen_fn=urlopen_fn,
                    cache_bust_token=cache_bust_token,
                )
                if check.kind == 'latest':
                    latest_status = status
                    latest_lesson_date = parsed_lesson_date
                elif check.kind == 'lesson':
                    lesson_status = status
                else:
                    index_status = status
            else:
                error = _validate_audio_url(
                    check,
                    timeout=timeout,
                    urlopen_fn=urlopen_fn,
                    cache_bust_token=cache_bust_token,
                )
        except PagesValidationError as exc:
            error = str(exc)
        except URLError as exc:
            error = f'{check.kind} URL request failed: {check.url} ({exc.reason})'
        except Exception as exc:  # noqa: BLE001
            error = f'{check.kind} URL request failed: {check.url} ({exc})'
        if error is not None:
            failures.append(UrlValidationFailure(check=check, message=error))
    return ValidationRoundResult(
        failures=failures,
        latest_status=latest_status,
        latest_lesson_date=latest_lesson_date,
        lesson_status=lesson_status,
        index_status=index_status,
    )


def validate_pages_deployment(
    *,
    base_url: str,
    lesson_date: str,
    manifest: dict,
    expected_latest_date: str,
    check_index: bool = True,
    max_wait_seconds: float = DEFAULT_MAX_WAIT_SECONDS,
    retry_interval: float = DEFAULT_RETRY_INTERVAL_SECONDS,
    timeout: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    sleep_fn: SleepFn = time.sleep,
    monotonic_fn: MonotonicFn = time.monotonic,
    urlopen_fn: UrlOpenFn | None = None,
    cache_bust_token: str | None = None,
) -> dict[str, Any]:
    if max_wait_seconds < 0:
        raise ValueError('max_wait_seconds must be non-negative')
    if retry_interval <= 0:
        raise ValueError('retry_interval must be positive')

    require_three_levels(manifest)
    opener = urlopen_fn or default_urlopen_factory(base_url)
    checks = build_url_checks(
        base_url=base_url,
        lesson_date=lesson_date,
        manifest=manifest,
        check_index=check_index,
    )
    if not checks:
        raise PagesValidationError('no URLs to validate')

    started = monotonic_fn()
    deadline = started + max_wait_seconds
    attempt = 0
    last_failures: list[UrlValidationFailure] = []
    bust_token = cache_bust_token or str(int(time.time()))

    while True:
        attempt += 1
        round_result = validate_published_url_failures(
            checks,
            lesson_date=lesson_date,
            expected_latest_date=expected_latest_date,
            timeout=timeout,
            urlopen_fn=opener,
            cache_bust_token=f'{bust_token}-{attempt}',
        )
        elapsed = monotonic_fn() - started
        if not round_result.failures:
            summary = {
                'ok': True,
                'attempts': attempt,
                'elapsed_seconds': round(elapsed, 3),
                'lesson_date': lesson_date,
                'expected_latest_date': expected_latest_date,
            }
            print(
                f'[validate-pages] attempt {attempt} succeeded in {elapsed:.1f}s '
                f'for lessonDate={lesson_date}'
            )
            return summary

        last_failures = round_result.failures
        print(
            f'[validate-pages] attempt {attempt} failed '
            f'(elapsed={elapsed:.1f}s/{max_wait_seconds:.0f}s): '
            f'{len(last_failures)} issue(s)'
        )
        for failure in last_failures:
            print(f'[validate-pages] {failure.message}')

        remaining = deadline - monotonic_fn()
        if remaining <= 0:
            break
        sleep_fn(min(retry_interval, remaining))

    raise PagesValidationError(
        f'published URL validation failed after {attempt} attempt(s) '
        f'(max_wait={max_wait_seconds:.0f}s) for lessonDate={lesson_date}',
        failures=[failure.message for failure in last_failures],
    )


def today_jst() -> str:
    return datetime.now(JST).date().isoformat()


def write_github_summary(lines: list[str]) -> None:
    summary_path = os.environ.get('GITHUB_STEP_SUMMARY')
    if not summary_path:
        return
    with open(summary_path, 'a', encoding='utf-8') as handle:
        handle.write('\n'.join(lines) + '\n')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Validate GitHub Pages deployment content')
    parser.add_argument(
        '--repo-root',
        type=Path,
        default=Path.cwd(),
        help='Content repo checkout root containing latest.json',
    )
    parser.add_argument('--base-url', default=None)
    parser.add_argument('--lesson-date', default=None)
    parser.add_argument('--expected-latest-date', default=None)
    parser.add_argument('--check-index', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--max-wait-seconds', type=float, default=DEFAULT_MAX_WAIT_SECONDS)
    parser.add_argument('--retry-interval', type=float, default=DEFAULT_RETRY_INTERVAL_SECONDS)
    parser.add_argument('--timeout', type=float, default=DEFAULT_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument(
        '--require-today-jst',
        action='store_true',
        help='Fail when latest.json lessonDate != today in Asia/Tokyo (schedule fallback)',
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root.resolve()
    latest_path = repo_root / 'latest.json'
    if not latest_path.is_file():
        print(f'[error] missing {latest_path}')
        return 1

    try:
        manifest = read_json(latest_path)
    except (OSError, json.JSONDecodeError, PagesValidationError) as exc:
        print(f'[error] failed to read latest.json: {exc}')
        return 1

    lesson_date = args.lesson_date or manifest.get('lessonDate')
    if not isinstance(lesson_date, str) or not lesson_date.strip():
        print('[error] latest.json lessonDate is missing or invalid')
        return 1
    expected_latest_date = args.expected_latest_date or lesson_date
    base_url = args.base_url or os.environ.get('PAGES_BASE_URL') or DEFAULT_PAGES_BASE_URL

    if args.require_today_jst:
        expected_today = today_jst()
        if lesson_date != expected_today:
            message = (
                f'scheduled fallback: latest.json lessonDate={lesson_date!r} '
                f'does not match today JST={expected_today!r}'
            )
            print(f'[error] {message}')
            write_github_summary(
                [
                    '## Pages validation failed',
                    '',
                    f'- reason: `{message}`',
                ]
            )
            return 1

    event_name = os.environ.get('EVENT_NAME') or os.environ.get('GITHUB_EVENT_NAME') or 'local'
    deployment_sha = os.environ.get('DEPLOYMENT_SHA') or os.environ.get('GITHUB_SHA') or 'unknown'

    try:
        summary = validate_pages_deployment(
            base_url=base_url,
            lesson_date=lesson_date,
            manifest=manifest,
            expected_latest_date=expected_latest_date,
            check_index=args.check_index,
            max_wait_seconds=args.max_wait_seconds,
            retry_interval=args.retry_interval,
            timeout=args.timeout,
        )
    except PagesValidationError as exc:
        print(f'[error] {exc}')
        for failure in exc.failures:
            print(f'  - {failure}')
        write_github_summary(
            [
                '## Pages validation failed',
                '',
                f'- event: `{event_name}`',
                f'- deployment_sha: `{deployment_sha}`',
                f'- lessonDate: `{lesson_date}`',
                f'- base_url: `{normalize_base_url(base_url)}`',
                f'- error: `{exc}`',
            ]
        )
        return 1

    write_github_summary(
        [
            '## Pages validation succeeded',
            '',
            f'- event: `{event_name}`',
            f'- deployment_sha: `{deployment_sha}`',
            f'- lessonDate: `{summary["lesson_date"]}`',
            f'- attempts: `{summary["attempts"]}`',
            f'- elapsed_seconds: `{summary["elapsed_seconds"]}`',
            f'- base_url: `{normalize_base_url(base_url)}`',
        ]
    )
    print('[validate-pages] all published URLs are reachable')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
