# vivo/iQOO Bridge — reserved for verified ecosystem integration

This directory is a documentation boundary only. It intentionally contains
no code.

## Why it's empty

As of Phase 3A.5, nothing in this codebase talks to a vivo/iQOO SDK,
Office Kit API, or any vendor-specific transport. `docs/iqoo/OFFICE_KIT.md`
states this explicitly: SAM does not implement, replace, or bypass Office
Kit. Everything that was previously under `iqoo/` was generic HTTP+SSE
functionality with zero vendor dependency — it was audited file-by-file
during this migration and relocated to `multimodal/` and `interfaces/api/`
accordingly. There was nothing left over that was genuinely vivo/iQOO-specific.

Building placeholder SDK bindings, fake Office Kit calls, or simulated
hardware integration here — just to fill this folder — was explicitly out
of scope for this migration and would misrepresent what's actually
implemented.

## What belongs here, once it exists

Real, verified vivo/iQOO-specific integration code: vendor SDK bindings,
authenticated Office Kit API calls, or any other logic that genuinely
cannot run without vivo/iQOO-provided software or hardware.

## The intended shape

Per the SAM Connect architecture, SAM Core never talks to this bridge
directly. The path is:

```
SAM Core -> SAM Connect contract (capability, e.g. FILE_TRANSFER)
         -> SAM Connect routes to an available transport/bridge
         -> connect/bridges/vivo_iqoo/ (this directory, once populated)
```

So that Samsung, Xiaomi, or any future ecosystem can be added the same way,
without touching SAM's Brain, Memory, Agent, Planner, Reflection, or
Verification systems.

See `docs/iqoo/PHASE_3A5_MIGRATION.md` for the full audit that led to this
directory being a stub, and `docs/iqoo/OFFICE_KIT.md` for why today's phone
connectivity is same-WiFi HTTP, not an Office Kit integration.
