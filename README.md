# daily-health-agent

Fitbit / Google Drive / LINE / LLM を組み合わせて、前日分の健康データを毎朝 8:45 JST に解析し、日次レポートと行動アドバイスを生成する Cloud Run Jobs ベースのバッチサービスです。daily はローカルで mock により end-to-end 実行でき、weekly / monthly は将来拡張用のジョブ雛形を含みます。

## 概要

- Fitbit Web API から前日データを取得
- raw JSON を Google Drive 保管庫へ保存
- 特徴量と長期トレンドを生成
- ルールベース判定を実施
- OpenAI / Claude / mock を切り替えて説明と提案を生成
- LINE で受けた食事写真を画像入力対応 LLM で解析し、推定摂取カロリーを保存
- 日次レポート JSON / Markdown を Drive に保存
- LINE Messaging API で本人に通知
- Cloud SQL for PostgreSQL に履歴を upsert 保存
- Cloud Scheduler から Cloud Run Jobs を 8:45 JST に起動
- Cloud Run Service で LINE webhook を受け、食事画像を即時記録

## 前提

- Python 3.11 以上を前提に実装しています。
- このワークスペースの実行環境は確認時点で `Python 3.9.6` だったため、ローカルの完全検証には 3.11 以上の導入が必要です。
- ローカルでは `FITBIT_CLIENT_MODE=mock`、`GOOGLE_DRIVE_MODE=local`、`LINE_CLIENT_MODE=mock`、`LLM_PROVIDER=mock` を既定にしています。
- Fitbit は refresh token から access token を毎実行時に取得して API を呼び出します。
- Fitbit の refresh token はローテーションされるため、Cloud Run 実行時に取得した新しい token を Secret Manager に保存する前提です。
- 初回 daily 実行時は、`HISTORICAL_BOOTSTRAP_DAYS` で指定した日数ぶんだけ不足している過去 Fitbit データを自動補完し、2週間待たずにトレンド比較へ使います。Fitbit のレート制限回避のため、1 回の実行で取得するのは直近から `HISTORICAL_BOOTSTRAP_MAX_DAYS_PER_RUN` 日までに制限しています。既定は 14 日です。
- Google Drive は user OAuth refresh token を使って本人の Drive に保存します。Shared Drive がない個人 Google アカウントでも運用できます。
- Cloud SQL は Terraform 上で PostgreSQL を作成し、ローカルでは SQLite で手早く検証します。

## アーキテクチャ

```text
Cloud Scheduler (45 8 * * *, Asia/Tokyo)
  -> Cloud Run Job (daily)
     -> Fitbit client
     -> Google Drive client
     -> Feature builder
     -> Trend analyzer
     -> Rule engine
     -> LLM provider
     -> Report service
     -> Cloud SQL repositories
     -> LINE notification

LINE Messaging API webhook
  -> Cloud Run Service (line-webhook)
     -> LINE media content fetch
     -> Vision-capable LLM calorie estimation
     -> Google Drive meal image / JSON save
     -> Cloud SQL meal_records upsert
     -> LINE reply
```

LLM は判定器ではなく、ルールベース結果と要約済みトレンドを説明し、当日の行動提案と長期コメントを生成する役割です。失敗時は rule-based fallback でレポートと通知を生成します。

## ディレクトリ構成

```text
app/
  batch/
  clients/
  config/
  db/
  repositories/
  schemas/
  services/
infra/
  docker/
  sql/
  terraform/
alembic/
tests/
```

## ローカルセットアップ

