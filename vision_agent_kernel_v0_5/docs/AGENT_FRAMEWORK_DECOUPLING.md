# Aurora Agent Framework Decoupling

Aurora's target form is not a Genshin-specific automation script and not a
low-cost clone of an end-to-end VLA model. The durable product boundary is:

- **Framework layer:** planning, skill contracts, verification, evidence,
  input safety, repair, benchmark, and package lifecycle.
- **Game capsule layer:** detectors, keymaps, ROI profiles, domain data,
  declarative skills, runtime skills, verifiers, and benchmark tasks for a
  specific game or application.

## Six Implementation Lines

1. **Skill Contract v1**
   A skill is the unit that planners select, verifiers check, recorders produce,
   and repair sessions patch. It must declare capability tags, parameters,
   resource dependencies, verifier contracts, safety policy, cleanup, and
   failure policy. A recorded skill is therefore not just a macro; it is an
   executable, checkable, repairable contract.

2. **Capsule Manifest v1**
   A capsule is an optional capability package. It declares runtime entrypoint,
   slots, detectors, keymaps, skills, resources, profiles, verifiers, bridges,
   and benchmark tasks. Core runtime reads this manifest but does not encode
   game-specific concepts.

3. **Planner To Skill Runtime**
   The planner consumes a unified skill capability catalog built from installed
   capsule manifests and saved SkillDefinitions. It chooses by capability and
   verifier availability, not by hard-coded game names.

4. **Genshin As Optional Capsule**
   Existing Genshin detectors, bridges, skills, profiles, combat YAML, and world
   graph are declared through `capsules/genshin/capsule.yaml`. They remain
   installable without becoming part of core policy.

5. **Skill Recording As Asset Creation**
   Skill recording outputs contracts with resource references and verifier
   expectations. These artifacts can later be moved into a capsule or kept as
   user-local skills.

6. **AuroraBench At Skill/Capsule Level**
   Benchmarks should report capability coverage, verifier coverage, repair
   outcomes, and capsule boundaries. A game-specific improvement belongs in the
   capsule; a generic improvement belongs in the framework.

## Boundary Rules

- `core/`, `execution/`, `planning/`, `repair/`, and `evidence/` must not import
  a game package.
- A game package may import framework contracts and register into StateBus.
- High-frequency input history should be recorded as data artifacts, not
  published wholesale into StateBus.
- 30 Hz motor execution uses lightweight safety invariants; full proof and
  verifier checks happen at skill and mission checkpoints.
- Verifier contracts should combine OCR, templates, state machines, timing, and
  VLM checks where appropriate. A single VLM self-check is not a hard boundary.

## Target Extension Flow

1. Create a new `capsules/<game_id>/capsule.yaml`.
2. Add ROI profiles, keymaps, detectors, and resource files under the capsule or
   referenced data directories.
3. Declare runtime and recorded skills with capabilities and verifier contracts.
4. Install the capsule through `CapsuleRegistry`.
5. Let the planner discover capabilities through `SkillCapabilityCatalog`.
6. Add capsule-specific AuroraBench scenarios without modifying core.
