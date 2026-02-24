# Makefile for CXL double bandwidth microbenchmark

# Compiler and flags
CXX = g++
CXXFLAGS = -std=c++17 -O2 -Wall -Wextra -pthread
LDFLAGS = -lnuma -pthread

# Source and target
SOURCE = double_bandwidth.cpp
TARGET = double_bandwidth

# Default target
all: $(TARGET)

# Build the binary
$(TARGET): $(SOURCE)
	$(CXX) $(CXXFLAGS) -o $(TARGET) $(SOURCE) $(LDFLAGS)

# Clean build artifacts
clean:
	rm -f $(TARGET)

# Install target (optional)
install: $(TARGET)
	cp $(TARGET) /usr/local/bin/

# Phony targets
.PHONY: all clean install

# Debug build
debug: CXXFLAGS += -g -DDEBUG
debug: $(TARGET)

# Help target
help:
	@echo "Available targets:"
	@echo "  all     - Build the double_bandwidth binary (default)"
	@echo "  debug   - Build with debug symbols and DEBUG flag"
	@echo "  clean   - Remove build artifacts"
	@echo "  install - Install binary to /usr/local/bin/"
	@echo "  help    - Show this help message"