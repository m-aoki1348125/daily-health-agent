CREATE TABLE IF NOT EXISTS daily_metrics (
  date DATE PRIMARY KEY,
  sleep_minutes INTEGER,
  sleep_efficiency DOUBLE PRECISION,
  deep_sleep_minutes INTEGER,
  rem_sleep_minutes INTEGER,
  awakenings INTEGER,
  resting_hr INTEGER,
  steps INTEGER,
  calories INTEGER,
  raw_drive_file_id VARCHAR(255),
  bedtime_start VARCHAR(32),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trend_features (
  date DATE PRIMARY KEY,
  sleep_vs_14d_avg DOUBLE PRECISION,
  resting_hr_vs_30d_avg DOUBLE PRECISION,
  sleep_debt_streak_days INTEGER NOT NULL DEFAULT 0,
  bedtime_drift_minutes DOUBLE PRECISION,
  recovery_score INTEGER NOT NULL DEFAULT 50,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS advice_history (
  date DATE PRIMARY KEY,
  risk_level VARCHAR(32) NOT NULL,
  summary TEXT NOT NULL,
  key_findings_json JSONB NOT NULL,
  today_actions_json JSONB NOT NULL,
  exercise_advice TEXT NOT NULL,
  sleep_advice TEXT NOT NULL,
  caffeine_advice TEXT NOT NULL,
  medical_note TEXT NOT NULL,
  long_term_comment TEXT NOT NULL,
  provider VARCHAR(64) NOT NULL,
  model_name VARCHAR(128) NOT NULL,
  daily_report_drive_file_id VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drive_index (
  date DATE PRIMARY KEY,
  raw_file_id VARCHAR(255),
  daily_json_file_id VARCHAR(255),
  daily_md_file_id VARCHAR(255),
  weekly_file_id VARCHAR(255),
  monthly_file_id VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
