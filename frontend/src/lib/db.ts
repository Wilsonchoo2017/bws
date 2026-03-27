import { DuckDBInstance } from '@duckdb/node-api';
import path from 'path';
import os from 'os';
import fs from 'fs';

const DB_DIR = path.join(os.homedir(), '.bws');
const DB_PATH = path.join(DB_DIR, 'bws.duckdb');

const SCHEMA_DDL = `
CREATE SEQUENCE IF NOT EXISTS bricklink_items_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_price_history_id_seq;
CREATE SEQUENCE IF NOT EXISTS bricklink_monthly_sales_id_seq;
CREATE SEQUENCE IF NOT EXISTS product_analysis_id_seq;
CREATE SEQUENCE IF NOT EXISTS worldbricks_sets_id_seq;
CREATE SEQUENCE IF NOT EXISTS brickranker_items_id_seq;

CREATE TABLE IF NOT EXISTS bricklink_items (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL UNIQUE,
    item_type VARCHAR NOT NULL,
    title VARCHAR,
    weight VARCHAR,
    year_released INTEGER,
    image_url VARCHAR,
    watch_status VARCHAR DEFAULT 'active',
    scrape_interval_days INTEGER DEFAULT 7,
    last_scraped_at TIMESTAMP,
    next_scrape_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_analysis (
    id INTEGER PRIMARY KEY,
    item_id VARCHAR NOT NULL UNIQUE,
    overall_score INTEGER,
    confidence INTEGER,
    action VARCHAR,
    urgency VARCHAR,
    dimensional_scores JSON,
    risks JSON,
    opportunities JSON,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
`;

let instance: DuckDBInstance | null = null;

async function getInstance(): Promise<DuckDBInstance> {
  if (!instance) {
    if (!fs.existsSync(DB_DIR)) {
      fs.mkdirSync(DB_DIR, { recursive: true });
    }
    instance = await DuckDBInstance.create(DB_PATH);

    // Ensure schema exists
    const conn = await instance.connect();
    try {
      await conn.run(SCHEMA_DDL);
    } finally {
      conn.closeSync();
    }
  }
  return instance;
}

export async function query<T = Record<string, unknown>>(
  sql: string
): Promise<T[]> {
  const db = await getInstance();
  const connection = await db.connect();
  try {
    const reader = await connection.runAndReadAll(sql);
    return reader.getRowObjectsJson() as T[];
  } finally {
    connection.closeSync();
  }
}
