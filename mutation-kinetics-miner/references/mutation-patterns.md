# Mutation Notation Patterns

Reference guide for recognizing and parsing mutation notations in scientific literature.

## Standard Single-Letter Notation

The most common format: `[WT residue][Position][Mutant residue]`

| Pattern | Example | Meaning |
|---------|---------|---------|
| X###Y | D121N | Asp at position 121 → Asn |
| X###Y | A234S | Ala at position 234 → Ser |
| X###Y | W167F | Trp at position 167 → Phe |

## Three-Letter Notation

Full amino acid names: `[WT name][Position][Mutant name]`

| Pattern | Example | Single-Letter |
|---------|---------|---------------|
| Xxx###Yyy | Asp121Asn | D121N |
| Xxx###Yyy | Ala234Ser | A234S |
| Xxx###Yyy | Trp167Phe | W167F |

## Multi-Mutation Formats

### Double Mutants
| Format | Example | Meaning |
|--------|---------|---------|
| X###Y/X###Y | D121N/A234S | Two simultaneous mutations |
| X###Y+X###Y | D121N+A234S | Two simultaneous mutations |
| X###Y,X###Y | D121N,A234S | Two simultaneous mutations |

### Triple+ Mutants
| Format | Example |
|--------|---------|
| X###Y/X###Y/X###Y | D121N/A234S/W167F |

## Special Notations

### Deletions
| Format | Example | Meaning |
|--------|---------|---------|
| ΔX### | ΔD121 | Deletion of Asp at 121 |
| X###del | D121del | Deletion of Asp at 121 |
| Δ###-### | Δ121-125 | Deletion of residues 121-125 |
| ΔLoop | ΔLoop | Deletion of named loop region |

### Insertions
| Format | Example | Meaning |
|--------|---------|---------|
| ###insX | 121insG | Glycine inserted after 121 |
| ###_###insXXX | 121_122insGAL | GAL inserted between 121-122 |

### Wild-Type Reference
| Format | Meaning |
|--------|---------|
| WT | Wild-type (no mutation) |
| wt | Wild-type (no mutation) |
| wild-type | Wild-type (no mutation) |

## Amino Acid Code Reference

| 1-Letter | 3-Letter | Full Name |
|----------|----------|-----------|
| A | Ala | Alanine |
| C | Cys | Cysteine |
| D | Asp | Aspartic acid |
| E | Glu | Glutamic acid |
| F | Phe | Phenylalanine |
| G | Gly | Glycine |
| H | His | Histidine |
| I | Ile | Isoleucine |
| K | Lys | Lysine |
| L | Leu | Leucine |
| M | Met | Methionine |
| N | Asn | Asparagine |
| P | Pro | Proline |
| Q | Gln | Glutamine |
| R | Arg | Arginine |
| S | Ser | Serine |
| T | Thr | Threonine |
| V | Val | Valine |
| W | Trp | Tryptophan |
| Y | Tyr | Tyrosine |

## Common False Positives

Be aware of patterns that look like mutations but are not:

| Pattern | Actual Meaning |
|---------|----------------|
| T4 lysozyme | Protein name (bacteriophage T4) |
| P450 | Cytochrome P450 enzyme family |
| S1 pocket | Substrate binding site name |
| E. coli | Organism name |
| pH 7.5 | pH value |
| 37°C | Temperature |
| IC50 | Inhibition constant |

## Position Numbering Considerations

**Warning:** Position numbers may differ between:
- UniProt canonical sequence (includes signal peptide)
- Mature protein (signal peptide cleaved)
- Crystal structure (may have truncations)
- Different isoforms

Always verify position using:
1. UniProt feature annotations
2. Alignment with reference sequence
3. Published methods section

## Regex Patterns for Extraction

### Single-Letter Mutation
```regex
\b([ACDEFGHIKLMNPQRSTVWY])(\d{1,4})([ACDEFGHIKLMNPQRSTVWY])\b
```

### Three-Letter Mutation
```regex
\b(Ala|Arg|Asn|Asp|Cys|Gln|Glu|Gly|His|Ile|Leu|Lys|Met|Phe|Pro|Ser|Thr|Trp|Tyr|Val)(\d{1,4})(Ala|Arg|Asn|Asp|Cys|Gln|Glu|Gly|His|Ile|Leu|Lys|Met|Phe|Pro|Ser|Thr|Trp|Tyr|Val)\b
```

### Multi-Mutation (slash-separated)
```regex
([A-Z]\d+[A-Z])(/[A-Z]\d+[A-Z])+
```

## Usage in extract_mutations.py

The `scripts/extract_mutations.py` script implements these patterns. Example:

```bash
# Single mutation
python extract_mutations.py --text "The D121N mutant showed..."

# From file
python extract_mutations.py --file abstract.txt --format json
```

See the script documentation for full options.
