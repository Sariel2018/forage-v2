# Forage

**Autonomous Data Collection that Discovers What "Complete" Means**

[![Paper](https://img.shields.io/badge/arXiv-Forage-b31b1b.svg)](https://arxiv.org/abs/TODO)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Forage is a human-not-in-the-loop data collection harness in which the evaluation criteria *co-evolve* with the collection strategy. An independent **Evaluator Agent** discovers and iteratively refines the definition of completeness (the denominator), while an architecturally isolated **Planner Agent** optimizes collection (the numerator).

> Agents without independent evaluation exhibit coverage gaps of up to **+84 percentage points** (self-reporting 100% at 15.9% actual recall). Full Forage achieves the highest absolute recall (**98.8%** and **74.8%**) with the most calibrated self-assessment.

## The Problem: Denominator Blindness

When agents evaluate their own progress, they don't know what they don't know. A single agent might collect 2,000 records, self-report "100% coverage," and stop --- when the true total is 27,000. We call this **denominator blindness**: high self-reported coverage + wrong denominator = confidently incomplete.

| | Self-reported coverage | Actual recall | Cost |
|--|:-:|:-:|:-:|
| Single Agent (SA) | "unknown" | 15.9--94.5% | $1.6--37.3 |
| **Forage (M)** | **97--99%** | **74.8--98.8%** | **$3.5--4.8** |

Denominator blindness is not specific to data collection --- it applies to any autonomous agent operating in open-ended task spaces where the boundary of "done" must be discovered.

## Key Idea: Co-Evolving Evaluation

Existing systems (AutoML, AI-Scientist, autoresearch) use **fixed evaluation criteria**. Forage's evaluation criteria **evolve during execution**:

```
Round 1:  denominator = 308   (initial sitemap scan)
Round 2:  denominator = 551   (discovered broader index, overcounted)
Round 3:  denominator = 296   (excluded non-target content)
Round 4:  denominator = 295   (converged to ground truth)
```

This is possible because of **method isolation**: the Evaluator and Planner cannot see each other's code, preventing cognitive anchoring and enabling independent exploration.

## Architecture

```
Task Spec (YAML)
      |
      v
+-----------+     gaps + discovery     +----------+
| Evaluator |  ------------------->    | Planner  |
|   Agent   |     (not methods)        |  Agent   |
|  (LLM)    |                         |  (LLM)   |
+-----+-----+    METHOD ISOLATION     +----+-----+
      |           (code hidden)             |
      v                                     v
  eval.py                              collect.py
      |                                     |
      v                                     v
  Deterministic     <--- dataset/ ---   Executor
  Evaluation                          (deterministic)
      |
      v
  metrics.json  -----> reads ------> Planner
      |
      v
   Stop? ---yes---> Output (Dataset + Metrics + Gap Report)
    |
    no (continue, next round)
```

**Four layers of independence:**
1. **Method isolation** --- each agent's code is hidden from the other
2. **Context isolation** --- separate LLM calls, no shared reasoning
3. **Temporal separation** --- Evaluator defines the standard before Planner executes
4. **External anchoring** --- denominator grounded in verifiable external sources

## Results

Six-group ablation study across two benchmarks:

### WhiteHouse.gov Announcements (GT = 1,695)

| Group | Recall | Precision | F1 | Cost | Gap |
|-------|:------:|:---------:|:--:|:----:|:---:|
| **M (Forage)** | **98.8%** | **100.0%** | **99.4%** | $4.79 | -1pp |
| M-no-iso | 97.7% | 99.8% | 98.7% | $4.16 | +2pp |
| SA (baseline) | 94.5% | 100.0% | 97.1% | $20.21 | N/A |
| M-no-eval | 78.9% | 97.8% | 84.8% | $4.91 | +21pp |
| M-co-eval | 68.2% | 99.9% | 78.1% | $2.93 | +32pp |
| M-exp | 30.2% | 95.3% | 45.8% | $7.72 | +70pp |

### Foreign Affairs Archive (GT = 295)

| Group | Recall | Precision | F1 | Cost | Gap |
|-------|:------:|:---------:|:--:|:----:|:---:|
| **M (Forage)** | **50.4%** | **69.5%** | **56.2%** | $3.51 | +21pp |
| M-no-iso | 48.9% | 61.7% | 46.3% | $4.03 | +40pp |
| M-exp | 47.7% | 49.5% | 47.7% | $3.89 | +28pp |
| M-no-eval | 45.9% | 33.3% | 36.3% | $4.32 | +54pp |
| M-co-eval | 36.8% | 53.4% | 43.0% | $2.38 | +44pp |
| SA (baseline) | 34.1% | 27.1% | 30.2% | $20.53 | N/A |

**Key findings:**
- Method isolation alone accounts for a **+25.9pp** recall improvement on the harder benchmark
- Agents without independent evaluation suffer from denominator blindness (coverage gap up to +84pp)
- Forage costs **3--4x less** than single-agent baselines

## Installation

```bash
git clone https://github.com/Sariel2018/forage.git
cd forage
pip install -e .
```

### Prerequisites

- Python >= 3.11
- [Claude Code CLI](https://claude.ai/code) installed and authenticated (used as the LLM runtime)

## Usage

```bash
# Single run
forage run tasks/whitehouse_trump2.yaml --knowledge knowledge/

# Ablation experiment (multiple groups, 3 repeats each)
forage experiment tasks/whitehouse_trump2.yaml \
    --groups SA,M-exp,M,M-co-eval --repeats 3 --knowledge knowledge/
```

## Task Specification

Tasks are defined in YAML:

```yaml
task:
  name: "whitehouse_trump2"
  description: "Collect all White House announcements since Trump's 2nd inauguration"

target:
  topic: "White House presidential announcements and statements"
  time_range:
    start: "2025-01-20"
    end: "2026-04-01"

coverage:
  mode: "hard"
  target: 0.95

budget:
  max_rounds: 8
  max_runtime_minutes: 120
```

## Project Structure

```
forage/             # Core Python package
  core/             #   Outer loop, spec parser, tool definitions
  agents/           #   Evaluator, Planner, Executor agents
  experiments/      #   Experiment runner, single-agent baseline
tasks/              # Task specification YAML files
knowledge/          # Experience knowledge base (web scraping tips)
scripts/            # Analysis scripts (recall, figures)
tests/              # Unit tests
```

## Beyond Data Collection

Denominator blindness applies to any task where "done" is unknown at the start:

| Task | The denominator problem |
|------|----------------------|
| Data collection | "All articles" --- how many exist? |
| Systematic review | "All relevant papers" --- how many are there? |
| Security audit | "All vulnerabilities" --- how many exist? |
| Knowledge graph | "All entities" --- how many are there? |

Forage provides a general architecture for these tasks. Data collection is the case study in this paper.

## Citation

```bibtex
@article{xie2026forage,
  title={Forage: Solving Denominator Blindness in Autonomous Agents via Co-Evolving Evaluation},
  author={Xie, Huaqing},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2026}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
