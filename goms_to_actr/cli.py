import argparse
import json
from pathlib import Path
import sys
from . import ModelError, compile_model, load, simulate


def main(argv=None):
    parser = argparse.ArgumentParser(description='Convert GOMS JSON or NGOMSL to ACT-R 7 Lisp')
    parser.add_argument('command', choices=['compile', 'validate', 'simulate'])
    parser.add_argument('input', type=Path)
    parser.add_argument('--format', choices=['json', 'ngomsl'],
                        help='input format (default: NGOMSL for .ngomsl files, otherwise JSON)')
    parser.add_argument('-o', '--output', type=Path, help='output file (compile only; default stdout)')
    args = parser.parse_args(argv)
    if args.output and args.command != 'compile':
        parser.error('--output is only supported with compile')
    if args.output and args.output.resolve() == args.input.resolve():
        parser.error('output must differ from input')
    try:
        model = load(args.input, format=args.format)
        if args.command == 'compile':
            result = compile_model(model)
            if args.output:
                args.output.write_text(result, encoding='utf-8')
            else:
                sys.stdout.write(result)
        elif args.command == 'validate':
            print(f'Valid GOMS v1 model: {model["name"]}')
        else:
            result = simulate(model)
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result['status'] == 'done' else 1
        return 0
    except (ModelError, OSError, UnicodeError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
