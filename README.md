# Daily Shadowing Content

Public lesson delivery files for the **Daily Shadowing** app.

This repository hosts `latest.json`, dated lesson archives, and generated m4a audio over **GitHub Pages**.

## Important: sample content only (Step 9-C)

The current files are **manual sample lessons for delivery-path verification**.

They are **not** AI-generated daily news lessons. Topics are general everyday themes (weather, commute, focus) to avoid copying news articles.

Production daily generation will be added in later steps:

- **Step 9-D**: Private generator workflow
- **Step 9-E**: External cron trigger
- **Step 9-F**: End-to-end verification

## Public URLs

| Resource | URL |
|---|---|
| GitHub Pages root | https://shoya9696.github.io/daily-shadowing-content/ |
| Latest manifest | https://shoya9696.github.io/daily-shadowing-content/latest.json |
| Sample day archive | https://shoya9696.github.io/daily-shadowing-content/lessons/2026-06-23.json |

## Layout

```text
latest.json
lessons/YYYY-MM-DD.json
audio/YYYY-MM-DD/{level}.m4a
audio/YYYY-MM-DD/{level}-sNN.m4a
```

## What belongs here (Public OK)

- Generated lesson JSON
- English text and Japanese translations
- Vocabulary entries
- Source reference URLs
- Generated m4a audio (full lesson + per-sentence)

## What must NOT be committed

- API keys / secrets / `.env`
- Firebase configuration
- App source code
- Private prompts
- Internal documentation

## App integration

The Flutter app fetches `latest.json` over HTTPS when `RemoteLessonConfig.latestManifestUrl` is set. On failure it falls back to bundled assets.

Vocabulary audio uses on-device TTS (`flutter_tts`). Only full-lesson and sentence audio are served as m4a from this repo.

## License

Lesson text in this sample set is original sample content for app testing.
