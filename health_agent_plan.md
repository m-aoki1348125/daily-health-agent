# 健康管理AI Agent 実装計画書

## 1. 目的

Google Pixel Watch 4 / Fitbit で取得される健康データをもとに、毎朝日本時間 8:45 に自動解析を行い、以下を実現する。

- 前日分の健康データ取得
- 当日の健康状態分析
- 当日の過ごし方に関するアドバイス生成
- 長期的な健康傾向の分析
- 解析結果・アドバイスの Google Drive への整理保存
- LINE への通知

本システムは **Google Cloud の完全マネージド構成** を採用し、実装は **Codex を活用して進める**。

---

## 2. 採用方針

### 2.1 インフラ方針
Google Cloud の完全マネージド構成を採用する。

**採用サービス**
- Cloud Run Jobs
- Cloud Scheduler
- Secret Manager
- Cloud SQL for PostgreSQL
- Google Drive API
- LINE Messaging API
- Fitbit Web API
- OpenAI API または Claude API

### 2.2 LLM方針
LLM は **判定器** ではなく、**説明文・助言生成器** として使う。

- 一次判定: ルールベース
- 自然言語化: OpenAI / Claude API
- 実装支援・コード生成: Codex

### 2.3 データ保存方針
- **Google Drive**: 人が読むための正本保管先
- **Cloud SQL (PostgreSQL)**: 集計・履歴検索・長期分析用

---

## 3. システム全体構成

```text
Cloud Scheduler (毎朝 8:45 JST)
    ↓
Cloud Run Jobs
    ↓
1. Fitbit API から前日データ取得
2. raw JSON を Google Drive に保存
3. 特徴量を算出して Cloud SQL に保存
4. 過去履歴を集計して長期傾向を生成
5. Rule Engine で一次判定
6. LLM で日次助言 + 長期アドバイス生成
7. 日報JSON / Markdown を Google Drive に保存
8. LINE Messaging API で通知
```

---

## 4. 採用サービスと役割

### 4.1 Cloud Scheduler
役割:
- 毎朝 8:45 JST にバッチを定期実行する

設定例:
- cron: `45 8 * * *`
- timezone: `Asia/Tokyo`

### 4.2 Cloud Run Jobs
役割:
- バッチ処理本体の実行
- 前日データ取得、分析、保存、通知を一括実行

採用理由:
- 常時起動サーバ不要
- バッチ用途に適合
- コンテナベースで運用しやすい

### 4.3 Secret Manager
役割:
- Fitbit API トークン
- OpenAI / Claude API キー
- LINE Channel Access Token
- Google Drive 関連秘密情報
- DB 接続情報

### 4.4 Cloud SQL for PostgreSQL
役割:
- 日次メトリクス保存
- トレンド特徴量保存
- 助言履歴保存
- Drive ファイルID索引管理

### 4.5 Google Drive API
役割:
- raw データ保存
- 日報・週報・月報保存
- 人が読める履歴管理

### 4.6 LINE Messaging API
役割:
- 毎朝の健康サマリー通知
- 異常時や失敗時のエラー通知

### 4.7 Fitbit Web API
役割:
- 睡眠、心拍、歩数などの健康データ取得

### 4.8 OpenAI / Claude API
役割:
- ルール判定結果の説明
- 今日の行動提案
- 長期的な健康アドバイス生成

---

## 5. データフロー

### 5.1 毎朝の実行フロー
1. Cloud Scheduler が 8:45 JST に Cloud Run Jobs を起動
2. Fitbit API から前日分の健康データを取得
3. 取得した raw データを Google Drive に保存
4. 正規化・特徴量計算を実施
5. Cloud SQL に日次メトリクスを保存
6. 過去 7 / 30 / 90 日のデータを集計
7. Rule Engine で一次判定
8. LLM で日次 + 長期アドバイスを生成
9. レポートを JSON / Markdown 形式で Google Drive に保存
10. LINE にサマリーを送信

### 5.2 週次・月次フロー
- 毎週日曜 8:45 JST: 週報生成
- 毎月1日 8:45 JST: 前月月報生成

---

## 6. Google Drive 保存設計

