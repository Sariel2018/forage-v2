"""Forage CLI entry point.

Usage:
    python -m forage run tasks/fa_2018_2020.yaml
    python -m forage run tasks/whitehouse_trump2.yaml --knowledge knowledge/
    python -m forage experiment tasks/fa_2018_2020.yaml --groups B1,M-exp,M --repeats 3
    python -m forage learn tasks/fa_2018_2020.yaml --group M+ --num-runs 6
"""

import argparse
import sys

from .core.spec import TaskSpec
from .core.loop import run
from .experiments.runner import run_experiment


def main():
    parser = argparse.ArgumentParser(
        prog="forage",
        description="Autonomous data collection that discovers what 'complete' means",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- forage run ---
    run_parser = subparsers.add_parser("run", help="Run a single Forage task")
    run_parser.add_argument("spec", help="Path to task spec YAML")
    run_parser.add_argument("--output", default="output", help="Output directory")
    run_parser.add_argument("--knowledge", default=None, help="Path to knowledge directory")

    # --- forage experiment ---
    exp_parser = subparsers.add_parser("experiment", help="Run comparative experiments")
    exp_parser.add_argument("spec", help="Path to task spec YAML")
    exp_parser.add_argument(
        "--groups",
        default="SA,M-no-eval,M-no-iso,M-co-eval,M-exp,M",
        help="Comma-separated experiment groups (default: SA,M-no-eval,M-no-iso,M-co-eval,M-exp,M)",
    )
    exp_parser.add_argument("--repeats", type=int, default=3, help="Repeats per group (default: 3)")
    exp_parser.add_argument("--output", default="experiments", help="Experiments output directory")
    exp_parser.add_argument("--knowledge", default=None, help="Path to knowledge directory")
    exp_parser.add_argument("--parallel", action="store_true", help="Run groups in parallel")

    # --- forage learn ---
    learn_parser = subparsers.add_parser("learn", help="Run learning curve experiment")
    learn_parser.add_argument("spec", help="Path to task spec YAML")
    learn_parser.add_argument("--num-runs", type=int, default=6, help="Number of sequential runs (default: 6)")
    learn_parser.add_argument("--output", default="experiments", help="Output directory")
    learn_parser.add_argument("--knowledge", default=None, help="Knowledge directory (for M group)")
    learn_parser.add_argument("--group", default="M+", choices=["M+", "M", "M-exp"],
                              help="Experiment group (default: M+)")

    args = parser.parse_args()

    if args.command == "run":
        spec = TaskSpec.from_yaml(args.spec)
        run(spec, output_dir=args.output, knowledge_dir=args.knowledge)

    elif args.command == "experiment":
        spec = TaskSpec.from_yaml(args.spec)
        groups = [g.strip() for g in args.groups.split(",")]
        run_experiment(
            spec=spec,
            groups=groups,
            repeats=args.repeats,
            output_dir=args.output,
            knowledge_dir=args.knowledge,
            parallel=args.parallel,
        )

    elif args.command == "learn":
        spec = TaskSpec.from_yaml(args.spec)
        from .experiments.learning_curve import run_learning_curve
        run_learning_curve(
            spec=spec,
            num_runs=args.num_runs,
            output_dir=args.output,
            knowledge_dir=args.knowledge,
            group=args.group,
        )

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
