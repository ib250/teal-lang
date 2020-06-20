"""Teal.

Usage:
  teal [options] asm FILE
  teal [options] ast [-o OUTPUT] FILE
  teal [options] deploy [--config CONFIG]
  teal [options] destroy [--config CONFIG]
  teal [options] invoke [--config CONFIG] [ARG...]
  teal [options] events [--config CONFIG] [--unified | --json] SESSION_ID
  teal [options] logs [--config CONFIG] SESSION_ID
  teal [options] FILE [ARG...]
  teal --version
  teal --help

Commands:
  asm      Compile a file and print the bytecode listing.
  ast      Create a data flow graph (PNG).
  deploy   Deploy to the cloud.
  destroy  Remove cloud deployment.
  invoke   Invoke a teal function in the cloud.
  events   Get events for a session.
  logs     Get logs for a session.
  default  Run a Teal function locally.

Options:
  -h, --help      Show this screen.
  -q, --quiet     Be quiet.
  -v, --verbose   Be verbose.
  -V, --vverbose  Be very verbose.
  --version       Show version.

  -f FUNCTION, --fn=FUNCTION   Function to run      [default: main]
  -s MODE, --storage=MODE      memory | dynamodb    [default: memory]
  -c MODE, --concurrency=MODE  processes | threads  [default: threads]

  -o OUTPUT  Name of the output file

  --config CONFIG  Config file to use  [default: teal.toml]

  -u, --unified  Merge events into one table
  -j, --json     Print as json
"""

# http://try.docopt.org/
#
# - pyfiglet https://github.com/pwaller/pyfiglet
# - typer? https://typer.tiangolo.com/
# - colorama https://pypi.org/project/colorama/

import json
import logging
import pprint
import subprocess
import sys
import time
from pathlib import Path

import colorama

from docopt import docopt

from .. import __version__
from .styling import dim, em
from .ui import configure_logging

LOG = logging.getLogger(__name__)


def _run(args):
    from ..config import load

    cfg = load(config_file=Path(args["--config"]))
    fn = args["--fn"]
    filename = args["FILE"]
    sys.path.append(".")

    fn_args = args["ARG"]

    LOG.info(f"Running `{fn}` in {filename} ({len(fn_args)} args)...")

    if args["--storage"] == "memory":
        if args["--concurrency"] == "processes":
            raise ValueError("Can't use processes with in-memory storage")

        from ..run.local import run_local

        configure_logging(args["--verbose"], args["--vverbose"])

        # NOTE: we use the "lambda" timeout even for local invocations. Maybe
        # there should be a more general timeout
        result = run_local(filename, fn, fn_args, cfg.service.lambda_timeout)
        print(result)

    elif args["--storage"] == "dynamodb":
        from ..run.dynamodb import run_ddb_local, run_ddb_processes

        configure_logging(args["--verbose"], args["--vverbose"])

        if args["--concurrency"] == "processes":
            run_ddb_processes(filename, fn, fn_args)
        else:
            run_ddb_local(filename, fn, fn_args)

    else:
        raise ValueError(args["--storage"])


def _ast(args):
    fn = args["--fn"]
    filename = Path(args["FILE"])

    if args["-o"]:
        dest_png = args["-o"]
    else:
        dest_png = f"{filename.stem}_{fn}.png"
    raise NotImplementedError


def _asm(args):
    from .. import load

    exe = load.compile_file(Path(args["FILE"]))
    print(em("\nBYTECODE:"))
    print(exe.listing())
    print(em("\nBINDINGS:\n"))
    print(exe.bindings_table())
    print()


def timed(fn):
    """Time execution of fn and print it"""

    def _wrapped(args, **kwargs):
        start = time.time()
        fn(args, **kwargs)
        end = time.time()
        if not args["--quiet"]:
            print(f"Done ({int(end-start)}s elapsed).")

    return _wrapped


