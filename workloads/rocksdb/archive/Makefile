.PHONY: all clone build configure benchmark clean install deps

# RocksDB configuration
ROCKSDB_REPO = https://github.com/facebook/rocksdb.git
ROCKSDB_DIR = rocksdb
ROCKSDB_BRANCH = main
BUILD_THREADS = $(shell nproc)

all: deps clone build configure

deps:
	@echo "Installing RocksDB dependencies..."
	sudo apt-get update
	sudo apt-get install -y build-essential libgflags-dev libsnappy-dev \
		zlib1g-dev libbz2-dev liblz4-dev libzstd-dev cmake \
		libgtest-dev libtbb-dev

clone:
	@echo "Cloning RocksDB repository..."
	if [ ! -d $(ROCKSDB_DIR) ]; then \
		git clone --depth=1 --branch=$(ROCKSDB_BRANCH) $(ROCKSDB_REPO) $(ROCKSDB_DIR); \
	fi

build: clone
	@echo "Building RocksDB..."
	cd $(ROCKSDB_DIR) && make -j$(BUILD_THREADS) static_lib
	cd $(ROCKSDB_DIR) && make -j$(BUILD_THREADS) db_bench

configure:
	@echo "Configuring RocksDB..."
	mkdir -p /tmp/rocksdb_data

benchmark:
	@echo "Running RocksDB benchmark..."
	python3 rocksdb_benchmark.py

quick-benchmark:
	@echo "Running quick RocksDB benchmark..."
	cd $(ROCKSDB_DIR) && ./db_bench \
		--benchmarks=fillseq,readrandom \
		--num=100000 \
		--db=/tmp/rocksdb_data \
		--disable_wal=true \
		--statistics=false

clean:
	@echo "Cleaning up..."
	cd $(ROCKSDB_DIR) && make clean || true
	rm -rf /tmp/rocksdb_data
	rm -rf $(ROCKSDB_DIR)

install: build
	@echo "Installing RocksDB..."
	cd $(ROCKSDB_DIR) && sudo make install

test: build
	@echo "Running RocksDB tests..."
	cd $(ROCKSDB_DIR) && make -j$(BUILD_THREADS) check