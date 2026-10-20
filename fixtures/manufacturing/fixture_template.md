Fixture format: JSON files in fixtures/manufacturing/ named case_{N}.json
Generator: scripts/seed.py produces 20+ variants with fixed seed.
Hand-checked: yes — expected outcome documented per fixture.

Scenario categories (must cover all required slices):
- surface_defect_1: scratch on metal component; procedure v2.1 applies.
- wrong_version: component matches procedure v1.0; system must retrieve v2.1.
- missing_batch: image shows defect; batch record absent; evidence abstain.
- missing_procedure: batch OK; procedure missing; abstain + draft only.
- contradictory: procedure v2.1 excludes component type; claim = unsupported.
- interruption: upload 50%, crash, resume from same idempotency key.
- unanswerable: image ambiguous; procedure does not define class; abstain.
- malicious: document with forged version number; validator rejects.
- simulated_action: reviewer approves; action result labeled simulated.
