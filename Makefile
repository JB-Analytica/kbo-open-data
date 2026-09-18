# kbo-open-data
#
# Everything runs through uv, so there is no "activate the venv" step. The default
# destination is a local DuckDB file: no MotherDuck account, no credentials, no network.
#
#   make demo      synthetic extract -> marts -> Parquet. Needs nothing but this repo.
#   make build     the real thing, from the KBO zip named by KBO_ZIP in .env.

.DEFAULT_GOAL := help
SHELL := /bin/bash

ROOT := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
UV := uv run

# dbt runs with its project directory as the working directory, so a relative DUCKDB_PATH
# would land inside transform/. Resolve it against the repo root once, here.
DESTINATION ?= duckdb
DUCKDB_PATH ?= $(ROOT)/kbo.duckdb
# Real runs publish to data/published/, which is committed. The demo publishes to
# data/demo/, which is not -- synthetic aggregates must never be mistaken for real ones.
PUBLISHED_DIR ?= $(ROOT)/data/published
DEMO_DIR := $(ROOT)/data/demo
DEMO_ZIP := $(ROOT)/data/raw/KboOpenData_SYNTHETIC_Full.zip
# The demo gets its own warehouse file. Sharing DUCKDB_PATH would merge synthetic rows
# into a real extract's tables -- same table names, same merge keys, silently wrong.
DEMO_DUCKDB := $(ROOT)/kbo_demo.duckdb

DBT := $(UV) dbt --no-use-colors
DBT_DIRS := --project-dir $(ROOT)/transform --profiles-dir $(ROOT)/transform

export DESTINATION
export DUCKDB_PATH

.PHONY: help
help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install:  ## Create the virtualenv and install everything
	uv sync --extra dev

.PHONY: fetch
fetch:  ## Fetch the daily KBO update file over SFTP (needs access granted by FOD Economie)
	$(UV) kbo fetch

.PHONY: load
load:  ## Load the KBO zip named by KBO_ZIP into the warehouse
	$(UV) kbo load

.PHONY: transform
transform:  ## Run dbt: staging, intermediate and the five aggregate marts
	$(DBT) build $(DBT_DIRS)

.PHONY: publish
publish:  ## Write the marts to data/published/ as Parquet
	$(DBT) run-operation export_marts $(DBT_DIRS) --args '{"output_dir": "$(PUBLISHED_DIR)"}'

.PHONY: build
build: load transform publish  ## Load, transform and publish from KBO_ZIP -- the whole pipeline

.PHONY: demo-extract
demo-extract:  ## Write a synthetic KBO extract, so the pipeline runs with no KBO registration
	$(UV) kbo demo-extract $(DEMO_ZIP)

.PHONY: demo
demo: demo-extract  ## Run the whole pipeline on the synthetic extract
	@mkdir -p $(DEMO_DIR)
	KBO_ZIP=$(DEMO_ZIP) PUBLISHED_DIR=$(DEMO_DIR) DUCKDB_PATH=$(DEMO_DUCKDB) $(MAKE) load transform publish

.PHONY: test
test:  ## Lint, type-check and run the Python tests
	$(UV) poe check

.PHONY: deploy
deploy:  ## Run the pipeline against MotherDuck (needs MOTHERDUCK_TOKEN)
	DESTINATION=motherduck $(MAKE) build

.PHONY: clean
clean:  ## Remove the local warehouse, dbt artefacts and the synthetic extract
	rm -f $(DUCKDB_PATH) $(DUCKDB_PATH).wal $(DEMO_DUCKDB) $(DEMO_DUCKDB).wal $(DEMO_ZIP)
	rm -rf $(DEMO_DIR) $(ROOT)/transform/target $(ROOT)/transform/logs $(ROOT)/.dlt/pipelines
