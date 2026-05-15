#!/usr/bin/env python3
"""Promote the latest committed version to production alias."""

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
    parser.add_argument("--alias", default="production")
    parser.add_argument("--version", default=None, help="Specific version to promote (default: LAST)")
    args = parser.parse_args()

    fqn = f"{args.database}.{args.schema}.{args.agent_name}"
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(f"USE DATABASE {args.database}")
        cur.execute(f"USE SCHEMA {args.schema}")

        if args.version:
            version = args.version
        else:
            cur.execute(f"SHOW VERSIONS IN AGENT {fqn}")
            versions = cur.fetchall()
            version = versions[-1][0] if versions else "LAST"

        cur.execute(f"ALTER AGENT {fqn} MODIFY VERSION {version} SET ALIAS = {args.alias}")
        print(f"Promoted {version} → {args.alias}", file=sys.stderr)

        cur.execute(f"ALTER AGENT {fqn} SET DEFAULT_VERSION = '{version}'")
        print(f"Set DEFAULT_VERSION = {version}", file=sys.stderr)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
