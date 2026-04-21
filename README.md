<p align="center">
  <img src="assets/logo.png" alt="Forage" width="280">
</p>

<h3 align="center">Your basecamp for the unknown.</h3>

<p align="center">
  An autonomous agent architecture that accumulates and transfers experience<br>
  across runs, models, and task types.
</p>

---

## The problem

You ask an AI agent to do an open-ended task. It works for a while, declares victory, reports 100% complete. It found 15% of what exists.

[Forage V1](https://github.com/Sariel2018/forage) solved this for single runs — splitting execution and evaluation into two isolated agents so neither can grade its own work. V1 called the problem **denominator blindness** and achieved 98.8% actual recall where a single agent stopped at 15.9%.

But V1 teams start from scratch every time. Hard-won discoveries about the territory are lost between expeditions.

## V2: The organization remembers

Forage V2 extends the architecture from a single expedition to a **learning organization**. After each run, both agents independently write down what they learned. The next team reads the notebook before heading out.

Over six runs, the organization accumulates 54 knowledge entries — which sources are reliable, what pitfalls exist, how the domain is structured. A weaker model (Sonnet), given a stronger model's (Opus) accumulated knowledge:

- **Closes a 6.6pp coverage gap to 1.1pp**
- **Halves the cost** ($9.40 → $5.13)
- **Converges in half the rounds** (mean 4.5 vs 7.0)
- Three independent runs arrive at **exactly the same answer** (266 products)

The knowledge didn't make Sonnet smarter. It made Sonnet *not waste time rediscovering what Opus already knew*.

## How it works

Two agents. One **explores** (the Planner), one **maps** (the Evaluator). They can't see each other's code — like an auditor who can't read the books they're auditing. The Evaluator doesn't check against a pre-written rubric. It *discovers* what "complete" means by independently exploring the problem space. Both evolve together.

V2 adds three things:
- **Knowledge evolution** — post-mortem lessons accumulate across runs as organizational memory
- **Knowledge transfer** — a new agent (any model, any provider) inherits the organization's experience on day one
- **Hardened isolation** — physical workspace separation, after we caught an agent peeking at the other's code

## The vision

<p align="center">
  <img src="assets/ui_vision.png" alt="Forage Basecamp UI" width="700">
  <br>
  <em>What the basecamp will look like — expedition management, team roster, knowledge assets.</em>
</p>

```
V1  Expedition     →  Two agents establish credible judgment
V2  Organization   →  Experience accumulates and transfers         ← you are here
V3  Basecamp       →  A camp manager allocates resources dynamically
V4  Highway        →  Verified routes crystallize into reusable pipelines
```

## Papers

- **V2**: Knowledge Evolution and Transfer in Autonomous Agent Organizations — [arXiv (coming soon)]()
- **V1**: Solving Denominator Blindness via Co-Evolving Evaluation — [arXiv (coming soon)]() | [code](https://github.com/Sariel2018/forage)

## Status

The V2 paper has been submitted to arXiv. The codebase is a research prototype under active development — isolation, recovery, and visualization are being hardened. Code will be released when ready.

## Citation

```bibtex
@article{foragev2,
    title={Forage V2: Knowledge Evolution and Transfer
           in Autonomous Agent Organizations},
    author={Xie, Huaqing},
    journal={arXiv preprint},
    year={2026}
}
```

## License

Apache 2.0
