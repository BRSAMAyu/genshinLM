# Open Beta

Open beta support is local-first.

## Benchmark

`open_beta/benchmark_suite.py` summarizes:

- task completion rate
- skill success rate
- verifier accuracy
- target lost count
- recovery success rate
- combat survival time
- collection success rate
- user intervention count
- mean time to complete

## Workshop

`open_beta/skill_workshop.py` validates Skill/Profile/Playbook/Persona blueprints before import.

## Feedback Package

`open_beta/feedback_package.py` creates a local feedback bundle with redacted logs and no automatic upload.
