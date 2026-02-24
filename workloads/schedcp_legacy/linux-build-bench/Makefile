# Makefile for Linux build benchmark
LINUX_DIR := linux
CONFIG := defconfig
JOBS ?= $(shell nproc)

.PHONY: all config clean distclean help

all: config
	@echo "Linux kernel configured. Ready for benchmarking."

config:
	@echo "Configuring Linux kernel with $(CONFIG)..."
	@cd $(LINUX_DIR) && make $(CONFIG)
	@echo "Configuration complete."

# Configure with minimal config for faster builds
tinyconfig:
	@echo "Configuring Linux kernel with tinyconfig..."
	@cd $(LINUX_DIR) && make tinyconfig
	@echo "Tiny configuration complete."

# Configure with allnoconfig for minimal build
allnoconfig:
	@echo "Configuring Linux kernel with allnoconfig..."
	@cd $(LINUX_DIR) && make allnoconfig
	@echo "Minimal configuration complete."

# Clean build artifacts
clean:
	@echo "Cleaning Linux build artifacts..."
	@cd $(LINUX_DIR) && make clean
	@echo "Clean complete."

# Deep clean including config
distclean:
	@echo "Deep cleaning Linux build..."
	@cd $(LINUX_DIR) && make distclean
	@echo "Distclean complete."