### 6.1 フォルダ構成
```text
/HealthAgent/
  /profile/
    user_profile.json
    thresholds.json
    preferences.json

  /raw/
    /2026/
      /2026-04/
        2026-04-01_fitbit_raw.json

  /daily_reports/
    /2026/
      /2026-04/
        2026-04-01_daily_report.json
        2026-04-01_daily_report.md

  /weekly_reports/
    /2026/
      2026-W14_weekly_review.json
      2026-W14_weekly_review.md

  /monthly_reports/
    /2026/
      2026-04_monthly_review.json
      2026-04_monthly_review.md
```

### 6.2 保存ファイル
#### raw データ
- Fitbit API の取得レスポンスそのまま
- 再処理・監査用

#### 日報JSON
- 特徴量
- 判定結果
- LLM出力
- 使用モデル
- 生成時刻
- Drive file ID

#### 日報Markdown
- 人が読むための要約レポート

---

## 7. DB 設計方針

### 7.1 daily_metrics
保持例:
- date
- sleep_minutes
- sleep_efficiency
- deep_sleep_minutes
- rem_sleep_minutes
- awakenings
- resting_hr
- steps
- calories
- raw_drive_file_id

### 7.2 trend_features
保持例:
- date
- sleep_vs_14d_avg
- resting_hr_vs_30d_avg
- sleep_debt_streak_days
- bedtime_drift_minutes
- recovery_score

### 7.3 advice_history
保持例:
- date
- risk_level
- summary
- actions_json
- provider
- model_name
- daily_report_drive_file_id

### 7.4 drive_index
保持例:
- date
- raw_file_id
- daily_json_file_id
- daily_md_file_id
- weekly_file_id
- monthly_file_id

---

## 8. 健康分析ロジック

### 8.1 一次判定
まずはルールベースで状態判定する。

例:
- 睡眠時間が過去14日平均より大きく短い
- 安静時心拍が過去30日平均より有意に高い
- 睡眠不足が3日以上連続
- 就寝時刻が長期的に後ろ倒し
- 活動量に対して回復不足

判定結果:
- green
- yellow
- red

### 8.2 LLM の役割
LLM は以下を生成する。
- 今日の状態サマリー
- 今日の行動提案
- 運動アドバイス
- 睡眠アドバイス
- カフェインや休憩の提案
- 長期改善コメント

### 8.3 長期分析
日次分析だけでなく、以下を扱う。
- 7日トレンド
- 30日トレンド
- 90日トレンド
- 過去に効果があった助言
- 悪化パターンの反復検出

---

## 9. LLM 入出力設計

### 9.1 入力方針
LLM に渡すのは raw データではなく、要約済み特徴量とトレンド情報に限定する。

例:
```json
{
  "date": "2026-04-02",
  "sleep_minutes": 341,
  "sleep_vs_14d_avg": -72,
  "resting_hr_vs_30d_avg": 5,
  "steps_yesterday": 9320,
  "sleep_debt_streak_days": 3,
  "rule_status": "yellow",
  "weekly_trends": [
    "平日は睡眠時間が短い",
    "運動日の翌日は睡眠質が改善"
  ],
  "monthly_trends": [
    "就寝時刻が月初より遅れている"
  ]
}
```

### 9.2 出力方針
構造化 JSON を返させる。

例:
```json
{
  "risk_level": "yellow",
  "summary": "回復不足気味です",
  "key_findings": [
    "睡眠時間が直近平均より短い",
    "安静時心拍がやや高い"
  ],
  "today_actions": [
    "午前は高強度運動を避ける",
    "カフェインは14時まで"
  ],
  "exercise_advice": "軽めの運動に留める",
  "sleep_advice": "今夜は就寝を早める",
  "caffeine_advice": "午後は摂取を控える",
  "medical_note": "状態が継続悪化する場合は医療機関に相談"
}
```

---

## 10. LINE 通知設計

### 10.1 通知内容
- 日付
- コンディション
- 睡眠サマリー
- 安静時心拍の変化
- 今日の行動提案
- 長期コメント
- Drive 保存完了メッセージ

### 10.2 通知例
```text
今日の健康サマリー 2026-04-02

コンディション: Yellow
睡眠: 5時間52分（14日平均より -68分）
安静時心拍: +5 bpm
前日歩数: 8,420歩

今日のおすすめ
- 午前は高強度運動を避ける
- カフェインは14時まで
- 昼に15分の仮眠は可

長期コメント
- 今週は平日の睡眠不足が続き気味
- 就寝時刻が月初より遅れています

詳細レポートは Drive に保存済みです
```

