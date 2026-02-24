# Linux Kernel Scheduler Optimization Test Cases

## Overview

This document presents a comprehensive collection of parallel benchmark test cases designed to demonstrate how custom Linux kernel schedulers can significantly improve performance on multi-CPU systems. These tests specifically target "long-tail" scenarios where one task takes significantly longer than others, creating inefficiencies in standard CFS (Completely Fair Scheduler) scheduling.

## Core Concept: The Long-Tail Problem

The framework implements a 40-task parallel configuration where:
- 39 tasks complete quickly (short tasks)
- 1 task takes significantly longer (long task)

This creates severe load imbalance typical in real-world scenarios:
- Under standard CFS scheduling: cores become idle after completing short tasks
- With custom schedulers: better load balancing and resource utilization
- Expected performance improvement: 30-35% reduction in wall-clock time

## Test Case Implementations

### 1. File Compression

**ID:** `compression`
**Category:** File Processing
**Description:** Compression of mixed-size files with severe load imbalance

**Configuration:**
- 39 short tasks: Compress small files (3M records each)
- 1 long task: Compress large file (20M records)
- Creates massive imbalance in compression time

**Setup Commands:**
```bash
# Small file setup (executed 39 times)
mkdir -p test_data
seq 1 3000000 > test_data/short_file.dat
cp $ORIGINAL_CWD/assets/compression.py .
cp compression.py small_compression.py
chmod +x small_compression.py

# Large file setup (executed 1 time)
mkdir -p test_data  
seq 1 20000000 > test_data/large_file.dat
cp $ORIGINAL_CWD/assets/compression.py .
cp compression.py large_compression.py
chmod +x large_compression.py
```

**Execution:**
- Small commands: `python3 small_compression.py test_data/short_file.dat 9`
- Large commands: `python3 large_compression.py test_data/large_file.dat 9`

**Expected Improvement:** 33%

### 2. Video Transcode (C++ Implementation)

**ID:** `video_transcode`
**Category:** Media Processing
**Description:** Video transcoding with one large file dominating processing time

**Configuration:**
- 39 short tasks: Process short video clips (30 seconds duration)
- 1 long task: Process long video clip (70 seconds duration)
- Severe imbalance in transcoding time

**Setup Commands:**
```bash
# Short video setup
mkdir -p clips out
ffmpeg -f lavfi -i testsrc=duration=30:size=320x240:rate=30 -loglevel quiet clips/short.mp4
cp $ORIGINAL_CWD/assets/video_transcode.cpp .
g++ -o small_video_transcode video_transcode.cpp -lavformat -lavcodec -lavutil -lswscale -lpthread -lm -lz

# Long video setup  
mkdir -p clips out
ffmpeg -f lavfi -i testsrc=duration=70:size=1920x1080:rate=30 -loglevel quiet clips/long.mp4
cp $ORIGINAL_CWD/assets/video_transcode.cpp .
g++ -o large_video_transcode video_transcode.cpp -lavformat -lavcodec -lavutil -lswscale -lpthread -lm -lz
```

**Execution:**
- Small commands: `./small_video_transcode clips/short.mp4 out/short_out.mp4 640`
- Large commands: `./large_video_transcode clips/long.mp4 out/long_out.mp4 640`

**Expected Improvement:** 33%

### 3. CTest Suite with Integration Test

**ID:** `ctest_suite`
**Category:** Software Testing
**Description:** Test suite with fast unit tests and one slow integration test

**Configuration:**
- 39 short tasks: Quick unit test programs
- 1 long task: Slow integration test program
- Creates typical CI/CD pipeline imbalance

**Setup Commands:**
```bash
# Short test setup
cp $ORIGINAL_CWD/assets/short.c .
gcc -O2 short.c -lm -o short

# Long test setup
cp $ORIGINAL_CWD/assets/long.c .
gcc -O2 long.c -lm -o long
```

**Execution:**
- Small commands: `./short`
- Large commands: `./long`

**Expected Improvement:** 33%

### 4. Git Add Different Size Directories

**ID:** `git_add_different`
**Category:** Version Control
**Description:** Git add operations with different numbers of files

**Configuration:**
- 39 short tasks: Git add on small repository (200MB data)
- 1 long task: Git add on large repository (~2GB data)
- Simulates repository staging imbalance scenarios

**Setup Commands:**
```bash
# Small repository setup
mkdir -p small_repo && cd small_repo && git init
cd small_repo && git config user.name 'Test User' && git config user.email 'test@example.com'
cd small_repo && dd if=/dev/urandom of=large_file_1.bin bs=100M count=1 2>/dev/null
cd small_repo && dd if=/dev/urandom of=large_file_2.bin bs=100M count=1 2>/dev/null
cd small_repo && mkdir -p src && for i in {1..200}; do echo "// File $i" > src/file_$i.js; done

# Large repository setup
mkdir -p large_repo && cd large_repo && git init
cd large_repo && git config user.name 'Test User' && git config user.email 'test@example.com'
cd large_repo && dd if=/dev/urandom of=huge_file_1.bin bs=500M count=1 2>/dev/null
cd large_repo && dd if=/dev/urandom of=huge_file_2.bin bs=500M count=1 2>/dev/null
cd large_repo && mkdir -p src && for i in {1..1000}; do dd if=/dev/urandom of=src/file_$i.dat bs=1M count=1 2>/dev/null; done
```

**Execution:**
- Small commands: `cd small_repo && git add .`
- Large commands: `cd large_repo && git add .`

**Expected Improvement:** 30%

### 5. Parallel File System Operations

**ID:** `file_checksum`
**Category:** File Processing  
**Description:** Checksum operations with one large file blocking completion

