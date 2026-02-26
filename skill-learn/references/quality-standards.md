# Quality Standards Reference

Detailed quality standards for skill creation. Reference this document when generating or reviewing skills.

## Frontmatter Requirements

| Field | Format | Example |
|-------|--------|---------|
| `name` | Lowercase, hyphenated | `api-documentation` |
| `description` | Third-person, 3+ trigger phrases | "This skill should be used when the user asks to..." |
| `user_invocable` | Optional boolean | `true` if slash-command invocable |
| `arguments` | Optional, angle brackets | `<topic> [--option]` |

### Description Pattern

```
This skill should be used when the user asks to "[trigger 1]", "[trigger 2]", "[trigger 3]", or wants to [broader context]. [Brief capability summary].
```

**Requirements:**
- Start with "This skill should be used when"
- Include 3-5 specific trigger phrases in quotes
- End with capability summary

## Content Requirements

### Writing Style

| Do | Don't |
|----|-------|
| "Create the file..." | "You should create the file..." |
| "Configure the settings..." | "You can configure..." |
| "Verify the output..." | "You need to verify..." |

**Rules:**
- Imperative/infinitive form throughout ("Create...", "Configure...", "To accomplish X, do Y")
- No second-person pronouns ("you should", "you can", "you need to")
- Active voice, direct instructions
- Consistent terminology throughout

### Length Guidelines

| File | Target | Maximum |
|------|--------|---------|
| SKILL.md body | 1,500-2,000 words | 3,000 words |
| references/ file | 500-1,500 words | 3,000 words |
| scripts/ file | As needed | No limit |

**If exceeding limits:**
1. Identify sections with detailed explanations
2. Extract to references/ files
3. Replace with summary and reference link

### Structural Requirements

- Clear hierarchical section headings (##, ###)
- Tables for structured data
- Code blocks for examples and templates
- Bullet lists for procedures with discrete steps
- Numbered lists for sequential steps

## Progressive Disclosure

Organize content into tiers loaded only when needed:

| Tier | Location | Content Type | When Loaded |
|------|----------|--------------|-------------|
| 1 | Frontmatter | Name + description | Always in context |
| 2 | SKILL.md body | Core workflow, essential procedures | When skill triggers |
| 3 | references/ | Detailed guides, advanced topics | On explicit reference |
| 4 | scripts/ | Executable code | On execution only |
| 5 | assets/ | Templates, media | On file operations |

### Content Placement Guide

**In SKILL.md (Tier 2):**
- Prerequisites and quick start
- Core workflow (phases/steps)
- Essential examples
- Troubleshooting summary

**In references/ (Tier 3):**
- Detailed agent prompts
- Extended examples
- Quality standards (this file)
- Script templates

**In scripts/ (Tier 4):**
- Validation utilities
- Generation scripts
- Processing tools

## Common Mistakes to Avoid

| Mistake | Problem | Solution |
|---------|---------|----------|
| Putting everything in SKILL.md | Context overload | Split to references/ |
| Second-person writing | Inconsistent style | Use imperative form |
| Vague trigger descriptions | Won't activate | Add specific quoted phrases |
| Referencing non-existent files | Broken links | Verify before referencing |
| Inline code that should be scripts | Maintenance burden | Extract to scripts/ |
| Missing error handling | Poor UX | Add troubleshooting section |

## Quality Checklist

Before finalizing a skill, verify:

### Structure
- [ ] SKILL.md exists with valid frontmatter
- [ ] name field is lowercase-hyphenated
- [ ] description has 3+ trigger phrases
- [ ] All referenced files exist

### Content
- [ ] Word count within guidelines
- [ ] Imperative writing style throughout
- [ ] No second-person pronouns
- [ ] Clear section hierarchy

### Functionality
- [ ] Trigger phrases are specific and unique
- [ ] Workflow steps are actionable
- [ ] Error cases are documented
- [ ] Examples are concrete and runnable
