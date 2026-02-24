#!/usr/bin/env python3
"""
Simple Nginx Benchmark using wrk2
"""
import subprocess
import time
import os
import sys

def start_nginx():
    """Start nginx server"""
    print("Starting nginx...")
    subprocess.run(["pkill", "nginx"], capture_output=True)
    time.sleep(1)
    
    nginx_bin = "./nginx/objs/nginx"
    nginx_conf = os.path.abspath("nginx-local.conf")
    
    result = subprocess.run([nginx_bin, "-c", nginx_conf], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Failed to start nginx: {result.stderr}")
        return False
    
    time.sleep(2)
    
    # Test if nginx is responding
    test = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "http://127.0.0.1:8080/"], 
                         capture_output=True, text=True)
    if test.stdout == "200":
        print("✓ Nginx started successfully")
        return True
    else:
        print(f"✗ Nginx not responding (HTTP {test.stdout})")
        return False

def stop_nginx():
    """Stop nginx server"""
    print("Stopping nginx...")
    subprocess.run(["./nginx/objs/nginx", "-s", "quit"], capture_output=True)
    time.sleep(1)
    subprocess.run(["pkill", "nginx"], capture_output=True)

def run_wrk_test(name, threads, connections, duration, rate):
    """Run a single wrk2 test"""
    print(f"\n--- Running {name} ---")
    print(f"Threads: {threads}, Connections: {connections}, Duration: {duration}s, Rate: {rate} req/s")
    
    cmd = [
        "./wrk2/wrk",
        f"-t{threads}",
        f"-c{connections}",
        f"-d{duration}s",
        f"-R{rate}",
        "--latency",
        "http://127.0.0.1:8080/"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=duration+30)
    
    if result.returncode == 0:
        print("✓ Test completed")
        print("\nOutput:")
        print(result.stdout)
    else:
        print(f"✗ Test failed: {result.stderr}")
    
    return result.stdout

def main():
    print("=" * 60)
    print("NGINX BENCHMARK WITH WRK2")
    print("=" * 60)
    
    # Start nginx
    if not start_nginx():
        print("Failed to start nginx. Exiting.")
        sys.exit(1)
    
    try:
        # Run tests
        tests = [
            ("Low Load", 2, 10, 10, 100),
            ("Medium Load", 4, 50, 10, 1000),
            ("High Load", 8, 100, 10, 5000),
        ]
        
        for test in tests:
            run_wrk_test(*test)
            time.sleep(2)
    
    finally:
        # Stop nginx
        stop_nginx()
    
    print("\n" + "=" * 60)
    print("BENCHMARK COMPLETED")
    print("=" * 60)

if __name__ == "__main__":
    main()