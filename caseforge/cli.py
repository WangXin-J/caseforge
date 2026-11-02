"""命令行入口：caseforge run <用例路径> --base-url <地址>"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .loader import CaseFormatError, load_cases
from .report import summary, to_console, to_json, to_junit
from .runner import run_suite


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="caseforge", description="声明式接口用例执行引擎")
    parser.add_argument("--version", action="version", version=f"caseforge {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="执行用例")
    run.add_argument("path", help="用例文件或目录")
    run.add_argument("--base-url", required=True, help="被测服务地址，如 http://127.0.0.1:8010")
    run.add_argument("--workers", type=int, default=1, help="并发用例数（默认 1）")
    run.add_argument("--tag", action="append", default=[], help="只执行带指定 tag 的用例，可重复")
    run.add_argument("--json", dest="json_out", help="把结果写成 JSON")
    run.add_argument("--junit", dest="junit_out", help="把结果写成 JUnit XML（给 CI 用）")
    run.add_argument("--env", action="append", default=[], metavar="KEY=VALUE", help="注入全局变量")
    run.add_argument("-q", "--quiet", action="store_true", help="只输出汇总")

    serve = sub.add_parser("serve", help="启动执行看板（需要额外安装 .[web]）")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--db", default="report/caseforge.db", help="SQLite 路径")
    serve.add_argument("--cases", default="examples/cases", help="用例目录")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "serve":
        try:
            import uvicorn
        except ImportError:
            print('启动看板需要先安装: pip install -e ".[web]"', file=sys.stderr)
            return 2
        from .web import create_app

        print(f"CaseForge 看板: http://{args.host}:{args.port}")
        uvicorn.run(create_app(args.db, args.cases), host=args.host, port=args.port)
        return 0

    if args.command != "run":
        return 2

    try:
        cases = load_cases(args.path)
    except CaseFormatError as exc:
        print(f"用例格式错误: {exc}", file=sys.stderr)
        return 2

    if args.tag:
        wanted = set(args.tag)
        cases = [c for c in cases if wanted & set(c.tags)]
        if not cases:
            print(f"没有匹配 tag {args.tag} 的用例", file=sys.stderr)
            return 2

    env: dict[str, str] = {}
    for item in args.env:
        key, _, value = item.partition("=")
        if not key:
            print(f"--env 格式错误: {item}", file=sys.stderr)
            return 2
        env[key] = value

    results = run_suite(cases, args.base_url, env=env, workers=max(1, args.workers))

    print(to_console(results, verbose=not args.quiet))

    if args.json_out:
        Path(args.json_out).write_text(to_json(results), encoding="utf-8")
    if args.junit_out:
        Path(args.junit_out).write_text(to_junit(results), encoding="utf-8")

    return 0 if summary(results)["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
