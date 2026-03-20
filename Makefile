.DEFAULT_GOAL := help
LAMBDAS_DIR  := lambdas
TF_DIR       := terraform
PYTHON       := python3

# ── Help ──────────────────────────────────────────────────────────────────────
.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Python environment ────────────────────────────────────────────────────────
.PHONY: install
install: ## Install runtime + dev dependencies
	pip install -r $(LAMBDAS_DIR)/requirements-dev.txt

# ── Tests ─────────────────────────────────────────────────────────────────────
.PHONY: test
test: ## Run all unit tests
	cd $(LAMBDAS_DIR) && $(PYTHON) -m pytest tests/ -v

.PHONY: test-cov
test-cov: ## Run tests with coverage report
	cd $(LAMBDAS_DIR) && $(PYTHON) -m pytest tests/ -v \
		--cov=incident_bundler --cov=llm_agent --cov=verifier \
		--cov-report=term-missing --cov-report=html:../coverage

# ── Lint ──────────────────────────────────────────────────────────────────────
.PHONY: lint
lint: ## Lint Lambda source with ruff (pip install ruff)
	ruff check $(LAMBDAS_DIR)/incident_bundler/app.py \
	           $(LAMBDAS_DIR)/llm_agent/app.py \
	           $(LAMBDAS_DIR)/verifier/app.py

.PHONY: fmt
fmt: ## Auto-format Lambda source with ruff
	ruff format $(LAMBDAS_DIR)/incident_bundler/app.py \
	            $(LAMBDAS_DIR)/llm_agent/app.py \
	            $(LAMBDAS_DIR)/verifier/app.py

# ── Terraform ─────────────────────────────────────────────────────────────────
.PHONY: tf-init
tf-init: ## terraform init
	cd $(TF_DIR) && terraform init

.PHONY: tf-plan
tf-plan: ## terraform plan (requires terraform.tfvars)
	cd $(TF_DIR) && terraform plan -out=tfplan

.PHONY: tf-apply
tf-apply: ## terraform apply previously saved plan
	cd $(TF_DIR) && terraform apply tfplan

.PHONY: tf-destroy
tf-destroy: ## terraform destroy (prompts for confirmation)
	cd $(TF_DIR) && terraform destroy

.PHONY: tf-validate
tf-validate: ## Validate Terraform configuration
	cd $(TF_DIR) && terraform validate

# ── Lambda packaging ──────────────────────────────────────────────────────────
.PHONY: package
package: ## Zip each Lambda function for manual deployment
	@for fn in incident_bundler llm_agent verifier; do \
		echo "Packaging $$fn..."; \
		cd $(LAMBDAS_DIR)/$$fn && \
		pip install -r ../requirements.txt -t ./package --quiet && \
		cp app.py ./package/ && \
		cd package && zip -qr ../../$$fn.zip . && \
		cd .. && rm -rf package && cd ../..; \
	done
	@echo "Zip files written to lambdas/"

# ── CI shortcut ───────────────────────────────────────────────────────────────
.PHONY: ci
ci: lint test ## Run lint + tests (used in CI)
