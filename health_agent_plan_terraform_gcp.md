# 健康管理AI Agent 実装計画書（Terraform / GCP設定込み版）

## 1. 目的

本ドキュメントは、健康管理AI Agent を **Google Cloud の完全マネージド構成** で実装・運用するための  
**GCP サービス設計、Terraform 管理方針、初期構築手順、権限設計** をまとめたものである。

---

## 2. 採用 GCP 構成

### 使用サービス
- Cloud Run Jobs
- Cloud Scheduler
- Secret Manager
- Cloud SQL for PostgreSQL
- Artifact Registry
- Cloud Logging
- IAM
- Service Accounts

### 外部サービス
- Fitbit Web API
- Google Drive API
- LINE Messaging API
- OpenAI API または Claude API

---

## 3. 全体構成

```text
Cloud Scheduler
   ↓
Cloud Run Job
   ↓
Cloud SQL (PostgreSQL)
Google Drive API
LINE Messaging API
Fitbit Web API
OpenAI / Claude API
Secret Manager
Artifact Registry
Cloud Logging
```

---

## 4. GCP プロジェクト設計

### 推奨プロジェクト構成
- `health-agent-dev`
- `health-agent-prod`

小規模で始めるなら 1 プロジェクトでもよいが、将来的には dev / prod 分離を推奨する。

### 推奨リージョン
- メイン: `asia-northeast1` または Google Cloud 側の東京リージョン系
- Scheduler timezone: `Asia/Tokyo`

---

## 5. リソース一覧

## 5.1 Artifact Registry
用途:
- Cloud Run Jobs 用 Docker image 保管

例:
- repository 名: `health-agent-images`

## 5.2 Cloud Run Jobs
用途:
- 日次バッチ
- 週次バッチ
- 月次バッチ

例:
- `health-agent-daily-job`
- `health-agent-weekly-job`
- `health-agent-monthly-job`

## 5.3 Cloud Scheduler
用途:
- 8:45 JST の日次実行
- 日曜 8:45 JST の週次実行
- 毎月1日 8:45 JST の月次実行

例:
- `health-agent-daily-scheduler`
- `health-agent-weekly-scheduler`
- `health-agent-monthly-scheduler`

## 5.4 Cloud SQL for PostgreSQL
用途:
- 健康履歴保存
- トレンド分析
- Drive file ID 索引

例:
- インスタンス名: `health-agent-postgres`
- DB 名: `health_agent`
- ユーザー名: `health_agent_app`

## 5.5 Secret Manager
用途:
- Fitbit client id / secret / refresh token
- OpenAI API key
- Claude API key
- LINE channel access token
- DB password
- Google Drive root folder id

## 5.6 Service Accounts
用途:
- Cloud Run Job 実行権限
- Scheduler から Job 実行権限
- Secret access
- Cloud SQL access

例:
- `health-agent-job-sa`
- `health-agent-scheduler-sa`

---

## 6. Terraform 管理方針

### ディレクトリ構成案

```text
infra/terraform/
  envs/
    dev/
      main.tf
      variables.tf
      terraform.tfvars
      outputs.tf
    prod/
      main.tf
      variables.tf
      terraform.tfvars
      outputs.tf

  modules/
    artifact_registry/
    cloud_run_job/
    cloud_scheduler/
    cloud_sql/
    secret_manager/
    service_account/
    iam/
```

### 方針
- 環境差分は `envs/dev`, `envs/prod` に分離
- リソース共通部分は `modules/` に切り出す
- Secret の値そのものは Terraform 管理外にしてもよい
- まずは GCP リソース作成までを Terraform 管理対象にする

---

## 7. Terraform で作るべき主要リソース

## 7.1 API 有効化
有効化対象:
- Cloud Run Admin API
- Cloud Scheduler API
- Secret Manager API
- Artifact Registry API
- Cloud SQL Admin API
- IAM API

### タスク
- [ ] `google_project_service` で各 API を有効化

---

## 7.2 Artifact Registry
### 作成対象
- Docker repository

### Terraform タスク
- [ ] Docker repository 作成
- [ ] リージョン指定
- [ ] 読み書き権限付与

---

## 7.3 Service Accounts
### 作成対象
- `health-agent-job-sa`
- `health-agent-scheduler-sa`

