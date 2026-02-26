---
name: skill-learn
description: This skill should be used when the user asks to "create a new skill", "learn a skill", "generate a skill", "build a skill about X", "teach me how to make a skill", or wants automated skill generation through multi-agent collaboration. This meta-skill orchestrates multiple specialized agents to design and create high-quality skills from just a topic description.
user_invocable: true
---

# Skill-Learn: Multi-Agent Skill Generator

This meta-skill enables automated generation of high-quality skills through collaborative multi-agent design. Given a topic from the user, orchestrate specialized agents to analyze, design, and create a complete skill package.

## Prerequisites

Before using this skill, understand these concepts:

- **Claude Code Skills System**: Skills are markdown files in `~/.claude/skills/` that extend Claude's capabilities
- **Task Tool**: A built-in Claude Code tool that delegates work to sub-agents. Parameters: `subagent_type` (agent role), `description` (brief label), `prompt` (full instructions)
- **AskUserQuestion Tool**: A built-in tool for collecting user input with multiple-choice options
- **YAML Frontmatter**: Metadata at the top of SKILL.md files (name, description, user_invocable)
- **Progressive Disclosure**: Organizing content so only relevant information is loaded when needed

## Quick Start Example

Generate a simple skill in minimal steps:

```
User: /skill-learn git commit message generator

1. [Phase 1] Domain: Technical, Complexity: Simple → 3 agents
2. [Phase 2] Agents: domain-expert, structure-designer, validator
3. [Phase 3] 2-round discussion (parallel execution within rounds)
4. [Phase 4] User approves design preview
5. Result: ~/.claude/skills/git-commit-message/SKILL.md created
```

## Topic

$ARGUMENTS

### Handling Ambiguous Topics

If the topic is unclear or too broad, use AskUserQuestion to clarify:
- Scope: e.g., "git" → "git commits" vs "git branching" vs "git workflows"
- Target audience: beginner, intermediate, or advanced users
- Primary use case: what specific problem should the skill solve?

## Workflow Overview

Execute the following 4 phases in sequence to generate a skill for the topic provided above.

## Phase 1: Analysis & Agent Configuration

Analyze the topic, assess complexity, and configure the agent team in a single phase.

### Domain Classification

| Domain | Examples | Characteristics |
|--------|----------|-----------------|
| **Technical** | Programming, DevOps, CLI tools | Code examples, scripts, technical accuracy |
| **Business** | Workflows, documentation, processes | Procedures, templates, stakeholder communication |
| **Creative** | Content creation, design, writing | Quality criteria, style guides, iterative refinement |
| **Automation** | Task automation, integration | Scripts, error handling, scheduling |
| **Scientific** | Bioinformatics, cheminformatics, statistics, clinical | Domain-specific expertise via scientific-skills, reproducibility, data analysis |

### Complexity & Agent Selection

| Complexity | Criteria | Agents |
|------------|----------|--------|
| **Simple** | Single workflow, few edge cases | domain-expert, structure-designer, validator |
| **Medium** | Multiple workflows, branching logic | + workflow-architect |
| **Complex** | Multi-step processes, scripts needed | + tooling-specialist |

### Agent Roles

| Agent | Role |
|-------|------|
| domain-expert | Specialized knowledge for the topic domain |
| structure-designer | File structure and content organization |
| validator | Review designs, ensure quality standards |
| workflow-architect | Step-by-step processes (Medium/Complex) |
| tooling-specialist | Scripts and tool integrations (Complex) |
| scientific-domain-expert | Scientific expertise via scientific-skills (Scientific domain only) |

### Scientific Domain Expert Selection

When domain is **Scientific**, add `scientific-domain-expert` and select relevant scientific-skills based on topic keywords:

