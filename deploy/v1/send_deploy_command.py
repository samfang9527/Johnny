#!/usr/bin/env python3
"""Dispatch one validated production v1 release through SSM and wait for its result."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import time


def aws(*args: str) -> dict:
    result = subprocess.run(["aws", *args, "--output", "json"], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--release-bucket", required=True)
    parser.add_argument("--backup-bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--mode", required=True, choices=("deploy", "rollback"))
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.sha):
        parser.error("SHA must be a full 40-character commit ID")
    if not re.fullmatch(r"i-[0-9a-f]+", args.instance_id):
        parser.error("Invalid EC2 instance ID")
    for name in (args.release_bucket, args.backup_bucket):
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", name):
            parser.error("Invalid S3 bucket name")

    release_dir = f"/opt/johnny/releases/{args.sha}"
    source = f"s3://{args.release_bucket}/production/v1/{args.sha}/deploy/"
    commands = [
        "set -euo pipefail",
        "mkdir -p " + shlex.quote(release_dir),
        "aws s3 sync " + shlex.quote(source) + " " + shlex.quote(release_dir) + " --region " + shlex.quote(args.region) + " --only-show-errors",
        "bash " + shlex.quote(f"{release_dir}/deploy-host.sh") + " " + " ".join(shlex.quote(value) for value in (args.sha, args.release_bucket, args.backup_bucket, args.region, args.mode)),
    ]
    response = aws(
        "ssm", "send-command", "--region", args.region,
        "--document-name", "AWS-RunShellScript",
        "--instance-ids", args.instance_id,
        "--parameters", json.dumps({"commands": commands, "executionTimeout": ["3600"]}),
        "--timeout-seconds", "3600",
        "--comment", f"{args.mode.title()} Johnny production v1 {args.sha}",
    )
    command_id = response["Command"]["CommandId"]
    print(f"SSM command: {command_id}", flush=True)
    deadline = time.monotonic() + 3700
    while time.monotonic() < deadline:
        try:
            invocation = aws("ssm", "get-command-invocation", "--region", args.region, "--command-id", command_id, "--instance-id", args.instance_id)
        except subprocess.CalledProcessError:
            time.sleep(5)
            continue
        status = invocation["Status"]
        if status == "Success":
            print("Backend deployment succeeded")
            return
        if status in {"Failed", "Cancelled", "TimedOut", "Cancelling"}:
            raise SystemExit(f"Backend deployment failed: {status}; inspect SSM command {command_id}")
        time.sleep(10)
    raise SystemExit(f"Backend deployment timed out; inspect SSM command {command_id}")


if __name__ == "__main__":
    main()
