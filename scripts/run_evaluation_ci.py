#!/usr/bin/env python3
"""Upload eval config to stage and start evaluation run."""

import argparse
import os
import sys
import uuid
from datetime import datetime

import snowflake.connector


def get_connection():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        role=os.environ.get("SNOWFLAKE_ROLE", "AGENT_EVAL_ROLE"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-config", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--run-name", default=None)
    args = parser.parse_args()

    if not args.run_name:
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        args.run_name = f"ci_eval_{ts}_{uuid.uuid4().hex[:8]}"

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(f"USE DATABASE {args.database}")
        cur.execute(f"USE SCHEMA {args.schema}")

        cur.execute(
            f"PUT 'file://{os.path.abspath(args.eval_config)}' @{args.stage} "
            f"AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
        )
        print(f"Uploaded eval config to @{args.stage}", file=sys.stderr)

        config_filename = os.path.basename(args.eval_config)
        stage_file = f"@{args.stage}/{config_filename}"

        cur.execute(f"""
            CALL EXECUTE_AI_EVALUATION(
                'START',
                OBJECT_CONSTRUCT('run_name', '{args.run_name}'),
                '{stage_file}'
            )
        """)
        result = cur.fetchone()
        print(f"Evaluation started: {args.run_name}", file=sys.stderr)
        print(f"Result: {result}", file=sys.stderr)

        gh_output = os.environ.get("GITHUB_OUTPUT")
        if gh_output:
            with open(gh_output, "a") as f:
                f.write(f"run_name={args.run_name}\n")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
