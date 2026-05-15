#!/usr/bin/env python3
"""Poll evaluation status until COMPLETED or FAILED."""

import argparse
import os
import sys
import time

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
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--config-filename", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--poll-interval", type=int, default=30)
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(f"USE DATABASE {args.database}")
        cur.execute(f"USE SCHEMA {args.schema}")

        stage_file = f"@{args.stage}/{args.config_filename}"
        elapsed = 0

        while elapsed < args.timeout:
            cur.execute(f"""
                CALL EXECUTE_AI_EVALUATION(
                    'STATUS',
                    OBJECT_CONSTRUCT('run_name', '{args.run_name}'),
                    '{stage_file}'
                )
            """)
            row = cur.fetchone()
            status = row[3] if row else "UNKNOWN"
            details = row[4] if row and len(row) > 4 else ""

            print(f"[{elapsed}s] Status: {status} {details}", file=sys.stderr)

            if status == "COMPLETED":
                print("Evaluation completed successfully", file=sys.stderr)
                return
            elif status == "FAILED":
                print(f"Evaluation FAILED: {details}", file=sys.stderr)
                sys.exit(1)

            time.sleep(args.poll_interval)
            elapsed += args.poll_interval

        print(f"Evaluation timed out after {args.timeout}s", file=sys.stderr)
        sys.exit(1)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
