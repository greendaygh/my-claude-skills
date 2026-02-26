#!/usr/bin/env python3
"""
extract_mutations.py - Extract mutation notations from scientific text

Parses text to identify amino acid substitution notations and extracts
associated kinetic parameters when present.

Usage:
    python extract_mutations.py --text "The D121N mutant showed 2.3-fold increase..."
    python extract_mutations.py --file abstract.txt --output mutations.json
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Mutation:
    """Represents a single amino acid mutation."""
    original: str
    position: int
    mutant: str
    notation: str  # Full notation e.g., "D121N"


@dataclass
class MutationData:
    """Mutation with associated kinetic data."""
    mutation: Mutation
    km: Optional[str] = None
    kcat: Optional[str] = None
    kcat_km: Optional[str] = None
    fold_change: Optional[str] = None
    tm: Optional[str] = None
    context: Optional[str] = None  # Surrounding text


# Standard amino acid codes
AA_CODES = {
    'A': 'Ala', 'C': 'Cys', 'D': 'Asp', 'E': 'Glu', 'F': 'Phe',
    'G': 'Gly', 'H': 'His', 'I': 'Ile', 'K': 'Lys', 'L': 'Leu',
    'M': 'Met', 'N': 'Asn', 'P': 'Pro', 'Q': 'Gln', 'R': 'Arg',
    'S': 'Ser', 'T': 'Thr', 'V': 'Val', 'W': 'Trp', 'Y': 'Tyr'
}

# Reverse mapping
AA_THREE_TO_ONE = {v: k for k, v in AA_CODES.items()}


def parse_mutation(notation: str) -> Optional[Mutation]:
    """
    Parse a mutation notation string.

    Supports formats:
    - Single letter: D121N, A234S
    - Three letter: Asp121Asn, Ala234Ser
    - With dashes: D-121-N

    Returns Mutation object or None if invalid.
    """
    # Pattern for single-letter notation: X###Y
    single_pattern = r'^([A-Z])(\d+)([A-Z])$'

    # Pattern for three-letter notation: Xxx###Yyy
    three_pattern = r'^([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})$'

    # Pattern with dashes: X-###-Y
    dash_pattern = r'^([A-Z])-?(\d+)-?([A-Z])$'

    notation = notation.strip()

    # Try single-letter format
    match = re.match(single_pattern, notation)
    if match:
        orig, pos, mut = match.groups()
        if orig in AA_CODES and mut in AA_CODES:
            return Mutation(
                original=orig,
                position=int(pos),
                mutant=mut,
                notation=notation
            )

    # Try three-letter format
    match = re.match(three_pattern, notation)
    if match:
        orig, pos, mut = match.groups()
        orig_cap = orig.capitalize()
        mut_cap = mut.capitalize()
        if orig_cap in AA_THREE_TO_ONE and mut_cap in AA_THREE_TO_ONE:
            return Mutation(
                original=AA_THREE_TO_ONE[orig_cap],
                position=int(pos),
                mutant=AA_THREE_TO_ONE[mut_cap],
                notation=f"{AA_THREE_TO_ONE[orig_cap]}{pos}{AA_THREE_TO_ONE[mut_cap]}"
            )

    # Try dash format
    match = re.match(dash_pattern, notation)
    if match:
        orig, pos, mut = match.groups()
        if orig in AA_CODES and mut in AA_CODES:
            return Mutation(
                original=orig,
                position=int(pos),
                mutant=mut,
                notation=f"{orig}{pos}{mut}"
            )

    return None


def extract_mutations_from_text(text: str) -> list[MutationData]:
    """
    Extract all mutations from text with surrounding context.

    Returns list of MutationData objects.
    """
    results = []

    # Pattern to find mutation notations in text
    # Matches: D121N, Asp121Asn, D-121-N, etc.
    patterns = [
        r'\b([A-Z])(\d{1,4})([A-Z])\b',  # Single letter: D121N
        r'\b([A-Z][a-z]{2})(\d{1,4})([A-Z][a-z]{2})\b',  # Three letter: Asp121Asn
    ]

    # Find all matches with context
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            notation = match.group(0)
            mutation = parse_mutation(notation)

            if mutation:
                # Extract context (50 chars before and after)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end].strip()

                # Try to extract kinetic values from context
                mut_data = MutationData(
                    mutation=mutation,
                    context=context
                )

                # Look for Km values
                km_match = re.search(r'[Kk]m\s*[=:≈]?\s*([\d.]+)\s*(mM|μM|µM|nM)', context)
                if km_match:
                    mut_data.km = f"{km_match.group(1)} {km_match.group(2)}"

                # Look for kcat values
                kcat_match = re.search(r'kcat\s*[=:≈]?\s*([\d.]+)\s*(s[⁻−-]1|/s|min[⁻−-]1)', context)
                if kcat_match:
                    mut_data.kcat = f"{kcat_match.group(1)} {kcat_match.group(2)}"

                # Look for fold change
                fold_match = re.search(r'([\d.]+)[×x-]\s*fold|fold\s*[=:]?\s*([\d.]+)', context, re.I)
                if fold_match:
                    value = fold_match.group(1) or fold_match.group(2)
                    mut_data.fold_change = f"{value}×"

                # Look for Tm values
                tm_match = re.search(r'[Tt]m\s*[=:≈]?\s*([\d.]+)\s*°?C', context)
                if tm_match:
                    mut_data.tm = f"{tm_match.group(1)} °C"

                results.append(mut_data)

    # Remove duplicates based on notation
    seen = set()
    unique_results = []
    for r in results:
        if r.mutation.notation not in seen:
            seen.add(r.mutation.notation)
            unique_results.append(r)

    return unique_results


def format_output(mutations: list[MutationData], format_type: str = "table") -> str:
    """Format mutation data for output."""

    if format_type == "json":
        return json.dumps([{
            "notation": m.mutation.notation,
            "original": m.mutation.original,
            "position": m.mutation.position,
            "mutant": m.mutation.mutant,
            "km": m.km,
            "kcat": m.kcat,
            "kcat_km": m.kcat_km,
            "fold_change": m.fold_change,
            "tm": m.tm
        } for m in mutations], indent=2)

    elif format_type == "table":
        lines = ["| Mutation | Position | Km | kcat | Fold Change | Tm |",
                 "|----------|----------|-----|------|-------------|-----|"]
        for m in mutations:
            lines.append(f"| {m.mutation.notation} | {m.mutation.position} | "
                        f"{m.km or '-'} | {m.kcat or '-'} | "
                        f"{m.fold_change or '-'} | {m.tm or '-'} |")
        return "\n".join(lines)

    else:  # simple list
        return "\n".join(m.mutation.notation for m in mutations)


def main():
    parser = argparse.ArgumentParser(
        description="Extract mutation notations from scientific text"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", "-t", help="Text to parse")
    group.add_argument("--file", "-f", help="File to parse")

    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--format", "-F", choices=["json", "table", "list"],
                       default="table", help="Output format")

    args = parser.parse_args()

    # Get input text
    if args.text:
        text = args.text
    else:
        with open(args.file, 'r') as f:
            text = f.read()

    # Extract mutations
    mutations = extract_mutations_from_text(text)

    if not mutations:
        print("No mutations found in text.", file=sys.stderr)
        sys.exit(0)

    # Format output
    output = format_output(mutations, args.format)

    # Write output
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Wrote {len(mutations)} mutations to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
