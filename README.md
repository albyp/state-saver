# state-saver

Extract, categorise, and review bank and credit card transactions from PDF statements.

## Overview

```text
local/
  [AccountName]/        <- drop PDFs here, folder name = account name
    eStatement_...pdf

report/
  categories.json       <- master category list
  category_rules.json   <- keyword rules + manual review + broad merchant lists

output/
  Transactions_[AccountName].csv   <- raw extracted transactions (one per account)
  tagged.xlsx                      <- categorised workbook (one sheet per account)
```

`local/`, `output/`, and `report/` are gitignored.

---

## Setup

```bash
pip install pdfplumber openpyxl
```

---

## Usage

### 1. Add statements

Place PDF statements into a subfolder of `local/` named after the account:

```text
local/
  ATX/
    eStatement_XXXXXXXXXX123_87.pdf
    eStatement_XXXXXXXXXX123_86.pdf
  CCQ/
    eStatement_XXXX-XXXX-XXXX-XXXX_2026-05-14.pdf
```

Supported formats:

- **Bank statements** — table-based (Bankwest transaction accounts)
- **Credit card statements** — Bankwest Mastercard (text-based, debit/credit column detection)

### 2. Extract to CSV

```bash
python extract_transactions.py
```

If multiple account folders are found, you will be prompted to select one or process all:

```text
Accounts found:
  0. All
  1. ATX (40 statements)
  2. CCQ (12 statements)
Select [0]:
```

Press Enter or `0` for all. Output is written to `output/Transactions_[AccountName].csv`.

### 3. Tag and export to XLSX

```bash
python tag_transactions.py
```

Reads all CSVs from `output/`, applies categorisation rules, and writes `output/tagged.xlsx` with one sheet per account.

Each row gets a `category` and a `needs_review` flag. Rows requiring attention are highlighted yellow:

- Merchants flagged for manual review (remote sites, ambiguous vendors)
- Broad retailers where the category can't be inferred (Bunnings, Kmart, JB Hi-Fi etc.)
- Transactions that matched no rule

Internal transfers (same date, amount, and description appearing as a debit in one account and a credit in another) are auto-tagged as `Internal Transfer`.

---

## Improving categorisation

Rules live in `report/category_rules.json`. Re-run `tag_transactions.py` after any changes.

**`rules`** — ordered list of keyword-to-category mappings. First match wins.

```json
{ "category": "Groceries", "keywords": ["WOOLWORTHS", "COLES ", "ALDI "] }
```

**`manual_review`** — merchant substrings that always get flagged yellow regardless of other rules (e.g. remote site terminals where a single vendor covers food, bar, and supplies).

**`broad_merchants`** — merchants that get a tentative category but are still flagged yellow for confirmation (large retailers where the purchase type is ambiguous).

To audit coverage and see what is still unmatched:

```bash
python report/analyse_gaps.py
```

---

## File reference

| File | Purpose |
| --- | --- |
| `extract_transactions.py` | Extract transactions from PDFs to CSV |
| `tag_transactions.py` | Categorise CSVs and export to `tagged.xlsx` |
| `report/analyse_gaps.py` | Coverage report — matched vs. unmatched vs. manual review |
| `report/category_rules.json` | Keyword rules, manual review list, broad merchant list |
| `report/categories.json` | Master list of valid category names |
