# Semantic Sequential Circuit Suite

The frozen suite contains **24 SAFE sequential circuits** in **2 semantic families**. Each property compares two meaningful implementations or checks synchronization of duplicated linear state machines.

## Category composition

| Category | Models |
| --- | ---: |
| link-coding | 24 |

## Structural ranges

| Family | Models | Gates min/median/max | Latches min/max | XOR density min/max |
| --- | ---: | ---: | ---: | ---: |
| `crc_frame_align` | 8 | 370/984/2864 | 33/65 | 0.427/0.900 |
| `scrambler_recovery` | 16 | 7/145/769 | 118/175 | 0.833/0.998 |

## Aggregate structure

- Inputs across models: 954
- Latches across models: 2444
- AND/XOR/OR gates: 1560 / 9742 / 1658
- Every model is emitted as both AAG and XOR-preserving BLIF with SHA-256 hashes.
- Structural/hash validation and randomized sequential simulation are performed by `validate_semantic_suite.py`.

## Families

- `crc_frame_align`: serial and parallel CRC state alignment after start-of-frame.
- `scrambler_recovery`: IEEE 802.3 64b/66b self-synchronizing scrambler recovery.