| Keywords | Scientific Skills to Invoke |
|----------|----------------------------|
| protein, sequence, FASTA, genome, alignment | `scientific-skills:biopython`, `scientific-skills:esm`, `scientific-skills:pysam` |
| molecule, SMILES, compound, drug, ligand | `scientific-skills:rdkit`, `scientific-skills:deepchem`, `scientific-skills:pubchem-database` |
| cell, RNA-seq, single-cell, expression, scRNA | `scientific-skills:scanpy`, `scientific-skills:anndata`, `scientific-skills:cellxgene-census` |
| statistics, hypothesis, p-value, regression | `scientific-skills:statistical-analysis`, `scientific-skills:statsmodels`, `scientific-skills:pymc` |
| paper, manuscript, citation, publication | `scientific-skills:scientific-writing`, `scientific-skills:peer-review`, `scientific-skills:literature-review` |
| quantum, qubit, circuit, gate | `scientific-skills:qiskit`, `scientific-skills:pennylane`, `scientific-skills:cirq` |
| clinical, patient, trial, diagnosis | `scientific-skills:pyhealth`, `scientific-skills:clinical-decision-support`, `scientific-skills:clinicaltrials-database` |
| pathway, metabolic, enzyme, reaction | `scientific-skills:cobrapy`, `scientific-skills:kegg-database`, `scientific-skills:reactome-database` |
| visualization, plot, figure, chart | `scientific-skills:scientific-visualization`, `scientific-skills:matplotlib`, `scientific-skills:plotly` |

The scientific-domain-expert uses the `Skill` tool to invoke relevant scientific-skills for specialized knowledge. See `references/agent-templates.md` for detailed prompts.

### Literature Review Panel (5 Scientists) - Optional

For Scientific domains with methodological workflows, optionally add a Literature Review Panel of 5 scientists who search and review scientific literature to provide evidence-based feedback.

**Panel Composition:**

| Scientist | Role | Literature Focus |
|-----------|------|------------------|
| **Methodologist** | Review methods literature | Best practices, benchmarks, guidelines |
| **Domain Specialist** | Review domain papers | Recent advances, standard protocols |
| **Statistician** | Review statistical methods | Appropriate tests, assumptions |
| **Reproducibility Advocate** | Review reproducibility guidelines | FAIR principles, reporting standards |
| **Applications Researcher** | Review application papers | Real-world use cases, case studies |

**Literature Sources:**
- `scientific-skills:pubmed-database` - Peer-reviewed articles
- `scientific-skills:biorxiv-database` - Preprints
- `scientific-skills:openalex-database` - Scholarly metadata
- `scientific-skills:research-lookup` - Quick research queries

See `references/agent-templates.md` for detailed Literature Review Panel prompts.

## Phase 2: Multi-Agent Discussion

Conduct a structured 2-round discussion using the Task tool. Execute agents in parallel within each round for efficiency.

### Discussion Rounds

**Round 1: Initial Proposals** (All agents in parallel)
- domain-expert: Key knowledge areas and pitfalls
- structure-designer: File structure and content organization
- validator: Quality requirements and potential issues
- workflow-architect: Primary user workflows (if included)
- tooling-specialist: Automation opportunities (if included)

**Round 2: Synthesis & Finalization** (All agents in parallel)
- Respond to Round 1 proposals
- Resolve conflicts and build consensus
- Finalize specifications with explicit sign-off
- Validator provides final quality assessment with structured output:
  ```
  ## Decision: [APPROVED | NEEDS_REVISION]
  ## Rationale: [brief explanation]
  ## Open Issues: [if any]
  ```

**Conflict Resolution**: If validator outputs NEEDS_REVISION, use AskUserQuestion to present the conflict and options to the user before proceeding to Phase 3.

### Parallel Agent Invocation

Invoke all agents within a round simultaneously using multiple Task tool calls in a single message:

```
Task tool parameters (for each agent):
  subagent_type: general-purpose
  description: "[Agent name] Round [N]"
  prompt: |
    You are the [AGENT_NAME] in a skill design discussion.

    Topic: [SKILL_TOPIC]
    Round: [N] of 2

    Previous discussion (Round 1 only if Round 2):
    [ACCUMULATED_DISCUSSION]

    Your role: [AGENT_ROLE_DESCRIPTION]

    Provide your expert perspective. Keep under 200 words.
```

See `references/agent-templates.md` for detailed prompts.

### Discussion Log Format

