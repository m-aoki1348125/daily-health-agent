# 健康管理AI Agent 実装計画書（実装タスク一覧付き版）

## 1. 目的

Google Pixel Watch 4 / Fitbit の健康データを活用し、毎朝日本時間 8:45 に自動で解析を実行する健康管理 AI Agent を実装する。  
この Agent は以下を実現する。

- 前日分の健康データ取得
- 当日の健康状態分析
- 当日の過ごし方に関するアドバイス生成
- 長期的な健康傾向の分析
- Google Drive への整理保存
- LINE への通知

---

## 2. スコープ

### 2.1 MVP
- Fitbit Web API から前日データ取得
- Cloud SQL への保存
- ルールベース判定
- OpenAI / Claude による助言生成
- Google Drive への raw / report 保存
- LINE 通知
- Cloud Scheduler から毎朝 8:45 JST に実行

### 2.2 後続拡張
- 週報 / 月報
- 有効だったアドバイスの蓄積
- ベクトル検索
- 複数ユーザー対応
- Web UI / 設定管理画面
- 異常傾向の自動検出強化

---

## 3. アーキテクチャ概要

```text
Cloud Scheduler
   ↓
Cloud Run Jobs
   ↓
Fitbit Web API
   ↓
Feature Builder / Trend Analyzer / Rule Engine
   ↓
Cloud SQL + Google Drive
   ↓
LLM Provider (OpenAI / Claude)
   ↓
LINE Messaging API
```

---

## 4. ディレクトリ構成案

```text
health-agent/
  app/
    batch/
      run_daily_job.py
      run_weekly_job.py
      run_monthly_job.py

    clients/
      fitbit_client.py
      drive_client.py
      line_client.py
      llm_openai.py
      llm_claude.py

    services/
      feature_builder.py
      trend_analyzer.py
      rule_engine.py
      report_service.py
      notification_service.py

    repositories/
      metrics_repository.py
      advice_repository.py
      drive_index_repository.py

    schemas/
      health_features.py
      advice_result.py
      report_schema.py

    config/
      settings.py

  infra/
    docker/
    sql/
    terraform/

  tests/
```

---

## 5. 実装フェーズとタスク一覧

## フェーズ1: プロジェクト基盤構築

### 目的
Codex が後続実装を進めやすい最小骨格を作る。

### タスク
- [ ] Python プロジェクト初期化
- [ ] `pyproject.toml` 作成
- [ ] Ruff / Black / mypy 設定
- [ ] `.env.example` 作成
- [ ] ロギング設定追加
- [ ] `Dockerfile` 作成
- [ ] `Makefile` 追加
- [ ] アプリ共通設定 `settings.py` 作成
- [ ] Cloud Run Jobs エントリポイント追加
- [ ] 開発用 README 作成

### 完了条件
- ローカルで `python -m app.batch.run_daily_job` が起動できる
- Docker build が成功する

---

## フェーズ2: 設定・秘密情報管理

### 目的
環境変数・Secret Manager を前提とした設定読み込みを標準化する。

### タスク
- [ ] Pydantic Settings で設定クラス作成
- [ ] 実行環境ごとの設定整理（local / dev / prod）
- [ ] Secret Manager から読み込む秘密情報一覧を定義
- [ ] Fitbit refresh token / client secret の管理方針実装
- [ ] OpenAI / Claude API key の切替実装
- [ ] LINE Channel Access Token の読み込み実装
- [ ] DB 接続文字列の組み立て実装
- [ ] Google Drive ルートフォルダ ID 設定追加

### 完了条件
- ローカルと GCP で同じ設定クラスを使える
- 機密値がコードにハードコードされていない

---

## フェーズ3: DB スキーマと永続化

### 目的
日次保存と長期分析に必要な最低限のスキーマを整備する。

### テーブル
- `daily_metrics`
- `trend_features`
- `advice_history`
- `drive_index`

