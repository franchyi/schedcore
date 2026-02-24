.PHONY: all build configure benchmark clean install deps wrk2

# Nginx configuration
NGINX_DIR = nginx
WRK2_REPO = https://github.com/giltene/wrk2.git
WRK2_DIR = wrk2
BUILD_THREADS = $(shell nproc)
PWD = $(shell pwd)

all: deps build-nginx build-wrk2 configure

deps:
	@echo "Installing Nginx dependencies..."
	sudo apt-get update
	sudo apt-get install -y build-essential zlib1g-dev libpcre3-dev libssl-dev \
		lua5.1 liblua5.1-0-dev python3-psutil

build-wrk2:
	@echo "Cloning and building wrk2..."
	if [ ! -d $(WRK2_DIR) ]; then \
		git clone --depth=1 $(WRK2_REPO) $(WRK2_DIR); \
	fi
	cd $(WRK2_DIR) && make -j$(BUILD_THREADS)

build: build-nginx build-wrk2

build-nginx:
	@echo "Building Nginx..."
	@if [ ! -d $(NGINX_DIR) ]; then \
		echo "Error: nginx submodule not found. Please run: git submodule update --init"; \
		exit 1; \
	fi
	cd $(NGINX_DIR) && ./auto/configure \
		--prefix=$(PWD)/nginx-install \
		--sbin-path=$(PWD)/$(NGINX_DIR)/objs/nginx \
		--conf-path=$(PWD)/nginx-local.conf \
		--pid-path=$(PWD)/nginx.pid \
		--lock-path=$(PWD)/nginx.lock \
		--error-log-path=$(PWD)/error.log \
		--http-log-path=$(PWD)/access.log \
		--with-http_ssl_module \
		--with-http_v2_module \
		--with-http_realip_module \
		--with-http_stub_status_module \
		--with-threads \
		--with-file-aio \
		--http-client-body-temp-path=$(PWD)/client_temp \
		--http-proxy-temp-path=$(PWD)/proxy_temp \
		--http-fastcgi-temp-path=$(PWD)/fastcgi_temp \
		--http-uwsgi-temp-path=$(PWD)/uwsgi_temp \
		--http-scgi-temp-path=$(PWD)/scgi_temp
	cd $(NGINX_DIR) && make -j$(BUILD_THREADS)
	@echo "Creating temp directories..."
	@mkdir -p client_temp proxy_temp fastcgi_temp uwsgi_temp scgi_temp

configure: build-nginx
	@echo "Configuring Nginx..."
	mkdir -p ./html
	echo "<html><body><h1>Nginx Benchmark Test Page</h1></body></html>" > ./html/index.html
	@echo "Creating test files..."
	@dd if=/dev/zero of=./html/1k.bin bs=1024 count=1 2>/dev/null
	@dd if=/dev/zero of=./html/10k.bin bs=1024 count=10 2>/dev/null
	@dd if=/dev/zero of=./html/100k.bin bs=1024 count=100 2>/dev/null
	@dd if=/dev/zero of=./html/1m.bin bs=1024 count=1024 2>/dev/null
	@echo "Creating nginx-local.conf from nginx.conf..."
	@cp nginx.conf nginx-local.conf
	@echo "Nginx configuration complete!"

install: build configure
	@echo "Nginx built and configured locally"

start: install
	@echo "Starting Nginx server..."
	./$(NGINX_DIR)/objs/nginx -c $(PWD)/nginx-local.conf
	sleep 2

stop:
	@echo "Stopping Nginx server..."
	./$(NGINX_DIR)/objs/nginx -s quit -c $(PWD)/nginx-local.conf 2>/dev/null || true
	pkill -f nginx || true

benchmark: start
	@echo "Running Nginx benchmark with wrk2..."
	python3 nginx_benchmark.py

quick-benchmark: start
	@echo "Running quick Nginx benchmark..."
	./$(WRK2_DIR)/wrk -t4 -c100 -d30s -R2000 http://127.0.0.1:8080/

clean:
	@echo "Cleaning up..."
	cd $(NGINX_DIR) && make clean || true
	cd $(WRK2_DIR) && make clean || true
	rm -rf nginx-install html nginx-bin nginx-local.conf nginx.pid results
	rm -rf client_temp proxy_temp fastcgi_temp uwsgi_temp scgi_temp
	rm -f error.log access.log nginx.lock

test: install
	@echo "Testing Nginx configuration..."
	./$(NGINX_DIR)/objs/nginx -t -c $(PWD)/nginx-local.conf