# Smartphone Intel Clank v0.2 — Evidence Engine

> Status: Experimental / under construction

**From model numbers to intelligence.**

v0.1 built the sensors.  
v0.2 builds the interpretation layer.

Collectors stay dumb. They only answer: *"What did I discover?"*  
Everything else — enrichment, aliases, timeline, decay, families, alerts — lives downstream.

> Accuracy > Speed. Never invent data. Unknown fields stay `null`.

## Pipeline

```
Collectors
    ↓
Normalization
    ↓
Knowledge Enrichment      ← deterministic rules, YAML knowledge base
    ↓
Entity Resolution         ← regional variants, family linking
    ↓
Aliases                   ← persistent codename / marketing / model map
    ↓
Timeline                  ← append-only chronological evidence history
    ↓
Confidence (+ Decay)      ← old evidence loses weight; official never decays
    ↓
Alerts                    ← meaningful updates only
```

## What's New in v0.2

| Module | Purpose |
|--------|---------|
| `knowledge/` | Deterministic enrichment (family, tier, variant, launch window, chipset class) |
| `knowledge/data/manufacturers.yaml` | Manufacturer profiles — edit data, not code |
| `knowledge/data/codenames.yaml` | Codename mappings |
| `entity_resolution/aliases.py` | Persistent alias table |
| `entity_resolution/timeline.py` | Append-only device event history |
| `entity_resolution/decay.py` | Configurable confidence decay |
| `entity_resolution/families.py` | Explicit parent/child family trees |
| `knowledge/change_detection.py` | Multi-hash change detection (text / DOM / downloads / images) |

## CLI

```bash
python main.py init
python main.py run --once
python main.py status

python main.py inspect SM-S957B      # full intelligence view
python main.py timeline SM-S957B     # chronological evidence
python main.py family "Galaxy S"     # family tree
python main.py decay                 # recompute confidence decay
python main.py stats                 # historical lead-time stats
python main.py test-alert
```

### Example `inspect` output

```
Galaxy S27 Ultra
Model:          SM-S957B
Manufacturer:   samsung
Family:         Galaxy S
Tier:           flagship
Variant:        global_or_india
Launch month:   1
Chipset class:  flagship
Confidence:     55  (base 60)
KB confidence:  high

Aliases
  [model] SM-S957B
  [marketing] Galaxy S27 Ultra

Evidence
  bluetooth_sig         weight=18  (orig 20)
  samsung_support       weight=10  (orig 10)
  samsung_firmware      weight=25  (orig 25)

Timeline
  2026-05-14  bluetooth_sig
  2026-06-03  samsung_support
  2026-07-07  samsung_firmware
```

## Configuration

All intelligence knobs live in `config/config.yaml`:

```yaml
intelligence:
  knowledge_data_dir: "knowledge/data"
  apply_decay_on_resolve: true
  decay_schedule:
    - [30, 0.90]
    - [90, 0.75]
    - [180, 0.50]
    - [365, 0.30]
  never_decay_source_types:
    - official
```

Manufacturer knowledge is pure data:

```yaml
# knowledge/data/manufacturers.yaml
samsung:
  typical_flagship_launch_month: 1
  regional_suffixes:
    B: global_or_india
    U: usa
    N: korea
  series_patterns:
    - pattern: "^SM-S9[0-9]{2}"
      family: "Galaxy S"
      tier: flagship
```

## Design Rules (unchanged)

- Collectors never enrich, score, or alert.
- No AI / LLMs / vector DBs / microservices / Redis / Kafka.
- SQLite remains the default; schema is Postgres-ready.
- Never guess. Null is better than wrong.
- One developer should still understand the whole codebase in an afternoon.

## Success Criteria (v0.2)

The system answers **"What do we know about this device?"** instead of merely **"We found this model number."**

When a discovery arrives it:

1. Identifies / resolves the device  
2. Attaches evidence  
3. Updates confidence (with decay)  
4. Appends to timeline  
5. Registers aliases  
6. Applies knowledge enrichment  
7. Updates family relationships  
8. Persists  
9. Sends a concise Discord alert only if the new intelligence is meaningful  

## Supported Manufacturers

Samsung · Google · OnePlus · Nothing · Xiaomi

## Future (still not implemented)

TENAA, Wi-Fi Alliance, GCF, retailer monitoring, OTA package analysis, camera config extraction, kernel repos, supply-chain, AI correlation, launch window prediction, dashboard UI.

Internally this is already the **Evidence Engine**.  
Today it ingests phone certifications. Tomorrow it can ingest anything with pluggable collectors.
