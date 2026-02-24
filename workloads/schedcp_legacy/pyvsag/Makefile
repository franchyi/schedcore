# PyVSAG ANN Benchmark Makefile

.PHONY: all install test benchmark clean help

# Default target
all: install

# Install dependencies
install:
	@echo "Installing PyVSAG benchmark dependencies..."
	pip install -r requirements.txt

# Run basic benchmark
benchmark:
	@echo "Running PyVSAG scheduler benchmark..."
	python pyvsag_bench_start.py

# Run benchmark with production schedulers only
benchmark-prod:
	@echo "Running PyVSAG benchmark (production schedulers only)..."
	python pyvsag_bench_start.py --production-only

# Test specific scheduler
test-scheduler:
	@echo "Testing specific scheduler (use SCHEDULER=name)..."
	python pyvsag_bench_start.py --scheduler $(SCHEDULER)

# Run small-scale test
test:
	@echo "Running quick test with reduced parameters..."
	python pyvsag_bench_start.py \
		--num-elements 5000 \
		--num-queries 100 \
		--timeout 60

# Check PyVSAG installation
check:
	@echo "Checking PyVSAG installation..."
	@python -c "import pyvsag; print(f'PyVSAG version: {pyvsag.__version__}')" || \
		echo "PyVSAG not installed. Run 'make install' first."

# Clean results
clean:
	@echo "Cleaning benchmark results..."
	rm -rf results/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -delete

# Show help
help:
	@echo "PyVSAG ANN Benchmark Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  install      - Install dependencies"
	@echo "  benchmark    - Run full benchmark"
	@echo "  benchmark-prod - Run benchmark with production schedulers only"
	@echo "  test-scheduler - Test specific scheduler (set SCHEDULER=name)"
	@echo "  test         - Run quick test"
	@echo "  check        - Check PyVSAG installation"
	@echo "  clean        - Clean results and cache files"
	@echo "  help         - Show this help"
	@echo ""
	@echo "Examples:"
	@echo "  make install"
	@echo "  make benchmark"
	@echo "  make test-scheduler SCHEDULER=scx_rusty"
	@echo "  make test"