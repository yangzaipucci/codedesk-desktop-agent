"""Teacher's stable per-section JSON acceptance CLI."""
import argparse
import asyncio
import json
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m app.inspect')
    parser.add_argument('section', choices=['skills', 'custom', 'daemon'])
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    from agent.course_inspection import inspect_section
    try:
        report = asyncio.run(inspect_section(args.section, args.out))
    except Exception as error:
        from agent.capabilities import atomic_json
        report = {'passed': False, 'error': str(error)[:1000]}
        atomic_json(args.out, report)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get('passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
