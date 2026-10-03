# Local toolchain lives in .tools/ (git-ignored). No admin rights needed.
#
# Versions are the newest that actually work together, and the constraint is
# Iceberg, not Spark: there is no iceberg-spark-runtime for Spark 4.2 (checked on
# Maven Central), and JDK 25 is outside Spark 4.1's supported set. So 4.1.3 / 21.
SPARK_VERSION   := 4.1.3
ICEBERG_VERSION := 1.11.0
ICEBERG_JAR     := .tools/jars/iceberg-spark-runtime-4.1_2.13-$(ICEBERG_VERSION).jar
JDK_HOME        := $(CURDIR)/.tools/jdk21
UV              := .tools/uv/uv
PY              := .venv/bin/python

export JAVA_HOME         := $(JDK_HOME)
export ICEBERG_SPARK_JAR := $(CURDIR)/$(ICEBERG_JAR)
export PYSPARK_PYTHON    := $(CURDIR)/$(PY)


.PHONY: help setup tools venv jar test test-fast mutation contract-check demo check diagram clean-tools

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/' | expand -t24

setup: tools venv jar ## Install the whole toolchain and dependencies
	@echo "ready — run 'make test'"

tools: $(UV) $(JDK_HOME)/bin/java ## Fetch uv and JDK 21 into .tools/

$(UV):
	mkdir -p .tools
	curl -sSL https://astral.sh/uv/install.sh \
	  | UV_INSTALL_DIR="$(CURDIR)/.tools/uv" XDG_BIN_HOME="$(CURDIR)/.tools/uv" \
	    UV_NO_MODIFY_PATH=1 sh

$(JDK_HOME)/bin/java:
	mkdir -p $(JDK_HOME)
	curl -sSL "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse" \
	  | tar -xz -C $(JDK_HOME) --strip-components=1

venv: $(UV) ## Create .venv and install dependencies
	$(UV) venv .venv --python 3.14
	VIRTUAL_ENV=.venv $(UV) pip install -e ".[dev]"

jar: $(ICEBERG_JAR) ## Download the Iceberg Spark runtime jar

$(ICEBERG_JAR):
	mkdir -p .tools/jars
	curl -sSL -o $@ "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-4.1_2.13/$(ICEBERG_VERSION)/iceberg-spark-runtime-4.1_2.13-$(ICEBERG_VERSION).jar"

test: ## Run the whole suite, including the real-Iceberg tests
	.venv/bin/pytest $(ARGS)

test-fast: ## Only the tests that need no Spark session
	.venv/bin/pytest -m "not spark" $(ARGS)

mutation: ## Break each guard on purpose; every break must fail a test (about 15 minutes)
	$(PY) tests/mutation/run.py $(ARGS)

contract-check: ## Cube metric filters must use values the data contracts allow
	$(PY) tests/contract_check.py

demo: ## Run the three hard problems end to end on a local Iceberg catalog
	$(PY) demo/run.py

check: test contract-check ## The tests and the contract check
	$(PY) tests/mutation/run.py --check

# The README and design doc show a PNG rendered from the Mermaid source, so every viewer can see it.
# Rendering goes through the public mermaid.ink service; no local browser is needed.
DIAGRAM := docs/architecture/lakehouse_architecture
diagram: ## Re-render the architecture PNG from its Mermaid source
	$(PY) -c "import base64, urllib.request as r; src = open('$(DIAGRAM).mmd').read(); url = 'https://mermaid.ink/img/' + base64.urlsafe_b64encode(src.encode()).decode() + '?type=png&bgColor=FFFFFF&width=1600'; open('$(DIAGRAM).png', 'wb').write(r.urlopen(r.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=90).read())"

clean-tools: ## Remove the local toolchain
	rm -rf .tools .venv
