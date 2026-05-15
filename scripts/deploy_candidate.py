#!/usr/bin/env python3
"""Deploy candidate agent spec using ALTER AGENT (preserves eval history)."""

import argparse
import json
import os
import sys

import snowflake.connector
import yaml


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
    parser.add_argument("--agent-spec", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--agent-name", required=True)
    args = parser.parse_args()

    with open(args.agent_spec) as f:
        spec = yaml.safe_load(f)

    spec_json = json.dumps(spec, indent=2)
    fqn = f"{args.database}.{args.schema}.{args.agent_name}"

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(f"USE DATABASE {args.database}")
        cur.execute(f"USE SCHEMA {args.schema}")

        cur.execute(f"SHOW VERSIONS IN AGENT {fqn}")
        versions_before = [row[0] for row in cur.fetchall()]

        cur.execute(f"ALTER AGENT {fqn} ADD LIVE VERSION FROM LAST")

        alter_sql = f"""ALTER AGENT {fqn} SET SPEC = $${spec_json}$$"""
        cur.execute(alter_sql)

        cur.execute(f"ALTER AGENT {fqn} COMMIT COMMENT = 'CI deploy - run {os.environ.get('GITHUB_RUN_NUMBER', 'local')}'")

        cur.execute(f"SHOW VERSIONS IN AGENT {fqn}")
        versions_after = [row[0] for row in cur.fetchall()]
        new_versions = set(versions_after) - set(versions_before)
        version_name = new_versions.pop() if new_versions else "LAST"

        cur.execute(f"ALTER AGENT {fqn} MODIFY VERSION {version_name} SET ALIAS = staging")

        print(f"Deployed {version_name} with staging alias", file=sys.stderr)

        gh_output = os.environ.get("GITHUB_OUTPUT")
        if gh_output:
            with open(gh_output, "a") as f:
                f.write(f"version_name={version_name}\n")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