```markdown
## Discussion Log

### Round 1 (Parallel)
**domain-expert**: [response]
**structure-designer**: [response]
**validator**: [response]

### Round 2 (Parallel)
[same structure with responses to Round 1]
```

## Phase 3: User Confirmation

Present the design for user approval before creating files.

### Design Preview Format

Present to user:

```markdown
## Skill Design Preview

### Skill Name
[name]

### Trigger Phrases
- "[phrase 1]"
- "[phrase 2]"
- "[phrase 3]"

### File Structure
[tree structure]

### SKILL.md Outline
1. [Section 1]
2. [Section 2]
...

### Additional Resources
- references/[file]: [purpose]
- scripts/[file]: [purpose]
```

### Collect Feedback

Use AskUserQuestion to get user input:

```
questions:
  - question: "Does this skill design meet your needs?"
    header: "Approval"
    options:
      - label: "Yes, create the skill"
        description: "Proceed with generating all skill files"
      - label: "Modify structure"
        description: "Adjust file organization or content scope"
      - label: "Revise approach"
        description: "Go back to agent discussion with new direction"
```

### Handle Modifications

If user requests changes:
- For minor adjustments: Update design and re-present
- For significant changes: Return to Phase 2 with updated direction

## Phase 4: Skill Generation

Create all skill files based on the approved design.

### File Creation Order

1. Create skill directory structure
2. Write SKILL.md (main file first)
3. Write references/ files
4. Write scripts/ files (if any)
5. Copy/create assets/ files (if any)

### SKILL.md Template

```markdown
---
name: [skill-name]
description: This skill should be used when the user asks to "[trigger 1]", "[trigger 2]", "[trigger 3]", or [broader context]. [Brief capability summary].
---

# [Skill Title]

[Overview paragraph - purpose and capabilities]

## When to Use This Skill

[Specific scenarios and use cases]

## Core Workflow

### Step 1: [First Action]

[Imperative instructions]

### Step 2: [Second Action]

[Imperative instructions]

[Continue as needed]

## Additional Resources

### Reference Files

- **`references/[file].md`** - [Description]

### Scripts

- **`scripts/[file].sh`** - [Description]

## Validation

[How to verify correct skill usage]
```

### Dynamic Tool Generation

If tooling-specialist recommended scripts during discussion, generate them using this workflow:

#### Step 1: Review Script Specifications

From tooling-specialist's Round 2 output, extract for each script:
- Filename and language (Python/Bash)
- Purpose and priority (Essential/Recommended/Optional)
- Inputs, outputs, exit codes
- Dependencies

#### Step 2: Generate Script Code

Use the templates in `references/agent-templates.md` as base structure.

**For Python scripts:**
```python
#!/usr/bin/env python3
"""[Script Name] - [Purpose from spec]"""
import argparse, sys
# Implement based on specification
```

**For Bash scripts:**
```bash
#!/usr/bin/env bash
# [Script Name] - [Purpose from spec]
set -euo pipefail
# Implement based on specification
```

#### Step 3: Present for User Approval

For each script, show:

```markdown
## Script: [filename]

**Purpose**: [one-line description]
**Priority**: Essential | Recommended | Optional
**Language**: Python | Bash

### Code Preview
\`\`\`[language]
[generated code]
\`\`\`

### Usage
\`\`\`bash
[example invocation]
\`\`\`
```

Then request approval:
```
AskUserQuestion:
  question: "Approve scripts for inclusion?"
  options:
    - "Approve all scripts"           # Batch approval for efficiency
    - "Review individually"           # One-by-one approval
    - "Skip all scripts"              # No scripts needed
```

**Note**: "Approve all" is recommended for Essential-priority scripts. Use "Review individually" for Optional scripts or when modification is needed.

#### Step 4: Create Approved Scripts

1. Create `scripts/` directory if needed
2. Write script file with executable permissions
3. Add script documentation to SKILL.md

```bash
mkdir -p ~/.claude/skills/[skill-name]/scripts
# Write script file
chmod +x ~/.claude/skills/[skill-name]/scripts/[script-name]
```

#### Step 5: Document in SKILL.md

Add to the skill's "Additional Resources" section:

