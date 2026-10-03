"""Sample DAG: build a gold table on an audit branch, check it, then publish or hold (ADR-05).

The check is a blocking task. If it fails, the run fails: main never moves, nothing downstream
runs, and readers keep the previous version. Each step runs the platform's job image as a pod on
EKS. Airflow schedules the work and never moves data itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import dag

TABLE = "gold.fact_transaction"
BRANCH = "audit_{{ ts_nodash }}"  # a fresh branch every run; a held branch is never resumed
IMAGE = "platform-jobs:1.0.0"  # built and pushed to ECR by CI


def job(task_id: str, *args: str, retries: int = 1) -> KubernetesPodOperator:
    """Run one platform job as a pod. S3 and Glue access comes from the service account."""
    return KubernetesPodOperator(
        task_id=task_id,
        name=task_id.replace("_", "-"),
        namespace="data-jobs",
        service_account_name="data-jobs",
        image=IMAGE,
        arguments=[*args, "--table", TABLE],
        retries=retries,
        get_logs=True,
    )


@dag(
    schedule="*/15 * * * *",
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,  # one writer per table; publish would refuse a second anyway
    default_args={"owner": "data-platform", "retry_delay": timedelta(minutes=2)},
    tags=["gold", "gate"],
)
def gold_publish():
    build = job("build_on_branch", "build", "--branch", BRANCH)

    # Great Expectations or Soda, reading <table>.branch_<name>: complete, then correct.
    # A failed check is a hold, not a transient error, so it is never retried.
    check = job("check", "checkpoint", "--branch", BRANCH, retries=0)

    # fast_forward main to the branch, and stamp the version label on the commit.
    publish = job("publish", "publish", "--branch", BRANCH)

    # Each copy loads only the version just published, and swaps it in whole.
    load_clickhouse = job("load_clickhouse", "load-clickhouse")
    load_aurora = job("load_aurora", "load-aurora")

    build >> check >> publish >> [load_clickhouse, load_aurora]


gold_publish()
