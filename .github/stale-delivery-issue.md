**配信が止まっています。手動でのリトライが要るか確認してください。**

| | |
|---|---|
| 本日（JST） | `__TODAY__` |
| 配信中の lessonDate | `__SERVED__` |
| 検知した run | __RUN_URL__ |

## まず原因を見る

```bash
gh run list -R Shoya9696/daily-shadowing-generator --limit 6
```

ステップが1つも実行されないまま15分でキャンセルされていれば、**GitHub の macOS ランナーが取得できていない**のであって、コードの問題ではありません。注釈に `The job was not acquired by Runner of type hosted` が出ます。この場合は時間を置いて手動リトライすると通ることがあります（2026-11-06 の実績）。

ステップが走ったうえで落ちている場合は、失敗したステップ名とログを見てください。`Generate lessons` なら Gemini 側、`Publish to content repo` ならトークンの期限切れを疑います。

## 手動リトライ

本日分がまだ無いことを確かめてから実行します。

```bash
gh api repos/Shoya9696/daily-shadowing-content/contents/lessons/__TODAY__.json -q .name
# 404 なら force=false のままでよい
gh workflow run generate_daily_lessons.yml -R Shoya9696/daily-shadowing-generator \
  --ref main -f use_sample=false -f force=false -f lesson_date=__TODAY__
```

`lesson_date` は必ず明示します。省略すると実行時点の JST 当日になるため、前日分を埋めたいときに別の日を処理してしまいます。

## 確認

公開 URL と音声の両方を見ます。マニフェストだけ出て音声が欠けることがあります。

```bash
curl -s __BASE__/latest.json | head -c 120
```

---
このissueは、鮮度チェックが回復した時点で自動的に閉じられます。
