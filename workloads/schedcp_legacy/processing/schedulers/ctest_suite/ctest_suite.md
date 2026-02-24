# CTest Suite with Slow Integration Test

**ID:** `ctest_suite`

**Category:** software_testing

**Description:** Test suite with fast unit tests and one slow integration test

## Workload Purpose & Characteristics

This workload emulates a typical CI/CD test suite execution pattern where multiple fast unit tests run alongside a single slow integration test. The workload consists of 39 quick unit test processes ("short") and 1 lengthy integration test ("long"), representing common testing imbalances in software development pipelines.

## Key Performance Characteristics

- **CPU-intensive computation**: Both test types perform mathematical calculations
- **Predictable execution pattern**: Short tests complete quickly, long test dominates runtime
- **No I/O bottlenecks**: Pure CPU-bound computation workload
- **Independent test execution**: No inter-test communication or dependencies
- **Memory-efficient**: Minimal memory footprint for all tests

## Optimization Goals

1. **Reduce total test suite execution time**: Minimize wall-clock time from first test start to last test completion
2. **Ensure integration test progress**: Prevent starvation of the long-running integration test
3. **Maintain test throughput**: Complete short tests efficiently while prioritizing the long test
4. **Optimize CPU allocation**: Distribute CPU time to minimize idle cores during execution

## Scheduling Algorithm

The optimal scheduler for this test suite should implement:

1. **Process identification**: Match processes by name - "short" for unit tests, "long" for integration test
2. **Priority hierarchy**: Assign highest priority to "long" process to ensure continuous execution
3. **Time slice configuration**:
   - Long test: 15ms slices for uninterrupted computation
   - Short tests: 3ms slices for quick completion
4. **Dispatch strategy**: Maintain separate queues with long task queue taking absolute precedence
5. **Load balancing**: Distribute short tests across available cores while keeping long test stable

## Dependencies

- gcc

## Small Setup Commands

```bash
cp $ORIGINAL_CWD/assets/short.c .
gcc -O2 short.c -lm -o short
```

## Large Setup Commands

```bash
cp $ORIGINAL_CWD/assets/long.c .
gcc -O2 long.c -lm -o long
```

## Small Execution Commands

```bash
./short
```

## Large Execution Commands

```bash
./long
```

## Cleanup Commands

```bash
rm -f assets/short assets/long
```
