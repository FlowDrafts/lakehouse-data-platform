"""Test fixtures: one local Spark session with a real Iceberg catalog.

Loaded by pytest as a plugin (see `pyproject.toml`). The guarantees under test are properties
of Iceberg's MERGE, branches, tags and commit conflicts, so the tests run against the engine,
not mocks. A filesystem catalog stands in for Glue: table behaviour is identical, while commit
coordination is not, and is listed as untested in the test plan.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ICEBERG_JAR = REPO / ".tools" / "jars" / "iceberg-spark-runtime-4.1_2.13-1.11.0.jar"
ICEBERG_PACKAGE = "org.apache.iceberg:iceberg-spark-runtime-4.1_2.13:1.11.0"
LOCAL_JDK = REPO / ".tools" / "jdk21"

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
if "JAVA_HOME" not in os.environ and LOCAL_JDK.exists():
    os.environ["JAVA_HOME"] = str(LOCAL_JDK)
    os.environ["PATH"] = f"{LOCAL_JDK / 'bin'}:{os.environ['PATH']}"


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    """One session for the whole run, since starting Spark takes several seconds."""
    from pyspark.sql import SparkSession

    jar = os.environ.get("ICEBERG_SPARK_JAR", str(ICEBERG_JAR))
    builder = (
        SparkSession.builder.master("local[2]")
        .appName("lakehouse-tests")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
        )
        .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.lake.type", "hadoop")
        .config("spark.sql.catalog.lake.warehouse", str(tmp_path_factory.mktemp("warehouse")))
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
    )
    if Path(jar).exists():
        builder = builder.config("spark.jars", jar)
    else:
        builder = builder.config("spark.jars.packages", ICEBERG_PACKAGE)

    session = builder.getOrCreate()
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def namespace(spark) -> str:
    """A fresh namespace for each test, so no test sees another's tables."""
    name = f"lake.test_{uuid.uuid4().hex[:8]}"
    spark.sql(f"CREATE NAMESPACE {name}")
    return name
