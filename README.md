<p align="center">
  <img src="assets/logo.png" width="400" alt="Forage">
</p>

<h3 align="center">How can an autonomous agent know it's done — when "done" itself must be discovered?</h3>

<p align="center">
  <a href="https://arxiv.org/abs/TODO"><img src="https://img.shields.io/badge/arXiv-Forage-b31b1b.svg" alt="Paper"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

Most agent frameworks assume a pre-defined goal. But the real world is full of tasks where "done" is unknown at the start:

- A data collection agent told to "get all articles" doesn't know how many articles exist.
- An AI scientist exploring a chemical space doesn't know how many compounds have the desired property.  
- A security auditor doesn't know how many vulnerabilities exist in the system.
- A literature reviewer doesn't know how many relevant papers are out there.

In each case, the agent collects some results, declares victory, and stops --- often at single-digit completeness while self-reporting 100%. We call this **denominator blindness**: the agent confidently answers a question it was never equipped to ask --- *"how much is left?"*

Forage solves this with one architectural principle: **separate the agent that defines success from the agent that pursues it.** No human specifies the evaluation criteria. No human decides when to stop. No human intervenes at any point. The system autonomously discovers what "complete" means, verifies its own progress, and terminates when the goal is met --- or honestly reports what's missing when it isn't.

The name draws from Optimal Foraging Theory in ecology: like animals foraging in an unknown environment under energy budgets, Forage operates without knowing the total resource pool, iteratively refining its estimate of the world's boundaries.

<p align="center">
  <img src="assets/architecture.png" width="700" alt="Forage Architecture">
</p>

## Why This Matters

Current AI systems --- AutoML, AI-Scientist, autoresearch --- all use **fixed evaluation criteria** defined by humans before execution. This works when the goal is known. But when the goal space is open-ended, fixed evaluation becomes the bottleneck: the agent literally cannot know what it doesn't know.

Forage makes evaluation criteria **co-evolve** with the task:

<p align="center">
  <img src="assets/co_evolution_case.png" width="550" alt="Denominator Co-Evolution">
  <br>
  <em>The Evaluator's denominator estimate evolves across rounds: 308 → 551 → 296 → 295 (ground truth). No human intervention.</em>
</p>

This is an epistemological question that pervades autonomous AI: **how can an agent establish reliable knowledge about the boundaries of what it does not know?** Data collection is our case study because completeness is quantitatively verifiable, but the principle applies to any domain where "done" is unknown at the start.

## Results

In a 6-group ablation across two benchmarks:

<p align="center">
  <img src="assets/denominator_blindness.png" width="550" alt="Denominator Blindness">
  <br>
  <em>Without independent evaluation, agents self-report 100% at 15.9% actual recall (coverage gap: +84pp).</em>
</p>

- **Denominator blindness is real**: self-evaluating agents average +54pp coverage gap
- **Architectural separation works**: method isolation alone gives +25.9pp recall on the harder benchmark  
- **Forage is calibrated**: coverage gap of only -3pp (slightly conservative)
- **Forage is efficient**: 3--4x cheaper than single-agent baselines

Full results in the [paper](https://arxiv.org/abs/TODO).

## How It Works

Each round:

1. **Evaluator Agent** (LLM) explores data sources, defines the denominator, writes `eval.py`
2. **Planner Agent** (LLM) reads coverage gaps, designs strategy, writes `collect.py`  
3. **Executor** (deterministic) runs `collect.py`, then runs `eval.py` on the dataset
4. **Stop?** Continue if coverage insufficient; stop when converged or budget exhausted

The key constraint: **the Evaluator never sees `collect.py`, and the Planner never sees `eval.py`.** This method isolation prevents cognitive anchoring --- the same reason you don't let developers test their own code.

## Quick Start

```bash
git clone https://github.com/Sariel2018/forage.git
cd forage
pip install -e .

# Requires Claude Code CLI: https://claude.ai/code
forage run tasks/whitehouse_trump2.yaml --knowledge knowledge/
```

## Running Experiments

```bash
# 6-group ablation with 3 repeats
forage experiment tasks/fa_2011.yaml \
    --groups SA,M-no-eval,M-no-iso,M-co-eval,M-exp,M \
    --repeats 3 --knowledge knowledge/
```

## Project Structure

```
forage/             # Core package
  agents/           #   Evaluator, Planner, Executor
  core/             #   Outer loop, spec parser
  experiments/      #   Experiment runner
tasks/              # Task specs (YAML)
knowledge/          # Experience knowledge base
scripts/            # Analysis & figure generation
tests/              # Tests
```

## Citation

```bibtex
@article{xie2026forage,
  title={Forage: Solving Denominator Blindness in Autonomous Agents 
         via Co-Evolving Evaluation},
  author={Xie, Huaqing},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2026}
}
```

## What's Next

**v2 in progress**: extending Forage with cross-task knowledge accumulation.

## License

[MIT](LICENSE)

---

If you find this work useful, please consider giving it a star and citing our paper.
