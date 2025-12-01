-- schema.sql
CREATE TABLE IF NOT EXISTS banks (
    bank_id SERIAL PRIMARY KEY,
    bank_name VARCHAR(120) UNIQUE,
    app_name VARCHAR(150)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id UUID PRIMARY KEY,
    bank_id INT REFERENCES banks(bank_id),
    review_text TEXT,
    clean_text TEXT,
    rating INT,
    review_date DATE,
    vader_compound FLOAT,
    vader_sentiment VARCHAR(20),
    distilbert_label VARCHAR(20),
    distilbert_score FLOAT,
    themes_str TEXT,
    source VARCHAR(50) DEFAULT 'Google Play',
    inserted_at TIMESTAMP DEFAULT NOW()
);