1. Python 3.11 以上を用意します。
2. 仮想環境を作成します。
3. 依存関係をインストールします。
4. `.env.example` を `.env` にコピーして必要に応じて調整します。

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
```

## 必要な環境変数

主な環境変数は `.env.example` に記載しています。

- `DATABASE_URL`
- `FITBIT_CLIENT_MODE`
- `FITBIT_CLIENT_ID`
- `FITBIT_CLIENT_SECRET`
- `FITBIT_REFRESH_TOKEN`
- `HISTORICAL_BOOTSTRAP_ENABLED`
- `HISTORICAL_BOOTSTRAP_DAYS`
- `HISTORICAL_BOOTSTRAP_MAX_DAYS_PER_RUN`
- `GOOGLE_DRIVE_MODE`
- `DRIVE_ROOT_FOLDER_ID`
- `DRIVE_LOCAL_ROOT`
- `DRIVE_OAUTH_CLIENT_ID`
- `DRIVE_OAUTH_CLIENT_SECRET`
- `DRIVE_OAUTH_REFRESH_TOKEN`
- `DRIVE_OAUTH_TOKEN_URI`
- `LINE_CLIENT_MODE`
- `LINE_CHANNEL_ACCESS_TOKEN`
- `LINE_CHANNEL_SECRET`
- `LINE_USER_ID`
- `LINE_WEBHOOK_PATH`
- `LLM_PROVIDER`
- `LLM_MODEL_NAME`
- `OPENAI_API_KEY`
- `CLAUDE_API_KEY`
- `TIMEZONE`
- `HEALTH_AGENT_DATE`

Secret Manager の想定 secret 名:

- `fitbit-client-id`
- `fitbit-client-secret`
- `fitbit-refresh-token`
- `openai-api-key`
- `claude-api-key`
- `line-channel-access-token`
- `line-channel-secret`
- `db-password`
- `drive-root-folder-id`
- `drive-oauth-client-id`
- `drive-oauth-client-secret`
- `drive-oauth-refresh-token`

`drive-root-folder-id` は Google Drive 上の保存先フォルダ ID です。user OAuth 方式では My Drive 配下のフォルダ ID を指定できます。

## daily job の実行方法

mock 構成でのローカル実行:

```bash
make run-daily
```

明示日付で実行:

```bash
HEALTH_AGENT_DATE=2026-04-02 make run-daily
```

実行すると以下が行われます。

- 必要に応じて不足している過去 Fitbit データを最大 `HISTORICAL_BOOTSTRAP_DAYS` 日の範囲から、直近優先で `HISTORICAL_BOOTSTRAP_MAX_DAYS_PER_RUN` 日ぶん backfill
- 前日 raw を `DRIVE_LOCAL_ROOT/HealthAgent/raw/...` に保存
- `daily_report.json` と `daily_report.md` を `daily_reports/...` に保存
- 当日に LINE 経由で記録された `meal_records/...` を health data に合流
- DB に `daily_metrics`, `trend_features`, `advice_history`, `drive_index` を upsert
- LINE 送信用本文を生成

## LINE 食事画像 webhook のローカル起動

```bash
source .venv/bin/activate
python -m uvicorn app.web.line_webhook:app --host 0.0.0.0 --port 8080
```

画像メッセージを受けると以下を行います。

- LINE から画像本体を取得
- Claude / OpenAI の画像入力で推定摂取カロリーを算出
- `meal_images/...` に画像保存
- `meal_records/...` に推定結果 JSON と日次食事サマリ JSON を保存
- `meal_records` テーブルへ upsert
- 翌朝の daily job が食事カロリーを health data として参照

## テスト方法

```bash
make test
```

静的チェック:

```bash
make lint
make typecheck
```

## DB マイグレーション

Alembic を同梱しています。

```bash
alembic upgrade head
```

初期 SQL は [infra/sql/001_init.sql](/Users/m-aoki/work/service/my-health/infra/sql/001_init.sql) にあります。

## Docker

Docker build:

```bash
docker build -f infra/docker/Dockerfile -t daily-health-agent:local .
```

Cloud Run Jobs は daily を既定 entrypoint にしています。weekly / monthly は Terraform から `args` で切り替えます。

## Terraform apply 手順

dev 環境例:

```bash
cd infra/terraform/envs/dev
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform plan
terraform apply
```

## Terraform で作成するもの

- Artifact Registry
- Cloud Run Jobs: daily / weekly / monthly
- Cloud Run Service: line-webhook
- Cloud Scheduler: daily / weekly / monthly
- Secret Manager
- Cloud SQL for PostgreSQL
- Service Accounts
- IAM bindings
- 必要 API 有効化

主な Terraform 変数:

- `project_id`
- `region`
- `environment`
- `db_tier`
- `artifact_registry_repository`
- `cloud_run_image`
- `timezone`
- `daily_schedule`
- `weekly_schedule`
- `monthly_schedule`

## Secret の登録方法

```bash
printf '%s' 'your-fitbit-client-id' | gcloud secrets versions add fitbit-client-id --data-file=-
printf '%s' 'your-fitbit-client-secret' | gcloud secrets versions add fitbit-client-secret --data-file=-
printf '%s' 'your-fitbit-refresh-token' | gcloud secrets versions add fitbit-refresh-token --data-file=-
printf '%s' 'your-openai-key' | gcloud secrets versions add openai-api-key --data-file=-
printf '%s' 'your-claude-key' | gcloud secrets versions add claude-api-key --data-file=-
printf '%s' 'your-line-token' | gcloud secrets versions add line-channel-access-token --data-file=-
printf '%s' 'your-line-channel-secret' | gcloud secrets versions add line-channel-secret --data-file=-
printf '%s' 'your-db-password' | gcloud secrets versions add db-password --data-file=-
printf '%s' 'your-drive-root-folder-id' | gcloud secrets versions add drive-root-folder-id --data-file=-
printf '%s' 'your-drive-oauth-client-id' | gcloud secrets versions add drive-oauth-client-id --data-file=-
printf '%s' 'your-drive-oauth-client-secret' | gcloud secrets versions add drive-oauth-client-secret --data-file=-
printf '%s' 'your-drive-oauth-refresh-token' | gcloud secrets versions add drive-oauth-refresh-token --data-file=-
```

Cloud Run Job 側では secret 以外に以下の plain env も設定します。

- `LINE_USER_ID`
- `LLM_PROVIDER`
- `LLM_MODEL_NAME`
- `LINE_WEBHOOK_PATH`

Google Drive OAuth の前提:

1. Google Cloud Console で OAuth Client を作成
2. Drive API を有効化
3. `https://www.googleapis.com/auth/drive.file` スコープで refresh token を取得
4. My Drive 上の保存先フォルダ ID を `drive-root-folder-id` に設定

