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
from typing import List, Dict, Tuple, Optional


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
    
    def extract_header_info(self, pdf_path: str) -> None:
        """Extract metadata from first page."""
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]
            text = page.extract_text()
            
            # Extract key information
            lines = text.split('\n')
            for line in lines:
                if 'Account Number' in line:
                    match = re.search(r'(\d+)', line)
                    if match:
                        self.statement_info['account_number'] = match.group(1)
                elif 'BSB Number' in line:
                    match = re.search(r'(\d+-\d+)', line)
                    if match:
                        self.statement_info['bsb'] = match.group(1)
                elif 'Period' in line:
                    self.statement_info['period'] = line.split('Period')[1].strip()
                elif 'Issue Date' in line:
                    self.statement_info['issue_date'] = line.split('Issue Date')[1].strip()
                elif 'Account of:' in line:
                    self.statement_info['account_holder'] = line.split('Account of:')[1].strip()
    
    def extract_transactions_from_pdf(self, pdf_path: str) -> None:
        """Extract all transactions from a PDF file."""
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                if not tables:
                    continue
                
                table = tables[0]
                
                # Skip header rows (first few rows contain table headers)
                start_idx = 0
                for i, row in enumerate(table):
                    if row[0] and 'Date' in str(row[0]):
                        start_idx = i + 1
                        break
                
                # Extract transaction rows
                for row in table[start_idx:]:
                    if not row[0] or not row[0].strip():
                        continue
                    
                    date_str = row[0].strip()
                    
                    # Skip non-transaction rows
                    if 'OPENING BALANCE' in date_str or 'BROUGHT FORWARD' in date_str:
                        continue
                    
                    # Extract date from full date string (format: DD MMM YY ...)
                    date_match = re.match(r'(\d{2}\s\w+\s\d{2})', date_str)
                    if not date_match:
                        continue
                    
                    date = self.parse_date(date_match.group(1))
                    
                    particulars = row[1] if len(row) > 1 else ""
                    debit = self.extract_currency(row[2]) if len(row) > 2 else None
                    credit = self.extract_currency(row[3]) if len(row) > 3 else None
                    balance = self.extract_currency(row[4]) if len(row) > 4 else None
                    
                    # Only add if we have a date and some transaction info
                    if date and (debit or credit):
                        self.transactions.append({
                            'date': date,
                            'particulars': particulars.strip() if particulars else '',
                            'debit': debit,
                            'credit': credit,
                            'balance': balance,
                            'pdf_file': Path(pdf_path).name
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


def main():
    """Main extraction pipeline."""
    # Find all PDF files in local directory
    pdf_dir = Path("local")
    pdf_files = sorted(pdf_dir.glob("*.pdf"))
    
    if not pdf_files:
        print("No PDF files found in ./local directory")
        return
    
    # Extract from all PDFs
    extractor = BankStatementExtractor()
    extractor.extract_from_files([str(pdf) for pdf in pdf_files])
    
    # Print summary
    extractor.print_summary()
    
    # Export to CSV
    output_file = "transactions.csv"
    extractor.export_to_csv(output_file)


if __name__ == "__main__":
    main()
