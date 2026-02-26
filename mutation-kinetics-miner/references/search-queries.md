# PubMed Search Query Templates

Pre-built query templates for mutation-kinetics literature mining.

## Basic Mutation Search

```
"[PROTEIN_NAME]" AND (mutation OR mutant OR "site-directed mutagenesis")
```

## Kinetics-Focused Search

```
"[PROTEIN_NAME]" AND (mutation OR mutant OR "site-directed mutagenesis")
AND (kinetic* OR Km OR kcat OR "catalytic efficiency" OR Vmax)
```

## Stability-Focused Search

```
"[PROTEIN_NAME]" AND (mutation OR mutant)
AND (thermostab* OR "thermal stability" OR "melting temperature" OR Tm OR "half-life")
```

## Specificity-Focused Search

```
"[PROTEIN_NAME]" AND (mutation OR mutant)
AND ("substrate specificity" OR "substrate scope" OR selectivity OR promiscuity)
```

## Directed Evolution Search

```
"[PROTEIN_NAME]" AND ("directed evolution" OR "error-prone PCR" OR
"DNA shuffling" OR "saturation mutagenesis" OR "random mutagenesis")
```

## Rational Design Search

```
"[PROTEIN_NAME]" AND ("rational design" OR "structure-based" OR
"computational design" OR "site-directed mutagenesis" OR "structure-guided")
```

## Comprehensive Combined Query

```
"[PROTEIN_NAME]" AND
(mutation OR mutant OR variant* OR "site-directed mutagenesis" OR
"directed evolution" OR "rational design") AND
(kinetic* OR Km OR kcat OR "catalytic efficiency" OR thermostab* OR
"substrate specificity" OR "pH stability" OR "thermal stability")
```

## EC Number Based Search

```
"EC [X.X.X.X]" AND (mutation OR mutant) AND
(kinetic* OR Km OR kcat OR thermostab*)
```

## Family-Wide Search

```
("[PROTEIN_FAMILY]" OR "[ALTERNATIVE_NAME]") AND
(mutation OR mutant) AND (kinetic* OR catalytic)
```

## Query Modifiers

### Exclude Reviews
```
[QUERY] NOT review[pt]
```

### Recent Publications Only (5 years)
```
[QUERY] AND ("2021"[pdat] : "2026"[pdat])
```

### Free Full Text
```
[QUERY] AND free full text[filter]
```

### Specific Organism
```
[QUERY] AND "[organism]"[organism]
```

## Example Queries by Enzyme Type

### Lipases (EC 3.1.1.3)
```
(lipase OR "triacylglycerol lipase" OR "EC 3.1.1.3") AND
(mutation OR mutant) AND (enantioselectivity OR thermostab* OR
"organic solvent" OR Km OR kcat)
```

### Proteases (EC 3.4.x.x)
```
(protease OR peptidase OR "EC 3.4") AND
(mutation OR mutant) AND (specificity OR "cleavage site" OR
inhibitor OR Km OR kcat)
```

### Oxidoreductases (EC 1.x.x.x)
```
(oxidoreductase OR dehydrogenase OR oxidase OR reductase) AND
(mutation OR mutant) AND (cofactor OR NADH OR NADPH OR
"substrate specificity" OR kinetic*)
```

### Transaminases (EC 2.6.1.x)
```
(transaminase OR aminotransferase OR "EC 2.6.1") AND
(mutation OR mutant) AND (enantioselectivity OR
"amine donor" OR "amine acceptor" OR kinetic*)
```

## MeSH Term Enhancements

### Add MeSH for Comprehensive Coverage
```
[QUERY] OR
("[PROTEIN_NAME]"[MeSH Terms] AND "Mutation"[MeSH Terms])
```

### Enzyme Kinetics MeSH
```
[QUERY] AND "Kinetics"[MeSH Terms]
```

### Site-Directed Mutagenesis MeSH
```
[QUERY] AND "Mutagenesis, Site-Directed"[MeSH Terms]
```