## Cloud Run Jobs へのデプロイ方法

```bash
gcloud builds submit --tag asia-northeast1-docker.pkg.dev/$PROJECT_ID/daily-health-agent/daily-health-agent:latest
terraform -chdir=infra/terraform/envs/dev apply
```

apply 後は `line_webhook_url` output を LINE Developers Console の webhook URL に設定してください。
通常は `https://.../line/webhook` の形になります。

Terraform は以下のスケジュールを作成します。

- daily: `45 8 * * *`
- weekly: `45 8 * * 0`
- monthly: `45 8 1 * *`
- timezone: `Asia/Tokyo`

加えて、食事画像受信用の公開 Cloud Run Service を作成します。

## 運用時の再実行方法

同日再実行でも DB は primary key ベースで upsert され、Drive は同名ファイルを上書きし、重複登録を避けます。
過去データ backfill も、既に存在する日付は再取得せず不足分だけを補完します。

ローカル:

```bash
HEALTH_AGENT_DATE=2026-04-02 make run-daily
```

Cloud Run Job 手動再実行:

```bash
gcloud run jobs execute daily-health-dev-daily --region asia-northeast1
```

## LINE 通知内容

通知には以下を含めます。

- 日付
- コンディション
- 睡眠サマリー
- 安静時心拍差分
- 今日のおすすめ
- 長期コメント
- Drive 保存済みである旨

## 今後の拡張案

- weekly / monthly の本実装
- Fitbit refresh token の自動更新
- 複数ユーザー対応
- Drive 上の profile / thresholds / preferences 管理
- 医療相談閾値の個人最適化
- BigQuery 連携や可視化ダッシュボード
