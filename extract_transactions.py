#!/usr/bin/env python3
"""
Extract and consolidate bank transactions from bank PDF statements.
Supports multiple PDF files and exports to CSV format.
"""

import pdfplumber
import csv
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


class BankStatementExtractor:
    """Extracts transaction data from bank bank statement PDFs."""
    
    def __init__(self):
        self.transactions = []
        self.statement_info = {}
    
    def extract_currency(self, value: str) -> Optional[float]:
        """Convert currency string to float."""
        if not value or value.strip() == '':
            return None
        # Remove $ and commas, convert to float
        match = re.search(r'[\d,]+\.?\d*', value.replace(',', ''))
        if match:
            return float(match.group())
        return None
    
    def parse_date(self, date_str: str) -> Optional[str]:
        """Convert date string from 'DD MMM YY' format to YYYY-MM-DD."""
        if not date_str or not date_str.strip():
            return None
        try:
            # Parse format like "10 NOV 25"
            parsed = datetime.strptime(date_str.strip(), "%d %b %y")
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            return None
    
    _MONTHS = {'Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'}
    _CC_DEBIT_X1 = 490  # amounts right-aligned to x1<=490 are debits; >490 are credits

    def _is_credit_card(self, first_page_text: str) -> bool:
        return 'Credit limit' in first_page_text or 'Mastercard' in first_page_text

    def extract_header_info(self, pdf_path: str) -> None:
        """Extract metadata from first page."""
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            text = page.extract_text() or ''

            if self._is_credit_card(text):
                self._extract_cc_header(text)
            else:
                self._extract_bank_header(text)

    def _extract_bank_header(self, text: str) -> None:
        for line in text.split('\n'):
            if 'Account Number' in line:
                m = re.search(r'(\d+)', line)
                if m:
                    self.statement_info['account_number'] = m.group(1)
            elif 'BSB Number' in line:
                m = re.search(r'(\d+-\d+)', line)
                if m:
                    self.statement_info['bsb'] = m.group(1)
            elif 'Period' in line:
                self.statement_info['period'] = line.split('Period')[1].strip()
            elif 'Issue Date' in line:
                self.statement_info['issue_date'] = line.split('Issue Date')[1].strip()
            elif 'Account of:' in line:
                self.statement_info['account_holder'] = line.split('Account of:')[1].strip()

    def _extract_cc_header(self, text: str) -> None:
        for line in text.split('\n'):
            if 'Card number' in line:
                self.statement_info['account_number'] = line.split('Card number')[1].strip()
            elif line.startswith('From ') and ' to ' in line:
                self.statement_info['period'] = line.strip()
            elif 'MR ' in line or 'MS ' in line or 'MRS ' in line:
                self.statement_info['account_holder'] = line.strip()

    def extract_transactions_from_pdf(self, pdf_path: str) -> None:
        """Extract all transactions from a PDF file."""
        with pdfplumber.open(pdf_path) as pdf:
            first_text = pdf.pages[0].extract_text() or ''
            if self._is_credit_card(first_text):
                for page in pdf.pages:
                    self._extract_cc_page(page, Path(pdf_path).name)
            else:
                for page in pdf.pages:
                    self._extract_bank_page(page, Path(pdf_path).name)

    def _extract_bank_page(self, page, pdf_name: str) -> None:
        tables = page.extract_tables()
        if not tables:
            return

        table = tables[0]
        start_idx = 0
        for i, row in enumerate(table):
            if row[0] and 'Date' in str(row[0]):
                start_idx = i + 1
                break

        for row in table[start_idx:]:
            if not row[0] or not row[0].strip():
                continue
            date_str = row[0].strip()
            if 'OPENING BALANCE' in date_str or 'BROUGHT FORWARD' in date_str:
                continue
            date_match = re.match(r'(\d{2}\s\w+\s\d{2})', date_str)
            if not date_match:
                continue
            date = self.parse_date(date_match.group(1))
            particulars = row[1] if len(row) > 1 else ''
            debit = self.extract_currency(row[2]) if len(row) > 2 else None
            credit = self.extract_currency(row[3]) if len(row) > 3 else None
            balance = self.extract_currency(row[4]) if len(row) > 4 else None
            if date and (debit or credit):
                self.transactions.append({
                    'date': date,
                    'particulars': particulars.strip() if particulars else '',
                    'debit': debit,
                    'credit': credit,
                    'balance': balance,
                    'pdf_file': pdf_name,
                })

    def _extract_cc_page(self, page, pdf_name: str) -> None:
        text = page.extract_text() or ''
        if 'Transaction details' not in text and 'Date Description Debit Credit' not in text:
            return

        # Group words into lines by their vertical position
        lines: Dict[int, list] = {}
        for w in page.extract_words():
            key = round(w['top'])
            lines.setdefault(key, []).append(w)

        for words in sorted(lines.values(), key=lambda ws: ws[0]['top']):
            words = sorted(words, key=lambda w: w['x0'])
            texts = [w['text'] for w in words]

            # Transaction lines start with DD Mon YY
            if len(texts) < 4:
                continue
            if not (re.match(r'^\d{2}$', texts[0]) and texts[1] in self._MONTHS and re.match(r'^\d{2}$', texts[2])):
                continue

            date = self.parse_date(f"{texts[0]} {texts[1]} {texts[2]}")
            debit = None
            credit = None
            desc_parts = []

            for w in words[3:]:
                if w['text'].startswith('$'):
                    amount = self.extract_currency(w['text'])
                    if w['x1'] <= self._CC_DEBIT_X1:
                        debit = amount
                    else:
                        credit = amount
                else:
                    desc_parts.append(w['text'])

            if date and (debit is not None or credit is not None):
                self.transactions.append({
                    'date': date,
                    'particulars': ' '.join(desc_parts),
                    'debit': debit,
                    'credit': credit,
                    'balance': None,
                    'pdf_file': pdf_name,
                })
    
    def extract_from_files(self, pdf_paths: List[str]) -> None:
        """Extract from multiple PDF files."""
        for pdf_path in pdf_paths:
            print(f"Processing: {pdf_path}")
            self.extract_header_info(pdf_path)
            self.extract_transactions_from_pdf(pdf_path)
    
    def export_to_csv(self, output_path: str) -> None:
        """Export transactions to CSV file."""
        if not self.transactions:
            print("No transactions to export")
            return
        
        # Sort by date
        sorted_transactions = sorted(self.transactions, key=lambda x: x['date'])
        
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            fieldnames = ['date', 'particulars', 'debit', 'credit', 'balance', 'pdf_file']
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            
            # Write metadata as comments
            f.write(f"# Account Number: {self.statement_info.get('account_number', 'N/A')}\n")
            f.write(f"# BSB: {self.statement_info.get('bsb', 'N/A')}\n")
            f.write(f"# Account Holder: {self.statement_info.get('account_holder', 'N/A')}\n")
            f.write(f"# Period: {self.statement_info.get('period', 'N/A')}\n")
            f.write(f"# Issue Date: {self.statement_info.get('issue_date', 'N/A')}\n")
            f.write("#\n")
            
            writer.writeheader()
            writer.writerows(sorted_transactions)
        
        print(f"Exported {len(self.transactions)} transactions to {output_path}")
    
    def print_summary(self) -> None:
        """Print extraction summary."""
        print("\n" + "="*60)
        print("EXTRACTION SUMMARY")
        print("="*60)
        print(f"Total Transactions: {len(self.transactions)}")
        print(f"Account Number: {self.statement_info.get('account_number', 'N/A')}")
        print(f"Account Holder: {self.statement_info.get('account_holder', 'N/A')}")
        print(f"Period: {self.statement_info.get('period', 'N/A')}")
        
        if self.transactions:
            dates = [t['date'] for t in self.transactions]
            print(f"Date Range: {min(dates)} to {max(dates)}")
            
            total_debits = sum(t['debit'] or 0 for t in self.transactions)
            total_credits = sum(t['credit'] or 0 for t in self.transactions)
            print(f"Total Debits: ${total_debits:.2f}")
            print(f"Total Credits: ${total_credits:.2f}")
        
        print("="*60 + "\n")


