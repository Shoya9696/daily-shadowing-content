#!/usr/bin/env python3
"""Generate manual sample lesson JSON and m4a audio for Step 9-C."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / 'audio' / '2026-06-23'
LESSON_DATE = '2026-06-23'
BASE_URL = 'https://shoya9696.github.io/daily-shadowing-content'
GAP_MS = 400
VOICE = 'Samantha'


@dataclass
class SentenceSpec:
    text: str
    translation_ja: str


@dataclass
class LessonSpec:
    lesson_id: str
    level_group: str
    title: str
    cefr_level: str
    summary_ja: str
    source_urls: list[str]
    sentences: list[SentenceSpec]
    vocabulary: list[dict[str, str]]


LESSONS: list[LessonSpec] = [
    LessonSpec(
        lesson_id='beginner-2026-06-23',
        level_group='beginner',
        title='Sunny Morning Weather',
        cefr_level='A2',
        summary_ja='朝の天気を確認して、軽い服装で出かける短い会話です。',
        source_urls=['https://www.weather.gov/education'],
        sentences=[
            SentenceSpec("Today's weather is sunny and warm.", '今日の天気は晴れて暖かいです。'),
            SentenceSpec('I checked the forecast before I left home.', '家を出る前に天気予報を確認しました。'),
            SentenceSpec('A light jacket is enough for the morning.', '朝は薄手のジャケットで十分です。'),
            SentenceSpec('The sky looks clear after lunch.', '昼過ぎも空は晴れていそうです。'),
        ],
        vocabulary=[
            {'word': 'weather', 'meaningJa': '天気', 'exampleEn': 'The weather is nice today.', 'exampleJa': '今日は天気がいいです。'},
            {'word': 'forecast', 'meaningJa': '予報', 'exampleEn': 'I read the weather forecast.', 'exampleJa': '天気予報を読みました。'},
            {'word': 'sunny', 'meaningJa': '晴れた', 'exampleEn': 'It is sunny outside.', 'exampleJa': '外は晴れています。'},
            {'word': 'jacket', 'meaningJa': 'ジャケット', 'exampleEn': 'She wore a light jacket.', 'exampleJa': '彼女は薄手のジャケットを着ました。'},
            {'word': 'clear', 'meaningJa': '晴れた・澄んだ', 'exampleEn': 'The sky is clear.', 'exampleJa': '空が晴れています。'},
        ],
    ),
    LessonSpec(
        lesson_id='intermediate-2026-06-23',
        level_group='intermediate',
        title='Commute and Notifications',
        cefr_level='B1',
        summary_ja='通勤中の習慣と、スマホ通知への対処を扱います。',
        source_urls=['https://www.apta.com/research-technical-resources'],
        sentences=[
            SentenceSpec('My commute takes about forty minutes on the train.', '電車での通勤はだいたい40分かかります。'),
            SentenceSpec('I read short articles while I wait on the platform.', 'ホームで待つ間に短い記事を読みます。'),
            SentenceSpec('Smartphone notifications can break my focus during the ride.', 'スマホの通知は移動中の集中を妨げることがあります。'),
            SentenceSpec('I silence non-urgent alerts before I board.', '乗車前に急ぎでない通知を消音にします。'),
        ],
        vocabulary=[
            {'word': 'commute', 'meaningJa': '通勤', 'exampleEn': 'My commute is long.', 'exampleJa': '通勤が長いです。'},
            {'word': 'platform', 'meaningJa': 'ホーム', 'exampleEn': 'Wait on the platform.', 'exampleJa': 'ホームで待ちます。'},
            {'word': 'notification', 'meaningJa': '通知', 'exampleEn': 'Turn off notifications.', 'exampleJa': '通知をオフにします。'},
            {'word': 'focus', 'meaningJa': '集中', 'exampleEn': 'I need focus at work.', 'exampleJa': '仕事で集中が必要です。'},
            {'word': 'urgent', 'meaningJa': '緊急の', 'exampleEn': 'This is not urgent.', 'exampleJa': 'これは緊急ではありません。'},
        ],
    ),
    LessonSpec(
        lesson_id='advanced-2026-06-23',
        level_group='advanced',
        title='Cafe Focus Routine',
        cefr_level='B2',
        summary_ja='カフェでの作業習慣と集中力の保ち方を扱います。',
        source_urls=['https://www.apa.org/topics/attention'],
        sentences=[
            SentenceSpec('Working from a quiet cafe helps me enter a deep focus state.', '静かなカフェで働くと深い集中状態に入りやすいです。'),
            SentenceSpec('Background noise is low, so meetings do not disturb others.', '周囲の雑音が少ないので、会議が周りの人の邪魔になりません。'),
            SentenceSpec('I limit social media to short breaks between sessions.', '作業の合間の短い休憩にだけSNSを使うようにしています。'),
            SentenceSpec('A consistent routine makes difficult tasks feel manageable.', '一定のルーティンがあると難しい作業もこなしやすくなります。'),
        ],
        vocabulary=[
            {'word': 'routine', 'meaningJa': '日課・ルーティン', 'exampleEn': 'I follow a morning routine.', 'exampleJa': '朝のルーティンを守っています。'},
            {'word': 'manageable', 'meaningJa': '対処できる', 'exampleEn': 'The task feels manageable.', 'exampleJa': 'その作業は対処できそうです。'},
            {'word': 'disturb', 'meaningJa': '邪魔する', 'exampleEn': 'Please do not disturb others.', 'exampleJa': '他の人の邪魔をしないでください。'},
            {'word': 'session', 'meaningJa': '作業の区切り', 'exampleEn': 'Take a break between sessions.', 'exampleJa': '作業の合間に休憩を取ります。'},
            {'word': 'consistent', 'meaningJa': '一貫した', 'exampleEn': 'Stay consistent every day.', 'exampleJa': '毎日一貫して続けます。'},
        ],
    ),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def audio_duration_ms(path: Path) -> int:
    output = subprocess.check_output(['afinfo', str(path)], text=True)
    for line in output.splitlines():
        if 'estimated duration' in line:
            seconds = float(line.split('sec')[0].split()[-1])
            return int(round(seconds * 1000))
    raise RuntimeError(f'Could not read duration for {path}')


def synthesize_m4a(text: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    aiff = output.with_suffix('.aiff')
    run(['say', '-v', VOICE, '-o', str(aiff), text])
    run(['afconvert', '-f', 'm4af', '-d', 'aac', str(aiff), str(output)])
    aiff.unlink(missing_ok=True)


def lesson_prefix(level_group: str) -> str:
    return level_group


def build_lesson_json(spec: LessonSpec) -> dict:
    prefix = lesson_prefix(spec.level_group)
    sentence_entries: list[dict] = []
    cursor_ms = 0
    sentence_durations: list[int] = []

    for index, sentence in enumerate(spec.sentences):
        sentence_id = f'{spec.lesson_id}-s{index + 1:02d}'
        sentence_file = f'{prefix}-s{index + 1:02d}.m4a'
        sentence_path = AUDIO_DIR / sentence_file
        synthesize_m4a(sentence.text, sentence_path)
        duration_ms = audio_duration_ms(sentence_path)
        sentence_durations.append(duration_ms)
        start_ms = cursor_ms
        end_ms = cursor_ms + duration_ms
        cursor_ms = end_ms + GAP_MS
        sentence_entries.append(
            {
                'id': sentence_id,
                'index': index,
                'text': sentence.text,
                'translationJa': sentence.translation_ja,
                'startMs': start_ms,
                'endMs': end_ms,
                'sentenceAudioUrl': f'{BASE_URL}/audio/{LESSON_DATE}/{sentence_file}',
            }
        )

    full_text = ' ... '.join(sentence.text for sentence in spec.sentences)
    full_path = AUDIO_DIR / f'{prefix}.m4a'
    synthesize_m4a(full_text, full_path)
    duration_seconds = max(1, int(round(audio_duration_ms(full_path) / 1000)))

    return {
        'id': spec.lesson_id,
        'levelGroup': spec.level_group,
        'title': spec.title,
        'cefrLevel': spec.cefr_level,
        'summaryJa': spec.summary_ja,
        'sourceUrls': spec.source_urls,
        'audioUrl': f'{BASE_URL}/audio/{LESSON_DATE}/{prefix}.m4a',
        'durationSeconds': duration_seconds,
        'sentences': sentence_entries,
        'vocabulary': spec.vocabulary,
    }


def build_manifest() -> dict:
    return {
        'version': 1,
        'generatedAtUtc': datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'lessonDate': LESSON_DATE,
        'lessons': [build_lesson_json(spec) for spec in LESSONS],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    manifest = build_manifest()
    write_json(ROOT / 'latest.json', manifest)
    write_json(ROOT / 'lessons' / f'{LESSON_DATE}.json', manifest)
    print(f'Wrote {ROOT / "latest.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
