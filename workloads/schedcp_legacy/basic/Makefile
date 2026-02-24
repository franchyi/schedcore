# Makefile for building workloads/basic benchmarks

.PHONY: all clean schbench stress-ng cachyos-benchmarker help

# Default target
all: schbench stress-ng cachyos-benchmarker
	@echo "All benchmarks built successfully"

# Build schbench
schbench:
	@echo "Building schbench..."
	@$(MAKE) -C schbench
	@echo "schbench built successfully"

# Build stress-ng
stress-ng:
	@echo "Building stress-ng..."
	@$(MAKE) -C stress-ng
	@echo "stress-ng built successfully"

# Build cachyos-benchmarker
cachyos-benchmarker:
	@echo "Building cachyos-benchmarker..."
	@if [ -f cachyos-benchmarker/Makefile ]; then \
		$(MAKE) -C cachyos-benchmarker; \
	elif [ -f cachyos-benchmarker/build.sh ]; then \
		cd cachyos-benchmarker && ./build.sh; \
	else \
		echo "Warning: No build system found for cachyos-benchmarker"; \
	fi
	@echo "cachyos-benchmarker build complete"

# Clean all builds
clean:
	@echo "Cleaning schbench..."
	@$(MAKE) -C schbench clean 2>/dev/null || true
	@echo "Cleaning stress-ng..."
	@$(MAKE) -C stress-ng clean 2>/dev/null || true
	@echo "Cleaning cachyos-benchmarker..."
	@if [ -f cachyos-benchmarker/Makefile ]; then \
		$(MAKE) -C cachyos-benchmarker clean 2>/dev/null || true; \
	fi
	@echo "All benchmarks cleaned"

# Help target
help:
	@echo "Available targets:"
	@echo "  all                 - Build all benchmarks"
	@echo "  schbench           - Build schbench (scheduler benchmark)"
	@echo "  stress-ng          - Build stress-ng (comprehensive stress testing)"
	@echo "  cachyos-benchmarker - Build cachyos-benchmarker (system benchmarking suite)"
	@echo "  clean              - Clean all build artifacts"
	@echo "  help               - Show this help message"