### Terraform タスク
- [ ] job service account 作成
- [ ] scheduler service account 作成
- [ ] 必要 IAM ロール付与

---

## 7.4 IAM
### 付与候補
`health-agent-job-sa`
- Secret Manager Secret Accessor
- Cloud SQL Client
- Logs Writer
- Artifact Registry Reader
- Cloud Run Job Runner 相当の必要権限
- 必要に応じて Drive 用 Google API アクセス設定

`health-agent-scheduler-sa`
- Cloud Run Job 実行トリガー権限

### Terraform タスク
- [ ] SA ごとのロール整理
- [ ] 最小権限でバインド作成

---

## 7.5 Secret Manager
### 管理対象シークレット名例
- `fitbit-client-id`
- `fitbit-client-secret`
- `fitbit-refresh-token`
- `openai-api-key`
- `claude-api-key`
- `line-channel-access-token`
- `db-password`
- `drive-root-folder-id`

### Terraform タスク
- [ ] シークレット container 作成
- [ ] 必要なら初期 version を手動投入
- [ ] Cloud Run Job SA に access 権限付与

---

## 7.6 Cloud SQL
### 構成例
- PostgreSQL 16 系
- 小さめインスタンスから開始
- 自動バックアップ有効化
- 削除保護は prod で有効化

### Terraform タスク
- [ ] Cloud SQL instance 作成
- [ ] database 作成
- [ ] user 作成
- [ ] backup 設定
- [ ] maintenance window 設定
- [ ] 接続用出力設定

---

## 7.7 Cloud Run Jobs
### ジョブ一覧
- `health-agent-daily-job`
- `health-agent-weekly-job`
- `health-agent-monthly-job`

### 推奨環境変数
- `APP_ENV`
- `DB_HOST`
- `DB_NAME`
- `DB_USER`
- `FITBIT_CLIENT_ID_SECRET_NAME`
- `FITBIT_CLIENT_SECRET_SECRET_NAME`
- `FITBIT_REFRESH_TOKEN_SECRET_NAME`
- `OPENAI_API_KEY_SECRET_NAME`
- `CLAUDE_API_KEY_SECRET_NAME`
- `LINE_CHANNEL_ACCESS_TOKEN_SECRET_NAME`
- `DRIVE_ROOT_FOLDER_ID_SECRET_NAME`
- `LLM_PROVIDER`
- `LOG_LEVEL`

### 推奨リソース
初期値の目安:
- CPU: 1
- Memory: 512Mi〜1Gi
- Timeout: 900s 程度

### Terraform タスク
- [ ] Cloud Run Job 作成
- [ ] container image 指定
- [ ] service account 紐付け
- [ ] env / secret ref 設定
- [ ] retry / timeout 設定
- [ ] 実行パラメータ設定

---

## 7.8 Cloud Scheduler
### 設定例
- 日次: `45 8 * * *`
- 週次: `45 8 * * 0`
- 月次: `45 8 1 * *`
- timezone: `Asia/Tokyo`

### Terraform タスク
- [ ] daily scheduler 作成
- [ ] weekly scheduler 作成
- [ ] monthly scheduler 作成
- [ ] Cloud Run Job との接続設定
- [ ] scheduler service account 指定

---

## 8. Cloud Run Job 設計

### 日次ジョブ
役割:
- Fitbit 前日データ取得
- raw JSON を Drive に保存
- DB 保存
- 日次分析
- LLM 生成
- Drive へ report 保存
- LINE 通知

### 週次ジョブ
役割:
- 過去7日集計
- 週報生成
- Drive 保存
- 必要なら LINE 通知

### 月次ジョブ
役割:
- 前月集計
- 月報生成
- Drive 保存
- 必要なら LINE 通知

---

## 9. Terraform 変数設計例

```hcl
variable "project_id" {}
variable "region" {
  default = "asia-northeast1"
}
variable "environment" {}
variable "db_tier" {
  default = "db-f1-micro"
}
variable "artifact_registry_repository" {
  default = "health-agent-images"
}
variable "cloud_run_image" {}
variable "timezone" {
  default = "Asia/Tokyo"
}
variable "daily_schedule" {
  default = "45 8 * * *"
}
variable "weekly_schedule" {
  default = "45 8 * * 0"
}
variable "monthly_schedule" {
  default = "45 8 1 * *"
}
```

---

