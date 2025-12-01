
import psycopg2
import pandas as pd
from tqdm import tqdm
import os

CSV_PATH = r"C:/Users/User\Desktop/KAIM\Week_2/Fintech_Customer_Experience/data/processed/task2_reviews_sentiment_theme.csv"

# Change this to your Postgres password
PG_USER = "postgres"
PG_PASS = "selam"   # <<-- replace this
PG_DB   = "bank_reviews"
PG_HOST = "localhost"
PG_PORT = "5432"

# 1. Load cleaned CSV
if not os.path.exists(CSV_PATH):
    raise SystemExit(f"CSV not found: {CSV_PATH}")

df = pd.read_csv(CSV_PATH)

# Normalize bank names to match banks table entries
def map_bank(name):
    name = str(name)
    if "Abyssinia" in name or "BOA" in name:
        return "Bank of Abyssinia"
    if "Commercial Bank of Ethiopia" in name or "CBE" in name:
        return "Commercial Bank of Ethiopia"
    if "Dashen" in name:
        return "Dashen Bank"
    return name

df["bank_name_clean"] = df["bank_name"].apply(map_bank)

# 2. Connect to PostgreSQL
conn = psycopg2.connect(
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASS,
    host=PG_HOST,
    port=PG_PORT
)
cur = conn.cursor()

# 3. Insert banks first (id mapping)
bank_id_map = {}
unique_banks = df["bank_name_clean"].unique().tolist()

for bank in unique_banks:
    # Insert or get existing
    cur.execute("""
        INSERT INTO banks (bank_name, app_name)
        VALUES (%s, %s)
        ON CONFLICT (bank_name) DO UPDATE SET app_name = EXCLUDED.app_name
        RETURNING bank_id;
    """, (bank, bank))
    bank_id = cur.fetchone()[0]
    bank_id_map[bank] = bank_id

conn.commit()
print("Banks upserted:", bank_id_map)

# 4. Insert reviews (row by row, safe)
insert_query = """
INSERT INTO reviews (
    review_id, bank_id, review_text, clean_text, rating,
    review_date, vader_compound, vader_sentiment,
    distilbert_label, distilbert_score, themes_str, source
)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'Google Play')
ON CONFLICT (review_id) DO NOTHING;
"""

print("Inserting reviews...")
for _, row in tqdm(df.iterrows(), total=len(df)):
    # Clean and type-cast values
    review_id = row.get("review_id")
    bank_id = bank_id_map.get(row.get("bank_name_clean"))
    review_text = row.get("review_text")
    clean_text = row.get("clean_text") if "clean_text" in row else None
    rating = int(row["rating"]) if (not pd.isna(row.get("rating"))) else None
    review_date = row.get("review_date")
    vader_compound = float(row["vader_compound"]) if ("vader_compound" in row and pd.notna(row.get("vader_compound"))) else None
    vader_sentiment = row.get("vader_sentiment") if "vader_sentiment" in row else None
    distil_label = row.get("distilbert_label") if "distilbert_label" in row else None
    distil_score = float(row["distilbert_score"]) if ("distilbert_score" in row and pd.notna(row.get("distilbert_score"))) else None
    themes = row.get("themes_str") if "themes_str" in row else None

    try:
        cur.execute(insert_query, (
            review_id, bank_id, review_text, clean_text, rating,
            review_date, vader_compound, vader_sentiment,
            distil_label, distil_score, themes
        ))
    except Exception as e:
        # optional: print or log problem rows
        print("Error inserting row", review_id, e)

conn.commit()
cur.close()
conn.close()
print("Finished inserting reviews.")
