"""
Data Preprocessing Script
Task 1: Data Preprocessing

This script cleans and preprocesses the scraped reviews data.
- Handles missing values
- Normalizes dates
- Cleans text data
- Removes duplicates
- Removes non-English / Amharic texts (keep only English)
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime
import re
from config import DATA_PATHS

# Try to import langdetect for improved language detection; optional dependency.
try:
    from langdetect import detect
    LANGDETECT_AVAILABLE = True
except Exception:
    LANGDETECT_AVAILABLE = False


class ReviewPreprocessor:
    """Preprocessor class for review data"""

    def __init__(self, input_path=None, output_path=None):
        self.input_path = input_path or DATA_PATHS['raw_reviews']
        self.output_path = output_path or DATA_PATHS['processed_reviews']
        self.df = None
        self.stats = {}

    def load_data(self):
        print("Loading raw data...")
        try:
            self.df = pd.read_csv(self.input_path)
            print(f"Loaded {len(self.df)} reviews")
            self.stats['original_count'] = len(self.df)
            return True
        except FileNotFoundError:
            print(f"ERROR: File not found: {self.input_path}")
            return False
        except Exception as e:
            print(f"ERROR: Failed to load data: {str(e)}")
            return False

    def check_missing_data(self):
        print("\n[1/7] Checking for missing data...")
        missing = self.df.isnull().sum()
        missing_pct = (missing / len(self.df)) * 100

        print("\nMissing values:")
        for col in missing.index:
            if missing[col] > 0:
                print(f"  {col}: {missing[col]} ({missing_pct[col]:.2f}%)")

        self.stats['missing_before'] = missing.to_dict()

        critical_cols = ['review_text', 'rating', 'bank_name']
        missing_critical = self.df[critical_cols].isnull().sum()

        if missing_critical.sum() > 0:
            print("\nWARNING: Missing values in critical columns:")
            print(missing_critical[missing_critical > 0])

    def remove_duplicates(self):
        """
        Remove duplicate reviews.
        Keep the most recent review if duplicates are found (by review_text within same bank).
        """
        print("\n[2/7] Removing duplicates...")
        before = len(self.df)

        # Ensure review_date exists and is datetime for sorting — try convert if necessary
        if 'review_date' in self.df.columns:
            try:
                self.df['review_date'] = pd.to_datetime(self.df['review_date'], errors='coerce')
            except Exception:
                # If conversion fails, create a fallback ordering by index
                self.df['review_date'] = pd.NaT

        # Sort so that most recent rows appear first, then drop duplicates keeping first (most recent)
        sort_cols = []
        if 'bank_code' in self.df.columns:
            sort_cols.append('bank_code')
        if 'review_date' in self.df.columns:
            sort_cols.append('review_date')

        if sort_cols:
            # sort by bank_code ascending, review_date descending (most recent first)
            if 'review_date' in sort_cols:
                self.df = self.df.sort_values(sort_cols, ascending=[True, False])
            else:
                self.df = self.df.sort_values(sort_cols, ascending=[True])
        # Drop exact duplicate review_text within same bank_code if available, else globally
        if 'bank_code' in self.df.columns:
            self.df = self.df.drop_duplicates(subset=['bank_code', 'review_text'], keep='first')
        else:
            self.df = self.df.drop_duplicates(subset=['review_text'], keep='first')

        removed = before - len(self.df)
        print(f"Removed {removed} duplicate rows")
        self.stats['duplicates_removed'] = removed
        self.stats['count_after_duplicates'] = len(self.df)

    def handle_missing_values(self):
        print("\n[3/7] Handling missing values...")
        critical_cols = ['review_text', 'rating', 'bank_name']
        before_count = len(self.df)
        self.df = self.df.dropna(subset=critical_cols)
        removed = before_count - len(self.df)
        if removed > 0:
            print(f"Removed {removed} rows with missing critical values")

        self.df['user_name'] = self.df['user_name'].fillna('Anonymous')
        self.df['thumbs_up'] = self.df['thumbs_up'].fillna(0)
        self.df['reply_content'] = self.df['reply_content'].fillna('')

        self.stats['rows_removed_missing'] = removed
        self.stats['count_after_missing'] = len(self.df)

    def normalize_dates(self):
        print("\n[4/7] Normalizing dates...")
        try:
            self.df['review_date'] = pd.to_datetime(self.df['review_date'], errors='coerce')
            # keep date only
            self.df['review_date'] = self.df['review_date'].dt.date
            self.df['review_year'] = pd.to_datetime(self.df['review_date']).dt.year
            self.df['review_month'] = pd.to_datetime(self.df['review_date']).dt.month
            print(f"Date range: {self.df['review_date'].min()} to {self.df['review_date'].max()}")
        except Exception as e:
            print(f"WARNING: Error normalizing dates: {str(e)}")

    def clean_text(self):
        print("\n[5/7] Cleaning text...")

        def clean_review_text(text):
            if pd.isna(text) or text == '':
                return ''
            text = str(text)
            # normalize whitespace
            text = re.sub(r'\s+', ' ', text)
            text = text.strip()
            return text

        self.df['review_text'] = self.df['review_text'].apply(clean_review_text)
        before_count = len(self.df)
        self.df = self.df[self.df['review_text'].str.len() > 0]
        removed = before_count - len(self.df)
        if removed > 0:
            print(f"Removed {removed} reviews with empty text")
        self.df['text_length'] = self.df['review_text'].str.len()
        self.stats['empty_reviews_removed'] = removed
        self.stats['count_after_cleaning'] = len(self.df)

    def filter_non_english(self):
        """
        Remove reviews that are Amharic (Ethiopic script) or detected as non-English.
        Strategy:
        1. Remove reviews containing Ethiopic Unicode characters (U+1200 — U+137F).
        2. If langdetect is available, use it to require 'en' language.
        3. Otherwise, use a heuristic: proportion of ASCII letters/tokens.
        """
        print("\n[6/7] Filtering non-English / Amharic reviews (keeping English only)...")
        before = len(self.df)

        def contains_amharic(text):
            # Ethiopic Unicode block: \u1200 - \u137F
            return bool(re.search(r'[\u1200-\u137F]', str(text)))

        def is_english_by_heuristic(text):
            # Simple fallback heuristic: ratio of ASCII letters to total chars
            if not isinstance(text, str):
                return False
            total_chars = len(text)
            if total_chars == 0:
                return False
            ascii_letters = len(re.findall(r'[A-Za-z]', text))
            # count words with ASCII letters
            ascii_words = len(re.findall(r'\b[A-Za-z]{2,}\b', text))
            # require at least 40% ascii letters or at least 2 ascii words
            return (ascii_letters / total_chars) >= 0.40 or (ascii_words >= 2)

        keep_mask = []
        for txt in self.df['review_text'].astype(str):
            if contains_amharic(txt):
                keep_mask.append(False)
                continue

            if LANGDETECT_AVAILABLE:
                try:
                    lang = detect(txt)
                    keep_mask.append(lang == 'en')
                except Exception:
                    # detection failed for this text — fall back to heuristic
                    keep_mask.append(is_english_by_heuristic(txt))
            else:
                keep_mask.append(is_english_by_heuristic(txt))

        self.df = self.df[pd.Series(keep_mask, index=self.df.index)]
        removed = before - len(self.df)
        print(f"Removed {removed} non-English / Amharic or unrelated reviews")
        self.stats['non_english_removed'] = removed
        self.stats['count_after_language_filter'] = len(self.df)

    def validate_ratings(self):
        print("\n[7/7] Validating ratings...")
        invalid = self.df[(self.df['rating'] < 1) | (self.df['rating'] > 5)]
        if len(invalid) > 0:
            print(f"WARNING: Found {len(invalid)} reviews with invalid ratings")
            self.df = self.df[(self.df['rating'] >= 1) & (self.df['rating'] <= 5)]
        else:
            print("All ratings are valid (1-5)")
        self.stats['invalid_ratings_removed'] = len(invalid)

    def prepare_final_output(self):
        print("\nPreparing final output...")
        output_columns = [
            'review_id',
            'review_text',
            'rating',
            'review_date',
            'review_year',
            'review_month',
            'bank_code',
            'bank_name',
            'user_name',
            'thumbs_up',
            'text_length',
            'source'
        ]
        output_columns = [col for col in output_columns if col in self.df.columns]
        self.df = self.df[output_columns]
        # Sort: bank_code ascending, review_date descending
        if 'review_date' in self.df.columns and 'bank_code' in self.df.columns:
            self.df = self.df.sort_values(['bank_code', 'review_date'], ascending=[True, False])
        elif 'review_date' in self.df.columns:
            self.df = self.df.sort_values(['review_date'], ascending=[False])
        self.df = self.df.reset_index(drop=True)
        print(f"Final dataset: {len(self.df)} reviews")

    def save_data(self):
        print("\nSaving processed data...")
        try:
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            self.df.to_csv(self.output_path, index=False)
            print(f"Data saved to: {self.output_path}")
            self.stats['final_count'] = len(self.df)
            return True
        except Exception as e:
            print(f"ERROR: Failed to save data: {str(e)}")
            return False

    def generate_report(self):
        print("\n" + "=" * 60)
        print("PREPROCESSING REPORT")
        print("=" * 60)

        print(f"\nOriginal records: {self.stats.get('original_count', 0)}")
        print(f"Records with missing critical data: {self.stats.get('rows_removed_missing', 0)}")
        print(f"Duplicate rows removed: {self.stats.get('duplicates_removed', 0)}")
        print(f"Empty reviews removed: {self.stats.get('empty_reviews_removed', 0)}")
        print(f"Non-English/Amharic removed: {self.stats.get('non_english_removed', 0)}")
        print(f"Invalid ratings removed: {self.stats.get('invalid_ratings_removed', 0)}")
        print(f"Final records: {self.stats.get('final_count', 0)}")

        if self.stats.get('original_count', 0) > 0:
            retention_rate = (self.stats.get('final_count', 0) / self.stats.get('original_count', 1)) * 100
            error_rate = 100 - retention_rate
            print(f"\nData retention rate: {retention_rate:.2f}%")
            print(f"Data error rate: {error_rate:.2f}%")
            if error_rate < 5:
                print("✓ Data quality: EXCELLENT (<5% errors)")
            elif error_rate < 10:
                print("✓ Data quality: GOOD (<10% errors)")
            else:
                print("⚠ Data quality: NEEDS ATTENTION (>10% errors)")

        if self.df is not None:
            print("\nReviews per bank:")
            bank_counts = self.df['bank_name'].value_counts()
            for bank, count in bank_counts.items():
                print(f"  {bank}: {count}")

            print("\nRating distribution:")
            rating_counts = self.df['rating'].value_counts().sort_index(ascending=False)
            for rating, count in rating_counts.items():
                pct = (count / len(self.df)) * 100
                print(f"  {'⭐' * int(rating)}: {count} ({pct:.1f}%)")

            print(f"\nDate range: {self.df['review_date'].min()} to {self.df['review_date'].max()}")
            print(f"\nText statistics:")
            print(f"  Average length: {self.df['text_length'].mean():.0f} characters")
            print(f"  Median length: {self.df['text_length'].median():.0f} characters")
            print(f"  Min length: {self.df['text_length'].min()}")
            print(f"  Max length: {self.df['text_length'].max()}")

    def process(self):
        print("=" * 60)
        print("STARTING DATA PREPROCESSING")
        print("=" * 60)

        if not self.load_data():
            return False

        self.check_missing_data()
        # remove duplicates early (so other steps work on deduplicated data)
        self.remove_duplicates()
        self.handle_missing_values()
        self.normalize_dates()
        self.clean_text()
        # filter non-English / Amharic AFTER cleaning
        self.filter_non_english()
        self.validate_ratings()
        self.prepare_final_output()

        if self.save_data():
            self.generate_report()
            return True

        return False


def main():
    preprocessor = ReviewPreprocessor()
    success = preprocessor.process()
    if success:
        print("\n✓ Preprocessing completed successfully!")
        return preprocessor.df
    else:
        print("\n✗ Preprocessing failed!")
        return None


if __name__ == "__main__":
    processed_df = main()