## 10. Terraform outputs 例

- Cloud SQL instance connection name
- DB 名
- Artifact Registry repository URL
- Cloud Run Job 名
- Scheduler 名
- Service account email

---

## 11. 初期構築手順

### 手順1
GCP プロジェクト作成

### 手順2
Terraform 用認証設定

### 手順3
Terraform で基盤作成
- API 有効化
- Artifact Registry
- Service Accounts
- IAM
- Secret containers
- Cloud SQL
- Cloud Run Jobs
- Cloud Scheduler

### 手順4
Secret 値投入
- Fitbit 関連
- OpenAI / Claude
- LINE
- DB password
- Drive root folder id

### 手順5
アプリの Docker image build / push

### 手順6
Cloud Run Job に image 反映

### 手順7
手動実行テスト

### 手順8
Scheduler 有効化

---

## 12. 運用ルール

### 冪等性
- 同日ジョブを再実行しても二重保存しない
- DB は upsert
- Drive は同日ファイルを上書きまたは version 管理

### ログ
- 実行開始 / 終了
- Fitbit 取得件数
- Drive 保存 file ID
- LLM provider / model
- LINE 通知結果

### 失敗時
- 再実行可能にする
- LINE もしくは別経路で失敗通知
- Cloud Logging 上で確認可能にする

---

## 13. Terraform 実装タスク一覧

## フェーズ1: ベース
- [ ] Terraform ディレクトリ作成
- [ ] provider 設定
- [ ] backend 設定
- [ ] envs/dev 作成
- [ ] envs/prod 作成

## フェーズ2: API 有効化
- [ ] 必要 API 一括有効化

## フェーズ3: Artifact Registry
- [ ] repository 作成
- [ ] 権限付与

## フェーズ4: Service Accounts / IAM
- [ ] job SA 作成
- [ ] scheduler SA 作成
- [ ] ロール付与
- [ ] 最小権限確認

## フェーズ5: Secret Manager
- [ ] secret container 作成
- [ ] access policy 設定

## フェーズ6: Cloud SQL
- [ ] instance 作成
- [ ] DB 作成
- [ ] user 作成
- [ ] backup 設定
- [ ] output 作成

## フェーズ7: Cloud Run Jobs
- [ ] daily job
- [ ] weekly job
- [ ] monthly job
- [ ] env / secret ref
- [ ] resource / timeout 設定

## フェーズ8: Cloud Scheduler
- [ ] daily scheduler
- [ ] weekly scheduler
- [ ] monthly scheduler
- [ ] timezone 設定
- [ ] SA 接続

## フェーズ9: 手順書
- [ ] terraform apply 手順
- [ ] secret 投入手順
- [ ] image push 手順
- [ ] job 手動実行手順
- [ ] rollback 手順

---

## 14. Codex に渡す Terraform 実装指示例

```text
Terraform で Google Cloud の基盤を実装してください。

要件:
- Cloud Run Jobs を日次・週次・月次で作成
- Cloud Scheduler から日本時間 8:45 に起動
- Artifact Registry にコンテナを配置
- Cloud SQL for PostgreSQL を作成
- Secret Manager に必要な secret container を作成
- job 用 service account と scheduler 用 service account を作成
- IAM は最小権限で付与
- envs/dev と envs/prod の構成にする
- modules 化して再利用可能にする
- outputs に接続情報を出す

まずは以下から始めてください:
1. provider / backend / variables
2. API enable
3. Artifact Registry
4. Service Accounts
5. Secret Manager
6. Cloud SQL
7. Cloud Run Jobs
8. Cloud Scheduler
```

---

## 15. アプリ側 GCP 接続で必要な考慮事項

- Cloud Run Job から Cloud SQL 接続方法を統一する
- Secret Manager をアプリ起動時に読む設計にする
- Drive API 利用の認証方式を明確化する
- Cloud Run Job SA と Drive 操作主体の整理をする
- DB migration の実行タイミングを決める

---

## 16. 最終方針

- インフラは Terraform 管理
- 実行基盤は Cloud Run Jobs
- 定期起動は Cloud Scheduler
- 秘密情報は Secret Manager
- 履歴保存は Cloud SQL
- raw / report の正本保管は Google Drive
- 日次実行は毎朝 8:45 JST
- Codex に Terraform とアプリ実装を段階的に作らせる