```markdown
### Scripts

- **`scripts/[name].py`** - [Purpose]. Usage: `python scripts/[name].py --input [file]`
- **`scripts/[name].sh`** - [Purpose]. Usage: `./scripts/[name].sh [args]`
```

#### Script Quality Checklist

Before finalizing scripts, verify:

- [ ] Shebang line present (`#!/usr/bin/env python3` or `#!/usr/bin/env bash`)
- [ ] Usage documentation in header comments
- [ ] Proper argument parsing (argparse for Python, getopts/case for Bash)
- [ ] Error handling with meaningful exit codes
- [ ] Input validation before processing
- [ ] No hardcoded paths (use relative paths or arguments)
- [ ] Dependencies documented

### Completion Report

After creating all files, output:

```markdown
## Skill Created Successfully

**Location**: ~/.claude/skills/[skill-name]/

**Files Created**:
- SKILL.md ([word count] words)
- references/[files if any]
- scripts/[files if any]

**Trigger Phrases**:
- "[phrase 1]"
- "[phrase 2]"

**Next Steps**:
1. Test by using a trigger phrase
2. Iterate based on usage

**Verify Triggers**:
Test each trigger phrase by typing it; confirm skill activates correctly.
```

## Quality Standards

For detailed quality standards, see `references/quality-standards.md`.

**Quick Checklist:**
- [ ] Frontmatter: name (lowercase-hyphenated), description (3+ trigger phrases)
- [ ] Writing: Imperative form, no second-person pronouns
- [ ] Length: SKILL.md 1,500-2,000 words, split to references/ if exceeding
- [ ] Structure: Clear headings, tables for data, code blocks for examples

## Troubleshooting

### Agent Discussion Not Converging

If agents disagree after 2 rounds:
1. Identify the core conflict (scope, approach, complexity)
2. Use AskUserQuestion to get user preference
3. Resume with clarified direction

### Skill Too Large

If SKILL.md exceeds 2,500 words:
1. Identify sections with detailed explanations
2. Extract to references/ files
3. Replace with summary and reference link
4. Re-verify word count

### Missing Trigger Activation

If the created skill does not trigger:
1. Verify frontmatter description includes exact user phrases
2. Add more specific trigger phrases
3. Test with variations of expected user queries

### Failure Recovery

| Failure Type | Symptoms | Recovery Action |
|--------------|----------|-----------------|
| Task tool error | Agent fails to respond or times out | Retry with same prompt; if persistent, reduce agent count |
| Agent produces nonsense | Irrelevant or incoherent output | Re-invoke with more specific prompt; add context |
| Validation fails | Validator rejects design repeatedly | Use AskUserQuestion to get user decision on conflict |
| User rejects design | Phase 3 approval denied | Return to Phase 2 with user's feedback incorporated |
| File creation fails | Permission or path errors | Verify `~/.claude/skills/` exists and is writable |

**General Recovery Protocol:**
1. Identify which phase failed
2. Check if input to that phase was valid
3. Retry the phase with adjusted parameters
4. If retry fails, fall back to manual user input via AskUserQuestion

## Additional Resources

### Reference Files

- **`references/agent-templates.md`** - Detailed prompt templates for each agent type with round-by-round instructions
- **`references/quality-standards.md`** - Comprehensive quality standards for skill creation
- **`references/script-templates.md`** - Python and Bash script templates for tooling-specialist

### Related Skills

Study these for implementation patterns:
- `../debate/SKILL.md` - Task tool usage for sequential multi-agent calls
- Plugin skill-development skill for comprehensive writing standards

### Skill Anatomy Reference

```
skill-name/
├── SKILL.md                    # Main entry point (always required)
│   ├── YAML frontmatter        # Metadata for discovery
│   └── Markdown body           # Core instructions
├── references/                 # Detailed documentation (load on demand)
│   ├── detailed-guide.md       # Comprehensive procedures
│   └── troubleshooting.md      # Problem resolution
├── scripts/                    # Executable code (run without loading)
│   ├── validate.py             # Validation utilities
│   └── generate.sh             # Generation scripts
└── assets/                     # Output resources (copy/use directly)
    └── template.md             # Reusable templates
```
