# Flag Forge

**Feature flags that live in your repo.** No SaaS dashboard, no runtime dependency, no vendor lock-in. Just a YAML file in version control with a powerful evaluation engine.

```
$ flag-forge create dark_mode --desc "Dark mode UI" --rollout 25 --owner design-team
Created flag: dark_mode (OFF, 25% rollout)

$ flag-forge toggle dark_mode
Flag 'dark_mode' is now ON

$ flag-forge eval dark_mode --context user_id=alice
Flag: dark_mode
Result: ENABLED
Reason: rollout_25pct

$ flag-forge eval dark_mode --context user_id=bob
Flag: dark_mode
Result: DISABLED
Reason: rollout_excluded_25pct
```

## Why Flag Forge?

- **Git-native** - flags stored in `.flags.yml`, versioned with your code
- **Deterministic rollout** - same user always gets same result (consistent hashing)
- **Targeting rules** - attribute matching (country, plan, role, etc.)
- **Stale detection** - automatically finds flags that should be cleaned up
- **Code scanning** - greps your codebase for flag references, finds unused and undefined flags
- **Python SDK** - `from flag_forge import FlagClient` and you're done
- **Zero dependencies at runtime** - just PyYAML

## Install

```bash
pip install flag-forge
```

## Quick Start

```bash
# Initialize with example flag
flag-forge init

# Create flags
flag-forge create payment_v2 --desc "New payment flow" --rollout 10
flag-forge create beta_ui --desc "Beta UI" --enabled

# Toggle
flag-forge toggle payment_v2

# Evaluate
flag-forge eval payment_v2 --context user_id=123

# Find stale flags
flag-forge stale --dir ./src
```

## Python SDK

```python
from flag_forge import FlagClient

flags = FlagClient(environment="production")

# Simple check
if flags.is_enabled("dark_mode", {"user_id": "alice"}):
    render_dark_mode()

# Detailed evaluation
result = flags.evaluate("payment_v2", {"user_id": "123", "plan": "pro"})
print(result.enabled)  # True/False
print(result.reason)   # "rollout_25pct", "targeting_match", etc.

# Get all flags for frontend
all_flags = flags.get_all_flags({"user_id": "123"})
# {"dark_mode": True, "payment_v2": False, "beta_ui": True}
```

## Flag Schema (.flags.yml)

```yaml
flags:
  dark_mode:
    enabled: true
    description: "Dark mode UI"
    rollout: 25
    targeting:
      - attribute: plan
        operator: in
        values: ["pro", "enterprise"]
    environments:
      - production
      - staging
    owner: "design-team"
    created_at: "2026-01-15T10:00:00Z"
```

## Targeting Operators

| Operator | Description | Example |
|----------|-------------|---------|
| `eq` / `in` | Value in list | `plan in [pro, enterprise]` |
| `neq` / `not_in` | Value not in list | `country not_in [CN, RU]` |
| `gt`, `gte`, `lt`, `lte` | Numeric comparison | `age gte [18]` |
| `contains` | String contains | `email contains [@company.com]` |
| `starts_with` | String prefix | `name starts_with [test_]` |
| `regex` | Regex match | `email regex [.*@corp\\.com]` |

## Commands

| Command | Description |
|---------|-------------|
| `flag-forge init` | Create .flags.yml with example |
| `flag-forge list [--json]` | List all flags |
| `flag-forge create <name>` | Create a new flag |
| `flag-forge toggle <name>` | Toggle enabled/disabled |
| `flag-forge eval <name> -c key=val` | Evaluate a flag |
| `flag-forge stale [-d dir]` | Find stale/unused/undefined flags |
| `flag-forge cleanup [--remove]` | Remove stale flags |

## License

MIT