---

## 11. エラー時の挙動

### 11.1 Fitbit 取得失敗
- LINE に失敗通知
- ログ記録
- 必要なら再試行

### 11.2 Drive 保存失敗
- DB に未保存フラグ
- エラー通知
- リカバリジョブ対象化

### 11.3 LLM 呼び出し失敗
- ルールベースの簡易メッセージで代替
- レポートには `llm_status=failed` を保存

### 11.4 LINE 通知失敗
- ログ保存
- リトライ
- レポート自体は保存継続

---

## 12. 実装ディレクトリ案

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

## 13. Codex に実装させる単位

Codex には以下の単位で順に実装させる。

### フェーズ1: 基盤
- Python プロジェクト初期化
- Dockerfile
- settings / config 管理
- Cloud Run Jobs 実行エントリポイント

### フェーズ2: API クライアント
- Fitbit API client
- Google Drive API client
- LINE Messaging API client
- OpenAI / Claude provider 実装

### フェーズ3: コアロジック
- raw データ正規化
- 特徴量生成
- ルールベース判定
- 長期トレンド分析
- JSON / Markdown レポート生成

### フェーズ4: 永続化
- PostgreSQL schema
- repository 実装
- Drive index 管理

### フェーズ5: 運用
- Cloud Scheduler 設定
- Secret Manager 連携
- logging / error handling
- retry 方針実装

### フェーズ6: テスト
- ユニットテスト
- API モックテスト
- 日次ジョブ統合テスト
- 回帰テスト

---

## 14. 実装優先順位

### MVP
最初に作るべきもの:
1. Fitbit API 取得
2. Cloud SQL 保存
3. Rule Engine
4. OpenAI / Claude による助言生成
5. Drive 保存
6. LINE 通知
7. Cloud Scheduler からの定期実行

### 拡張
後から追加するもの:
- 週報 / 月報
- 有効アドバイス学習
- ベクトル検索
- 異常傾向の自動検出
- ユーザー設定画面

---

## 15. セキュリティ・運用方針

- 秘密情報は Secret Manager に集約
- Cloud Run のサービスアカウント権限は最小化
- Drive への書き込み先フォルダは固定
- DB 接続は安全に管理
- ログに生の個人健康データを過剰出力しない
- 同日ジョブの重複実行に備えて冪等設計にする

---

## 16. 最終方針

本プロジェクトでは、以下を正式方針とする。

- インフラは **Google Cloud 完全マネージド構成**
- 実行は **Cloud Run Jobs + Cloud Scheduler**
- 保存は **Google Drive + Cloud SQL**
- 通知は **LINE Messaging API**
- 健康データ取得は **Fitbit Web API**
- 助言生成は **OpenAI API / Claude API**
- 実装は **Codex を活用して段階的に進める**
- 毎朝 **日本時間 8:45** に日次解析を実行する

---

## 17. Codex 向け実装開始プロンプト案

```text
Google Cloud の完全マネージド構成で、健康管理 AI Agent の Python 実装を開始してください。

要件:
- Cloud Run Jobs で日次バッチを実行
- Cloud Scheduler から毎朝 8:45 JST に起動
- Fitbit Web API から前日分の健康データを取得
- 正規化特徴量を PostgreSQL に保存
- Google Drive に raw JSON と日報(JSON/Markdown) を保存
- ルールベースで一次判定を行う
- OpenAI API または Claude API で日次助言と長期コメントを生成
- LINE Messaging API で通知する
- Python プロジェクト構成、Dockerfile、設定管理、主要クラス、DB スキーマ、ジョブエントリポイントを実装する
- 型ヒントとテストしやすい構造にする
- provider 切替可能な LLM 抽象化を入れる

まずは MVP として以下を実装してください:
1. プロジェクト骨格
2. settings 管理
3. Fitbit client のインターフェース
4. PostgreSQL schema
5. Rule Engine
6. LLMProvider 抽象化
7. 日次ジョブのエントリポイント
8. Google Drive / LINE client のスタブ
```

---