def _statement_key(pdf: Path) -> str:
    """Sort key: the identifier after the last underscore (number or YYYY-MM-DD date)."""
    return pdf.stem.rsplit('_', 1)[-1]


def prompt_account_selection(account_dirs: List[Path]) -> List[Path]:
    """Present a numbered menu of accounts and return the chosen subset."""
    print("\nAccounts found:")
    print("  0. All")
    for i, d in enumerate(account_dirs, 1):
        count = len(list(d.glob("*.pdf")))
        print(f"  {i}. {d.name} ({count} statements)")

    raw = input("Select [0]: ").strip()
    if not raw or raw == "0":
        return account_dirs

    try:
        idx = int(raw)
        if 1 <= idx <= len(account_dirs):
            return [account_dirs[idx - 1]]
    except ValueError:
        pass

    print("Invalid selection — using all.")
    return account_dirs


def main():
    """Main extraction pipeline."""
    local_dir = Path("local")
    account_dirs = sorted(d for d in local_dir.iterdir() if d.is_dir())

    if not account_dirs:
        print("No account directories found in ./local")
        return

    selected_dirs = prompt_account_selection(account_dirs) if len(account_dirs) > 1 else account_dirs

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for account_dir in selected_dirs:
        account = account_dir.name
        pdfs = sorted(account_dir.glob("*.pdf"), key=_statement_key)

        if not pdfs:
            continue

        extractor = BankStatementExtractor()
        extractor.extract_from_files([str(p) for p in pdfs])
        extractor.print_summary()

        output_file = output_dir / f"Transactions_{account}.csv"
        extractor.export_to_csv(str(output_file))


if __name__ == "__main__":
    main()