### タスク
- [ ] 初期 SQL 作成
- [ ] migration 方針決定（Alembic 推奨）
- [ ] SQLAlchemy または psycopg ベース repository 実装
- [ ] `daily_metrics` repository 実装
- [ ] `trend_features` repository 実装
- [ ] `advice_history` repository 実装
- [ ] `drive_index` repository 実装
- [ ] upsert 方針実装
- [ ] 同日再実行時の冪等動作実装

### 完了条件
- 前日データを DB に登録可能
- 同日再実行で重複登録されない

---

## フェーズ4: Fitbit API クライアント

### 目的
前日健康データを安定取得できるようにする。

### タスク
- [ ] OAuth 2.0 トークン更新処理実装
- [ ] 睡眠データ取得
- [ ] 心拍データ取得
- [ ] 活動量データ取得
- [ ] API レスポンスモデル定義
- [ ] エラーハンドリング実装
- [ ] レート制限ログ出力
- [ ] raw JSON 保存用オブジェクト生成

### 完了条件
- 指定日の Fitbit データ取得が成功する
- refresh token を使って継続動作する

---

## フェーズ5: Google Drive クライアント

### 目的
raw データとレポートを整理して保存できるようにする。

### タスク
- [ ] Drive API クライアント作成
- [ ] フォルダ存在確認 / 自動作成
- [ ] raw フォルダ保存実装
- [ ] daily_reports 保存実装
- [ ] weekly_reports 保存実装
- [ ] monthly_reports 保存実装
- [ ] JSON アップロード実装
- [ ] Markdown アップロード実装
- [ ] file ID を返す共通関数実装

### 完了条件
- 指定フォルダ構成でファイルが保存される
- 保存結果の file ID を DB に記録できる

---

## フェーズ6: LINE 通知クライアント

### 目的
毎朝の通知を本人に送信できるようにする。

### タスク
- [ ] LINE Messaging API クライアント作成
- [ ] push message 実装
- [ ] 通知フォーマット作成
- [ ] エラー時通知テンプレート作成
- [ ] 再試行ポリシー実装
- [ ] 送信結果ロギング

### 完了条件
- 日次サマリーが LINE に送信できる
- 失敗時にエラーが追跡できる

---

## フェーズ7: 特徴量生成

### 目的
LLM に渡す前の安定した特徴量表現を作る。

### タスク
- [ ] raw データ正規化
- [ ] 睡眠時間算出
- [ ] 睡眠効率算出
- [ ] 深睡眠 / REM 時間算出
- [ ] 中途覚醒回数算出
- [ ] 安静時心拍抽出
- [ ] 歩数 / 活動量抽出
- [ ] 日次特徴量オブジェクト定義

### 完了条件
- 1日分の raw データから正規化済み特徴量を生成できる

---

## フェーズ8: 長期トレンド分析

### 目的
日次だけでなく長期的な傾向を判定に組み込む。

### タスク
- [ ] 過去7日平均算出
- [ ] 過去14日平均との差算出
- [ ] 過去30日平均との差算出
- [ ] 睡眠不足連続日数算出
- [ ] 就寝時刻のドリフト算出
- [ ] 回復スコアの簡易算出
- [ ] 週次・月次の傾向要約生成

### 完了条件
- 日次特徴量から trend_features を作成できる
- 直近履歴を使った長期コメント材料が揃う

---

## フェーズ9: ルールベース判定

### 目的
LLM 依存を下げ、一次判定を安定化する。

### タスク
- [ ] green / yellow / red の判定ルール実装
- [ ] 睡眠不足判定
- [ ] 安静時心拍上昇判定
- [ ] 連続疲労判定
- [ ] データ欠損時の fallback 判定
- [ ] 判定理由の構造化出力実装

### 完了条件
- 特徴量入力から判定結果と理由を返せる

---

## フェーズ10: LLM 抽象化とプロバイダ実装

### 目的
OpenAI / Claude を切り替え可能にする。

### タスク
- [ ] `LLMProvider` 抽象インターフェース作成
- [ ] OpenAI provider 実装
- [ ] Claude provider 実装
- [ ] Structured JSON 出力実装
- [ ] タイムアウト / retry 実装
- [ ] 失敗時 fallback 実装
- [ ] モデル名 / provider 名の記録実装

