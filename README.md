# Daily Shadowing Content

Public lesson delivery files for the **Daily Shadowing** app.

This repository hosts `latest.json`, dated lesson archives, and generated m4a audio over **GitHub Pages**.

## Delivery-only repository

This repo holds **published static files only**. Lesson generation and publish run in the private generator repo:

- [Shoya9696/daily-shadowing-generator](https://github.com/Shoya9696/daily-shadowing-generator)

Do not add generation scripts or prompts here. Use the generator workflow to update this repo.

Post-deploy public URL checks run in this Public repo via `.github/workflows/validate_pages_deployment.yml` after a successful `github-pages` deployment (`deployment_status`). That workflow is read-only HTTP validation and does not write content.

## Current content (Step 9-F2)

| Item | Status |
|---|---|
| Publish path | Generator workflow → `CONTENT_REPO_PUSH_TOKEN` → this repo |
| Latest publish | `57ef57b` — `lessonDate=2026-06-23` (sample mode) |
| Production AI | **Not enabled** (`use_sample=false` / Gemini not configured) |
| External cron | **Not enabled** |

Topics in the current sample set are general everyday themes (not live news). Production daily news generation is a future step.

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
- Generation scripts or prompts
- Internal documentation

## App integration

The Flutter app fetches `latest.json` over HTTPS from `RemoteLessonConfig.latestManifestUrl`. On failure it falls back to bundled assets.

Vocabulary audio uses on-device TTS (`flutter_tts`). Only full-lesson and sentence audio are served as m4a from this repo.

## License

Lesson text in this sample set is original sample content for app testing.
