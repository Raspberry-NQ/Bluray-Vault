## Blu-ray DVD Backup System

A robust archival backup system utilizing Blu-ray optical discs for long-term data preservation, with emphasis on extreme data recoverability even under severe physical disc damage.

### Project Goals

1. **Data Encryption** — All data written to disc must be encrypted at rest
2. **Multi-format Support** — Primarily targets video, images, and documents
3. **Extreme Data Recoverability** — Ensure data can be recovered even when discs suffer physical damage (scratches, cracks, degradation); willing to sacrifice storage efficiency and I/O speed for this guarantee
4. **Tech Stack** — C++ (core encoding/decoding engine) + Python (CLI, orchestration, workflow)

*Raspberry 2026.4*

---

## Technical Roadmap

### Core Technical Challenge

Blu-ray discs are susceptible to physical damage (scratches, cracks, disc rot) and aging degradation. The system must provide **forward error correction (FEC)** capabilities far beyond what Blu-ray's built-in ECC (BIS/LDS Reed-Solomon Product Code) offers. This requires an **application-level erasure coding layer** that generates sufficient redundancy to reconstruct data from heavily damaged media.

### Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  Python CLI / Orchestrator           │
│  (backup workflow, disc management, recovery UI)    │
├─────────────────────────────────────────────────────┤
│                Encryption Layer (AES-256-GCM)        │
├─────────────────────────────────────────────────────┤
│            Erasure Coding Engine (C++ core)          │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ Reed-Solomon │ │ Cauchy RS    │ │  LRC (Local  │  │
│  │ (Vandermonde)│ │ (optimized)  │  │  Repair)     │  │
│  └─────────────┘ └──────────────┘ └──────────────┘  │
├─────────────────────────────────────────────────────┤
│          Galois Field Arithmetic (GF(2^w))           │
│          SIMD-accelerated (SSE/AVX/NEON)             │
├─────────────────────────────────────────────────────┤
│          Disc Layout / Parity Volume Manager         │
│  (data chunks ↔ disc mapping, parity distribution)  │
├─────────────────────────────────────────────────────┤
│          Blu-ray Disc I/O (UDF filesystem)           │
└─────────────────────────────────────────────────────┘
```

### Erasure Coding Strategy

The system uses a **multi-tier redundancy** approach:

#### Tier 1: Intra-disc Redundancy (Cauchy Reed-Solomon)
- Each disc is divided into N data stripes + M parity stripes
- Cauchy RS over GF(2^8) or GF(2^16), optimized with XOR-only operations
- Default ratio: 16 data + 8 parity (50% overhead) → tolerates 33% disc surface loss
- Supports configurable redundancy levels:
  - **Standard**: 16+4 (20% overhead, tolerates 20% damage)
  - **High**: 16+8 (50% overhead, tolerates 33% damage)
  - **Extreme**: 8+8 (100% overhead, tolerates 50% damage)

#### Tier 2: Inter-disc Redundancy (Reed-Solomon across discs)
- A logical volume spans across K discs
- Uses Vandermonde RS over GF(2^16) for cross-disc parity
- Example: 10 data discs + 3 parity discs → lose 3 entire discs and still recover
- Parity discs store repair information for the whole volume

#### Tier 3: Local Repair Codes (LRC)
- Hybrid approach: combine local parity groups with global parity
- When a small area is damaged, only need to read from the local group (not all discs)
- Significantly reduces recovery I/O for partial damage scenarios
- Structure: e.g., (12,6,5) LRC — 12 total, 6 data, 5 parity (2 local + 3 global)

### Encryption Design

- Algorithm: AES-256-GCM (authenticated encryption)
- Key derivation: Argon2id from user passphrase
- Per-disc random salt stored in disc metadata (unencrypted)
- Per-chunk nonce derived from chunk index + disc salt
- Key file export option for offline key management

### Disc Layout

```
┌──────────────────────────────────┐
│  Disc Header (unencrypted)       │
│  - Volume UUID, disc index       │
│  - Erasure code parameters       │
│  - Encryption salt               │
│  - Chunk manifest (encrypted)    │
├──────────────────────────────────┤
│  Data Region (encrypted)         │
│  - Chunk 0  (stripe 0)          │
│  - Chunk 1  (stripe 1)          │
│  - ...                          │
│  - Chunk N  (stripe N-1)        │
├──────────────────────────────────┤
│  Parity Region (encrypted)       │
│  - Parity Chunk 0                │
│  - Parity Chunk 1                │
│  - ...                          │
│  - Parity Chunk M-1              │
├──────────────────────────────────┤
│  Recovery Manifest (replicated)  │
│  - Copies of disc header at      │
│    multiple locations on disc    │
└──────────────────────────────────┘
```

- UDF filesystem for Blu-ray compatibility
- Recovery manifest replicated at 3+ positions on disc for header survivability
- Chunk size: 1 MiB (tunable)

---

## Development Steps

### Phase 1: Foundation (Core Math Library)

**Goal**: Build the Galois field arithmetic engine with SIMD acceleration.

1. Implement GF(2^8) and GF(2^16) arithmetic primitives
   - Addition (XOR), multiplication, division, inverse
   - Lookup tables for GF(2^8); composite field for GF(2^16)
2. Build SIMD-accelerated vector operations
   - SSE/AVX2 for x86, NEON for ARM (Mac)
   - Region multiply: GF region × constant, GF region × GF region
3. Implement unit tests for all Galois field operations
4. Benchmark: validate SIMD speedup over scalar implementation

**Deliverable**: `libgfarith` — standalone C++ library with C API

### Phase 2: Erasure Coding Engine

**Goal**: Implement the core erasure coding algorithms.

5. Implement Vandermonde Reed-Solomon encoding/decoding
   - Encoding matrix construction (Vandermonde matrix over GF(2^w))
   - Gaussian elimination decoder for erasure recovery
   - Support for any (n, k) configuration
6. Implement Cauchy Reed-Solomon encoding/decoding
   - Cauchy matrix construction (guaranteed invertibility)
   - XOR-optimized encoding (convert GF operations to XOR schedules)
   - Benchmark against Vandermonde RS
7. Implement Locally Repairable Codes (LRC)
   - Optimal LRC construction per Gopalan et al. bounds
   - Local group decoding + global decoding two-phase approach
8. Implement erasure detection: integrate with disc read errors
   - Map I/O read failures to erasure indicators
   - Partial chunk damage detection via checksums (SHA-256 per chunk)

**Deliverable**: `liberasure` — erasure coding library wrapping `libgfarith`

### Phase 3: Encryption Layer

**Goal**: Add authenticated encryption for data at rest.

9. Implement AES-256-GCM encryption/decryption
   - Use OS-native crypto APIs (CommonCrypto on macOS, OpenSSL fallback)
   - Chunk-level encryption with unique nonces
10. Implement key management
    - Argon2id passphrase → AES key derivation
    - Key file export/import
    - Per-volume and per-disc key separation

**Deliverable**: `libcrypto_layer` — encryption wrapper library

### Phase 4: Disc Layout & I/O Management

**Goal**: Define and implement the on-disc data format.

11. Design and implement disc header / metadata format
    - Volume UUID, disc index, code parameters
    - Chunk manifest (offset, size, checksum, stripe ID)
    - Binary format with versioning field
12. Implement UDF filesystem integration
    - Create UDF images for Blu-ray (udfinfo / mkudffs / growisofs)
    - Multi-session support for append operations
13. Implement disc write pipeline
    - Chunking → encryption → erasure encoding → UDF layout → burn
    - Progress tracking and resume capability
14. Implement disc read pipeline
    - Read → detect errors → erasure decode → decrypt → reassemble
    - Partial read support (extract individual files without full decode)

**Deliverable**: `libdiscio` — disc I/O and layout management library

### Phase 5: Python CLI & Orchestration

**Goal**: Build the user-facing tool.

15. Design Python CLI interface
    ```
    bbackup init <volume>              # Initialize a new backup volume
    bbackup add <volume> <files...>    # Add files to volume
    bbackup burn <volume> [--disc N]   # Burn pending data to disc(s)
    bbackup verify <volume> [--disc N] # Verify disc integrity
    bbackup recover <volume> <output>  # Recover data from disc set
    bbackup status <volume>            # Show volume/disc status
    bbackup key export <volume>        # Export volume key
    ```
16. Implement backup workflow orchestration
    - File scanning and categorization (video/image/document)
    - Staging area management (pending data before burn)
    - Multi-disc spanning logic
17. Implement recovery workflow
    - Scan available discs, identify damage level
    - Determine minimum set of discs needed for recovery
    - Progressive recovery (recover what's possible with partial discs)
18. Implement verification and health monitoring
    - Read-back verification after burn
    - Periodic disc health check (read test with CRC)
    - Damage assessment report

**Deliverable**: `bbackup` — Python CLI tool

### Phase 6: Advanced Features & Hardening

**Goal**: Production-quality reliability and usability.

19. Recovery manifest replication and embedded redundancy
    - Store critical metadata at 3+ physical locations on each disc
    - Error-correcting codes on the manifest itself
20. Partial damage recovery optimization
    - Smart scheduling: read undamaged regions first
    - Skip known-bad sectors to avoid drive errors/retries
21. Cross-platform support
    - macOS (primary), Linux (secondary)
    - Drive enumeration and compatibility detection
22. Documentation and user guide
    - Usage documentation
    - Disaster recovery playbook
    - Disc longevity best practices

**Deliverable**: Release v1.0

---

## Reference Papers

### Papers in Repository (Chinese)

| File | Topic | Key Contribution |
|------|-------|-----------------|
| `基于纠删码的光盘库数据纠错技术研究_张效群.pdf` | Erasure coding for optical disc libraries | RS-based erasure coding applied to optical disc library systems; disc-level fault tolerance |
| `基于估错码的数据纠错机制研究_魏兴慎.pdf` | Error estimation coding for data correction | Analysis of error patterns in optical media; error prediction and adaptive redundancy |
| `分布式存储系统中Reed-Solomon码快速解码算法研究_林泽冰.pdf` | Fast RS decoding for distributed storage | Optimized RS decoding algorithms; matrix operations and scheduling for erasure recovery |

### Papers in Repository (English) — `papers/` directory

| File | Authors/Year | Topic | Relevance |
|------|-------------|-------|-----------|
| `Plank1997_Tutorial_RS_Coding_RAID.pdf` | Plank, 1997 | Tutorial: RS coding for RAID-like fault tolerance | **Essential** — foundational reference for RS coding in storage systems |
| `Plank2008_Jerasure_Library.pdf` | Plank et al., 2008 | Jerasure: C library for erasure coding | **Essential** — reference implementation architecture |
| `Khan2012_Erasure_Coding_Survey.pdf` | Khan et al., 2012 | Survey of erasure coding for distributed storage | **High** — comprehensive overview of EC landscape |
| `Gopalan2012_LRC_Locality.pdf` | Gopalan et al., 2012 | Locality in codeword symbols (LRC theory) | **High** — theoretical basis for locally repairable codes |
| `Huang2012_LRC_WAS.pdf` | Huang et al., 2012 | LRC in Windows Azure Storage | **High** — practical LRC deployment in production storage |
| `Sathiamoorthy2013_Product_Codes_PIRUMA.pdf` | Sathiamoorthy et al., 2013 | Product code matrices (PIRUMA) for cold storage | **High** — product codes optimized for archival/cold storage |
| `Papailiopoulos2014_LRC_Bounds.pdf` | Papailiopoulos & Dimakis, 2014 | Bounds on locally repairable codes | **Medium** — optimal LRC parameter selection |
| `Muralidhar2014_Facebook_Data_Warehouse.pdf` | Muralidhar et al., 2014 | XOR-based coding at Facebook warehouse scale | **Medium** — practical large-scale erasure coding |
| `Alagappan2018_Erasure_Coding_Practical.pdf` | Alagappan, 2018 | Practical erasure coding considerations | **Medium** — engineering trade-offs in EC systems |
| `Hao2019_LRC_Survey.pdf` | Hao et al., 2019 | Survey on locally repairable codes | **Medium** — comprehensive LRC survey |
| `Surech2017_Erasure_Coding_Distributed_Survey.pdf` | Surech, 2017 | Erasure coding for distributed storage survey | **Medium** — distributed storage EC survey |
| `RFC6330_RaptorQ_Specification.txt` | IETF RFC 6330, 2011 | RaptorQ fountain code specification | **Reference** — potential alternative coding scheme for future exploration |

### Recommended Additional Papers (not yet in repository)

- **Plank & Xu, 2006** — "Optimized Cauchy Reed-Solomon Codes for Erasure-Coded Storage" (IEEE Trans. Computing) — XOR-optimized CRS encoding
- **Luby, 2002** — "LT Codes" (STOC) — Fountain codes for erasure channels
- **Shokrollahi, 2006** — "Raptor Codes" (IEEE Trans. Information Theory) — Efficient fountain codes for broadcast/distribution
- **Weatherspoon & Kubiatowicz, 2002** — "Erasure Coding vs. Replication: A Quantitative Comparison" — When EC beats replication
- **PAR2 Specification** — Parchive parity volume spec — Practical file-level erasure coding format

---

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Erasure code family | Cauchy RS (primary) + LRC (secondary) | Cauchy RS provides XOR-only encoding (fast); LRC reduces repair I/O for partial damage |
| Galois field | GF(2^8) for intra-disc, GF(2^16) for inter-disc | GF(2^8) fits byte-aligned disc I/O; GF(2^16) supports larger stripe counts across discs |
| Encryption | AES-256-GCM | Authenticated encryption prevents tampering; GCM is hardware-accelerated |
| Chunk size | 1 MiB | Balance between granularity of recovery and metadata overhead |
| Disc format | UDF | Blu-ray standard; cross-platform readable; supports large files |
| SIMD | SSE4.2/AVX2/NEON | 10-100x speedup for GF arithmetic; essential for practical encoding speed |
| Recovery manifest replication | 3 copies on disc | Header/metadata is the single point of failure; replication ensures survivability |

---

## Build & Development Notes

### Dependencies (planned)
- C++17 compiler (clang++ / g++)
- Python 3.10+
- CMake 3.20+
- libpthread, libm (standard)
- macOS: CommonCrypto (system), IOKit (disc drive access)
- Linux: OpenSSL (crypto), libcdio (disc access)

### Project Structure (planned)
```
blu-ray_Backup_System/
├── readme.md
├── papers/                    # Reference papers
├── src/
│   ├── libgfarith/           # Galois field arithmetic (C++)
│   ├── liberasure/           # Erasure coding engine (C++)
│   ├── libcrypto_layer/      # Encryption layer (C++)
│   ├── libdiscio/            # Disc I/O management (C++)
│   └── bbackup/              # Python CLI tool
├── tests/                    # Unit and integration tests
├── benchmarks/               # Performance benchmarks
└── docs/                     # Additional documentation
```