### 完了条件
- 同一入力で provider を切り替えて応答を得られる

---

## フェーズ11: レポート生成

### 目的
Drive 保存と LINE 通知に使うレポートを生成する。

### タスク
- [ ] `daily_report.json` schema 作成
- [ ] `daily_report.md` テンプレート作成
- [ ] `weekly_report.json` schema 作成
- [ ] `weekly_report.md` テンプレート作成
- [ ] `monthly_report.json` schema 作成
- [ ] `monthly_report.md` テンプレート作成
- [ ] 生成時刻 / provider / file id 埋め込み

### 完了条件
- JSON と Markdown の両方が生成できる

---

## フェーズ12: 日次ジョブ統合

### 目的
毎朝動く本番ジョブを完成させる。

### タスク
- [ ] daily job オーケストレーション実装
- [ ] 実行日決定ロジック実装
- [ ] raw 保存 → DB 保存 → 分析 → レポート → 通知 の順序実装
- [ ] 冪等性確保
- [ ] 実行結果サマリー出力
- [ ] 異常時 fallback 動作確認

### 完了条件
- 1コマンドで日次ジョブが最後まで完走する

---

## フェーズ13: 週次・月次ジョブ

### 目的
長期分析のレポートを定期生成する。

### タスク
- [ ] 週次レポート生成ジョブ実装
- [ ] 月次レポート生成ジョブ実装
- [ ] Cloud Scheduler 用分岐設計
- [ ] Drive 保存
- [ ] 通知要約作成

### 完了条件
- 週報・月報を Drive に出力できる

---

## フェーズ14: テスト

### 目的
毎朝の定期運用に耐える品質を確保する。

### タスク
- [ ] 設定読み込みテスト
- [ ] Fitbit client モックテスト
- [ ] Drive client テスト
- [ ] LINE client テスト
- [ ] Rule Engine 単体テスト
- [ ] Trend Analyzer 単体テスト
- [ ] LLM provider schema テスト
- [ ] 日次ジョブ統合テスト
- [ ] 冪等性テスト
- [ ] fallback テスト

### 完了条件
- 主要フローに自動テストがある
- 回帰確認が可能

---

## フェーズ15: 運用・監視

### 目的
本番運用時の失敗検知と復旧を容易にする。

### タスク
- [ ] Cloud Logging への構造化ログ出力
- [ ] エラーレベル整理
- [ ] 実行時間計測
- [ ] 失敗通知設計
- [ ] 手動再実行手順書作成
- [ ] 運用 Runbook 作成

### 完了条件
- 失敗時の調査・再実行手順がある

---

## 6. 優先順位付きバックログ

### P0
- [ ] プロジェクト骨格
- [ ] Fitbit client
- [ ] DB schema
- [ ] Rule Engine
- [ ] OpenAI / Claude provider
- [ ] Drive 保存
- [ ] LINE 通知
- [ ] Daily Job 完成

### P1
- [ ] 週報
- [ ] 月報
- [ ] 長期傾向強化
- [ ] fallback 改善
- [ ] 運用ログ整備

### P2
- [ ] ベクトル検索
- [ ] 過去有効助言学習
- [ ] UI
- [ ] 複数ユーザー対応

---

## 7. Codex への依頼テンプレート

```text
このプロジェクトのフェーズ1から順に実装してください。

制約:
- Python で実装
- 型ヒントを付ける
- テストしやすい構造にする
- LLM provider は抽象化する
- 同日再実行で冪等性を担保する
- Google Cloud の Cloud Run Jobs で実行できるようにする

まずは以下を実装:
1. プロジェクト骨格
2. settings.py
3. daily job エントリポイント
4. Rule Engine
5. Fitbit client interface
6. Google Drive / LINE の stub client
7. PostgreSQL schema
```

---

## 8. 完成条件

- 毎朝 8:45 JST に自動実行される
- 前日データを取得して分析できる
- Drive に raw と日報が保存される
- LINE に日次サマリーが届く
- 長期トレンドを踏まえた助言が生成される
- 再実行しても重複保存されない