@timed
def _deploy(args):
    from ..cloud import aws
    from ..config import load

    configure_logging(args["--verbose"], args["--vverbose"])

    cfg = load(
        config_file=Path(args["--config"]), require_dep_id=True, create_dep_id=True,
    )

    # Deploy the infrastructure (idempotent)
    aws.deploy(cfg)
    LOG.info(f"Core infrastructure ready, checking version...")

    api = aws.get_api()

    try:
        logs, response = api.version.invoke(cfg, {})
    except botocore.exceptions.KMSAccessDeniedException:
        print(em("AWS is not ready. Try `teal deploy` again in a few minutes."))
        print("If this persists, please let us know:")
        print("https://github.com/condense9/teal-lang/issues/new")
        return

    print("Teal:", response["body"])

    # Deploy the teal code
    with open(cfg.service.teal_file) as f:
        content = f.read()

    # See teal_lang/executors/awslambda.py
    exe_payload = {"content": content}
    logs, response = api.set_exe.invoke(cfg, exe_payload)
    LOG.info(f"Uploaded {cfg.service.teal_file}")
    print(em(f"Data stored in {cfg.service.data_dir}. `teal invoke` to run main()."))


@timed
def _destroy(args):
    from ..cloud import aws
    from ..config import load

    configure_logging(args["--verbose"], args["--vverbose"])

    cfg = load(config_file=Path(args["--config"]), require_dep_id=True)
    aws.destroy(cfg)
    print(em(f"Done. you can safely `rm -rf {cfg.service.data_dir}`."))


class InvokeError(Exception):
    """Something broke while running"""

    def __init__(self, err, traceback=None):
        self.err = err
        self.traceback = traceback

    def __str__(self):
        res = "\n\n" + em(str(self.err)) + "\n"
        if self.traceback:
            res += "\n" + "".join(self.traceback)
        return res


def _call_cloud_api(function, args, config_file, as_json=True):
    from ..cloud import aws
    from ..config import load

    api = aws.get_api()
    cfg = load(config_file=config_file, require_dep_id=True)

    # See teal_lang/executors/awslambda.py
    LOG.debug("Calling Teal cloud: %s %s", function, args)
    logs, response = getattr(api, function).invoke(cfg, args)
    LOG.info(logs)

    # This is when there's an unhandled exception in the Lambda.
    if "errorMessage" in response:
        msg = (
            "Teal Bug! Please report this! "
            + "https://github.com/condense9/teal-lang/issues/new \n\n"
            + response["errorMessage"]
        )
        raise InvokeError(msg, response["stackTrace"])

    code = response.get("statusCode", None)
    if code == 400:
        # This is when there's a (handled) error
        print("Error! (statusCode: 400)\n")
        err = json.loads(response["body"])
        raise InvokeError(err.get("message", err), err.get("traceback", None))

    if code != 200:
        raise ValueError(f"Unexpected response code: {code}")

    body = json.loads(response["body"]) if as_json else response["body"]
    LOG.info(body)

    return body


@timed
def _invoke(args):
    from ..config import load

    cfg = load(config_file=Path(args["--config"]))
    payload = {
        "function": args["--fn"],
        "args": args["ARG"],
        "timeout": cfg.service.lambda_timeout,
    }
    data = _call_cloud_api("new", payload, Path(args["--config"]))

    session_id = data["session_id"]
    last_session_file = cfg.service.data_dir / "last_session_id.txt"
    with open(last_session_file, "w") as f:
        LOG.info("Session ID: %s (saved in %s)", session_id, last_session_file)
        f.write(session_id)

    print(data["result"])


@timed
def _events(args):
    from ..executors import awslambda

    data = _call_cloud_api(
        "get_events", {"session_id": args["SESSION_ID"]}, Path(args["--config"]),
    )
    if args["--unified"]:
        awslambda.print_events_unified(data)
    elif args["--json"]:
        print(json.dumps(data, indent=2))
    else:
        awslambda.print_events_by_machine(data)


@timed
def _logs(args):
    from ..executors import awslambda

    data = _call_cloud_api(
        "get_output", {"session_id": args["SESSION_ID"]}, Path(args["--config"]),
    )
    awslambda.print_outputs(data)


def main():
    colorama.init()
    args = docopt(__doc__, version=__version__)
    LOG.debug("CLI args: %s", args)

    if args["ast"]:
        _ast(args)
    elif args["asm"]:
        _asm(args)
    elif args["deploy"]:
        _deploy(args)
    elif args["destroy"]:
        _destroy(args)
    elif args["invoke"]:
        _invoke(args)
    elif args["events"]:
        _events(args)
    elif args["logs"]:
        _logs(args)
    elif args["FILE"] and args["FILE"].endswith(".tl"):
        _run(args)
    else:
        print(em("Invalid command line.\n"))
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
