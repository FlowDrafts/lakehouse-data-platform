# Reproducible test runner: the suite needs a real JVM and a real Iceberg jar, so "it
# works on my machine" is not a claim anyone can check without this.
#
# Versions are pinned together deliberately and the binding constraint is Iceberg, not
# Spark: there is no iceberg-spark-runtime built for Spark 4.2 (checked on Maven Central),
# and JDK 25 is outside Spark 4.1's supported set.
FROM python:3.14-slim-bookworm

ARG ICEBERG_VERSION=1.11.0
ARG ICEBERG_ARTIFACT=iceberg-spark-runtime-4.1_2.13

# ca-certificates for the jar download, procps because Spark's launcher scripts need `ps`.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      openjdk-17-jre-headless=17.0.* \
      ca-certificates \
      curl \
      procps \
 && rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The jar is fetched before the source is copied, so editing code does not re-download 46MB.
ENV ICEBERG_SPARK_JAR=/opt/jars/${ICEBERG_ARTIFACT}-${ICEBERG_VERSION}.jar
RUN mkdir -p /opt/jars \
 && curl -sSfL -o "${ICEBERG_SPARK_JAR}" \
      "https://repo1.maven.org/maven2/org/apache/iceberg/${ICEBERG_ARTIFACT}/${ICEBERG_VERSION}/${ICEBERG_ARTIFACT}-${ICEBERG_VERSION}.jar"

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[dev]"

COPY src/ src/
COPY tests/ tests/
COPY contracts/ contracts/
COPY demo/ demo/
RUN pip install --no-cache-dir -e . --no-deps

# Spark launches Python workers by name; without this it picks whatever python3 is on PATH.
ENV PYSPARK_PYTHON=/usr/local/bin/python

RUN useradd --create-home --uid 10001 runner && chown -R runner:runner /app
USER runner

CMD ["pytest", "-q"]
