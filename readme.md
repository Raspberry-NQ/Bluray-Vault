# Bluray Vault

Blu-ray archival backup system with extreme data recoverability. Sacrifices storage efficiency and speed to guarantee data survival even under severe physical disc damage.

## Core Features

- **Forward Error Correction** — Multi-tier erasure coding (Cauchy RS + inter-disc RS + LRC)
- **Encryption** — AES-256-GCM authenticated encryption at rest
- **Recoverability** — Tolerate disc surface loss, cracks, and entire disc failures

## Architecture

```
Python CLI / Orchestrator
  ├── Encryption Layer (AES-256-GCM, Argon2id key derivation)
  ├── Erasure Coding Engine
  │   ├── Cauchy RS (intra-disc, GF(2^8), XOR-optimized)
  │   ├── Vandermonde RS (inter-disc, GF(2^16))
  │   └── LRC (local repair, reduced I/O)
  ├── Disc Layout Manager (UDF, chunk mapping, metadata replication)
  └── Blu-ray Disc I/O
```

## Redundancy Tiers

| Tier | Scope | Algorithm | Example Config | Tolerance |
|------|-------|-----------|---------------|-----------|
| 1 | Intra-disc | Cauchy RS | 16+8 (50% overhead) | 33% disc surface loss |
| 2 | Inter-disc | Vandermonde RS | 10+3 discs | 3 entire disc loss |
| 3 | Local repair | LRC | (12,6,5) | Fast partial recovery |

## Quick Start

```bash
pip install -e .
bbackup                    # Interactive mode
bbackup init <volume>      # Initialize backup volume
bbackup add <volume> <files...>
bbackup burn <volume>
bbackup recover <volume> <output>
bbackup verify <volume>
```

## Project Structure

```
src/
  cli/        CLI and interactive UI
  core/       Volume, backup, recovery workflows
  encoder/    Erasure coding interfaces (Cauchy RS, Vandermonde RS, LRC)
  crypto/     Encryption layer interface
  disc/       Disc layout and I/O
  models/     Data schemas
Cauchy-RS-FEC/  Reference C implementation
papers/          Research papers
```

## Tech Stack

- Python 3.10+ (CLI, orchestration, workflow)
- C++ (future: core encoding/decoding engine with SIMD)

*Raspberry 2026.4*
