#!/usr/bin/env python3
"""Quality gate: check evaluation metrics against thresholds."""

import argparse
import json
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
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--answer-correctness-threshold", type=float, default=0.75)
    parser.add_argument("--logical-consistency-threshold", type=float, default=0.80)
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute(f"""
            SELECT METRIC_NAME, ROUND(AVG(EVAL_AGG_SCORE), 4) AS AVG_SCORE, COUNT(*) AS NUM_RECORDS
            FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
                '{args.database}', '{args.schema}', '{args.agent_name}',
                'CORTEX AGENT', '{args.run_name}'
            ))
            GROUP BY METRIC_NAME
            ORDER BY METRIC_NAME
        """)

        results = {}
        for row in cur.fetchall():
            results[row[0]] = {"avg_score": float(row[1]), "num_records": int(row[2])}

        thresholds = {
            "answer_correctness": args.answer_correctness_threshold,
            "logical_consistency": args.logical_consistency_threshold,
        }

        passed = True
        lines = ["## Agent Evaluation Results\n"]
        lines.append(f"**Run:** `{args.run_name}`\n")
        lines.append(f"**Agent:** `{args.database}.{args.schema}.{args.agent_name}`\n")
        lines.append("| Metric | Score | Threshold | Status |")
        lines.append("|--------|-------|-----------|--------|")

        for metric, data in sorted(results.items()):
            threshold = thresholds.get(metric)
            score = data["avg_score"]
            if threshold is not None:
                status = "✅ PASS" if score >= threshold else "❌ FAIL"
                if score < threshold:
                    passed = False
                lines.append(f"| {metric} | {score:.4f} | {threshold:.2f} | {status} |")
            else:
                lines.append(f"| {metric} | {score:.4f} | — | ℹ️ Info |")

        lines.append("")
        lines.append(f"**Overall: {'✅ PASSED' if passed else '❌ FAILED'}**")

        if not passed:
            lines.append("")
            lines.append("### Failed Metrics Detail")
            lines.append("")

            cur.execute(f"""
                SELECT INPUT, METRIC_NAME, ROUND(EVAL_AGG_SCORE, 4) AS SCORE,
                       LEFT(OUTPUT, 300) AS OUTPUT_PREVIEW
                FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
                    '{args.database}', '{args.schema}', '{args.agent_name}',
                    'CORTEX AGENT', '{args.run_name}'
                ))
                WHERE EVAL_AGG_SCORE < 0.5
                ORDER BY EVAL_AGG_SCORE ASC
                LIMIT 10
            """)

            lines.append("| Question | Metric | Score |")
            lines.append("|----------|--------|-------|")
            for row in cur.fetchall():
                q = row[0][:80] + "..." if len(str(row[0])) > 80 else row[0]
                lines.append(f"| {q} | {row[1]} | {row[2]} |")

        summary = "\n".join(lines)
        with open("evaluation_summary.md", "w") as f:
            f.write(summary)
        print(summary, file=sys.stderr)

        gh_output = os.environ.get("GITHUB_OUTPUT")
        if gh_output:
            with open(gh_output, "a") as f:
                f.write(f"passed={'true' if passed else 'false'}\n")
                f.write(f"summary={json.dumps(summary)}\n")

        if not passed:
            print("Quality gate FAILED", file=sys.stderr)
            sys.exit(1)

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
