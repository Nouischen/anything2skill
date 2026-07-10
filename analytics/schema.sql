CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  install_id TEXT NOT NULL,
  event TEXT NOT NULL,
  note_count INTEGER DEFAULT 0,
  platform TEXT,
  version TEXT,
  ts INTEGER,
  received_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_install ON events(install_id);
CREATE INDEX IF NOT EXISTS idx_event ON events(event);
CREATE INDEX IF NOT EXISTS idx_ts ON events(ts);
