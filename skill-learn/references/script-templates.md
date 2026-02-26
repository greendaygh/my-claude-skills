# Script Templates Reference

Production-ready templates for Python and Bash scripts. Use these as the base structure when generating scripts for skills.

## Python Script Template

```python
#!/usr/bin/env python3
"""
[Script Name] - [Brief description]

Usage:
    python [script-name].py [arguments]

Example:
    python validate-input.py --file input.txt
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="[Description]")
    parser.add_argument("--input", "-i", required=True, help="Input file/value")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    try:
        result = process(args.input, verbose=args.verbose)

        if args.output:
            Path(args.output).write_text(result)
        else:
            print(result)

        return 0

    except FileNotFoundError as e:
        print(f"Error: File not found - {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


def process(input_value, verbose=False):
    """Main processing logic."""
    # TODO: Implement based on script purpose
    pass


if __name__ == "__main__":
    sys.exit(main())
```

### Python Template Features

- **Argparse**: Standard argument parsing with help text
- **Error handling**: Try/except with specific exit codes
- **Verbose mode**: Optional detailed output
- **Path handling**: Uses pathlib for cross-platform compatibility

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | File not found |
| 2 | General error |

---

## Bash Script Template

```bash
#!/usr/bin/env bash
#
# [Script Name] - [Brief description]
#
# Usage:
#     ./[script-name].sh [arguments]
#
# Example:
#     ./setup.sh --env production

set -euo pipefail

# Constants
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME="$(basename "$0")"

# Default values
VERBOSE=false
OUTPUT_DIR="."

# Functions
usage() {
    cat << EOF
Usage: $SCRIPT_NAME [OPTIONS]

Options:
    -i, --input FILE    Input file (required)
    -o, --output DIR    Output directory (default: current)
    -v, --verbose       Enable verbose output
    -h, --help          Show this help message

Examples:
    $SCRIPT_NAME -i data.txt -o ./output
    $SCRIPT_NAME --input config.json --verbose
EOF
}

log() {
    if [[ "$VERBOSE" == true ]]; then
        echo "[INFO] $*" >&2
    fi
}

error() {
    echo "[ERROR] $*" >&2
    exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--input)
            INPUT_FILE="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Validate required arguments
[[ -z "${INPUT_FILE:-}" ]] && error "Input file is required. Use -i or --input."
[[ ! -f "$INPUT_FILE" ]] && error "Input file not found: $INPUT_FILE"

# Main logic
main() {
    log "Processing: $INPUT_FILE"

    # TODO: Implement main logic based on script purpose

    log "Done."
}

main "$@"
```

### Bash Template Features

- **Strict mode**: `set -euo pipefail` for safety
- **Usage function**: Auto-generated help text
- **Logging**: Conditional verbose output to stderr
- **Error handling**: Dedicated error function with exit
- **Argument parsing**: Long and short options supported

### Bash Best Practices

| Practice | Implementation |
|----------|----------------|
| Fail on errors | `set -e` |
| Fail on undefined vars | `set -u` |
| Fail on pipe errors | `set -o pipefail` |
| Quote variables | `"$VAR"` not `$VAR` |
| Use readonly for constants | `readonly VAR="value"` |

---

## Language Selection Guide

| Use Case | Recommended | Rationale |
|----------|-------------|-----------|
| File operations | Bash | Native, fast, no dependencies |
| Text processing | Bash | sed/awk available |
| API calls | Python | requests library |
| JSON parsing | Python | json module built-in |
| Complex logic | Python | Better control flow |
| Cross-platform | Python | Consistent behavior |
| Simple automation | Bash | Lightweight |

---

## Script Quality Checklist

Before finalizing any script:

- [ ] Shebang line present (`#!/usr/bin/env python3` or `#!/usr/bin/env bash`)
- [ ] Usage documentation in header comments
- [ ] Proper argument parsing
- [ ] Error handling with meaningful exit codes
- [ ] Input validation before processing
- [ ] No hardcoded paths (use arguments or relative paths)
- [ ] Dependencies documented in comments
- [ ] Verbose/debug mode available
