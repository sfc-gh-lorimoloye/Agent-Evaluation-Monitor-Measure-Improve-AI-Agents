#!/usr/bin/env python3
"""Rollback: reassign production alias to previous version."""

import argparse
import os
import sys

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
    parser.add_argument("--database", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--agent-name", required=True)
    parser.add_argument("--target-version", default=None, help="Version to rollback to (default: second-to-last)")
    args = parser.parse_args()

    fqn = f"{args.database}.{args.schema}.{args.agent_name}"
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(f"USE DATABASE {args.database}")
        cur.execute(f"USE SCHEMA {args.schema}")

        cur.execute(f"SHOW VERSIONS IN AGENT {fqn}")
        versions = [row for row in cur.fetchall()]

        if args.target_version:
            rollback_version = args.target_version
        elif len(versions) >= 2:
            rollback_version = versions[-2][0]
        else:
            print("No previous version available for rollback", file=sys.stderr)
            sys.exit(1)

        cur.execute(f"ALTER AGENT {fqn} MODIFY VERSION {rollback_version} SET ALIAS = production")
        cur.execute(f"ALTER AGENT {fqn} SET DEFAULT_VERSION = '{rollback_version}'")
        print(f"Rolled back to {rollback_version}", file=sys.stderr)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