**Configuration:**
- 39 short tasks: Checksum small files (200MB each)
- 1 long task: Checksum large file (1000MB)
- Creates file I/O imbalance

**Setup Commands:**
```bash
# Small file setup
mkdir -p large-dir
dd if=/dev/urandom of=large-dir/short_file.dat bs=1M count=200 2>/dev/null

# Large file setup
mkdir -p large-dir
dd if=/dev/urandom of=large-dir/long_file.dat bs=1M count=1000 2>/dev/null
```

**Expected Improvement:** 33%

### 6. Log Processing with Skewed Chunks

**ID:** `log_processing`
**Category:** Data Processing
**Description:** Processing log files with different sizes and compression

**Configuration:**
- 39 short tasks: Process small log files (500K entries each)
- 1 long task: Process large log file (7M entries)
- Simulates log analysis pipeline imbalance

**Setup Commands:**
```bash
# Small log setup
mkdir -p log_chunks
seq 1 500000 | awk '{print strftime("%Y-%m-%d %H:%M:%S"), "[INFO]", "Request from", "192.168.1."int(rand()*255), "processed in", int(rand()*100), "ms"}' > log_chunks/small.log

# Large log setup  
mkdir -p log_chunks
seq 1 7000000 | awk '{print strftime("%Y-%m-%d %H:%M:%S"), "[INFO]", "Request from", "192.168.1."int(rand()*255), "processed in", int(rand()*100), "ms"}' > log_chunks/large.log
```

**Expected Improvement:** 35%

### 7. Hot Key Aggregation

**ID:** `hotkey_aggregation`
**Category:** Data Processing
**Description:** Analytics with skewed data distribution (hot key problem)

**Configuration:**
- 39 short tasks: Process regular keys (8K regular keys, 15K hot keys)
- 1 long task: Process heavily skewed data (100K regular keys, 800K hot keys)
- Simulates distributed analytics imbalance

**Data Generation:**
Uses `spark_skew_prepare.py` to generate CSV files with configurable key distributions

**Execution:**
- Small commands: `python3 spark_skew_test.py spark_small.csv`
- Large commands: `python3 spark_skew_test.py spark_large.csv`

**Expected Improvement:** 33%

### 8. DDoS Log Analysis

**ID:** `ddos_log_analysis`
**Category:** Data Processing  
**Description:** Security log analysis with temporal spike pattern (DDoS simulation)

**Configuration:**
- 39 short tasks: Process normal log volumes (30K normal, 8K error logs)
- 1 long task: Process DDoS spike volume (1M normal, 500K error logs)
- Simulates web traffic spike processing

**Data Generation:**
Uses `pandas_etl_prepare.py` to generate compressed log files with configurable volumes

**Expected Improvement:** 33%

### 9. Viral Product Analytics

**ID:** `viral_product_analytics`
**Category:** Data Processing
**Description:** Retail analytics with temporal hot product pattern (trending item simulation)

**Configuration:**
- 39 short tasks: Process regular transactions (8K regular, 12K hot transactions)
- 1 long task: Process popular item transactions (100K regular, 700K hot transactions)  
- Simulates retail analytics join imbalance

**Data Generation:**
Uses `flink_join_prepare.py` to generate transaction CSV files with hot product distributions

**Expected Improvement:** 33%

## Framework Configuration

### Test Structure
All test cases follow a consistent pattern defined in `test_cases_parallel.json`:

```json
{
  "configuration": {
    "short_tasks": 39,
    "long_tasks": 1,
    "total_tasks": 40
  }
}
```

### Common Fields
- **small_setup**: Commands to prepare data for short tasks
- **large_setup**: Commands to prepare data for long task
- **small_commands**: Commands executed 39 times in parallel
- **large_commands**: Commands executed 1 time in parallel
- **cleanup_commands**: Resource cleanup after test
- **expected_improvement**: Expected scheduler optimization ratio (0.30-0.35)
- **dependencies**: Required system packages

### Asset Scripts
The framework includes Python preparation scripts for complex workloads:

- **spark_skew_prepare.py**: Generates CSV with configurable key skew
- **pandas_etl_prepare.py**: Generates compressed log files with volume spikes
- **flink_join_prepare.py**: Creates transaction data with hot product distributions

### Execution Environment
- **Target platform**: Linux with 4+ CPU cores
- **Total tasks**: 40 parallel (39 short + 1 long)
- **Expected improvements**: 30-35% with optimized schedulers
- **Test categories**: File processing, media, testing, version control, data analytics

## Running the Framework

### Basic Usage
```bash
# List all available test cases
python3 evaluate_workloads_parallel.py --list

# Run a specific test case
python3 evaluate_workloads_parallel.py --test pigz_compression

# Run all test cases
python3 evaluate_workloads_parallel.py --all
```

### Analysis Features
Each test provides detailed analysis including:
- **Process monitoring**: Tracks CPU usage and runtime per task
- **Long-tail detection**: Identifies tasks running significantly longer  
- **Scheduler optimization**: Estimates potential improvement from custom schedulers
- **JSON output**: Structured results for further analysis

## Key Benefits

1. **Realistic Workloads**: Based on real-world scenarios with authentic load imbalance patterns
2. **Parallel Execution**: 40-task configuration creates measurable scheduler optimization opportunities  
3. **Zero Application Changes**: Optimizations work at kernel level without code modifications
4. **Quick Demonstration**: Tests complete in minutes, showing clear performance improvements
5. **Comprehensive Coverage**: Spans file processing, media, testing, version control, and data analytics

## Expected Outcomes

With optimized kernel schedulers, these test cases demonstrate:
- **30-35% performance improvement** in wall-clock time
- **Better resource utilization** across all CPU cores
- **Reduced tail latency** in parallel workload completion
- **Scalable optimization** applicable to production systems
