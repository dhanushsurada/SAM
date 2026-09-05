"""
SAM Sovereign Workbench (SIH26117).

Local-first agentic document workflows built as an additive capability
layer on top of the existing SAM core (agent/, core/, memory/) — see
SIH26117_Repository_Audit.md for the full audit and milestone plan.

Nothing in this package talks to the network except through the same
local Ollama host the rest of SAM already uses (settings.ollama_host).
"""
