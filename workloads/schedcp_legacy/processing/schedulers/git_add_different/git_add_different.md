# Git Add Different Size Directories

**ID:** `git_add_different`

**Category:** version_control

**Description:** Git add operations with different numbers of files

## Workload Purpose & Characteristics

This workload simulates version control staging operations with vastly different repository sizes, common in monorepo environments or mixed project workflows. The scenario includes 39 processes staging small repositories (40MB binary + 100 source files) and 1 process staging a large repository (200MB binary + 500MB of data files), representing typical development team workflows with imbalanced repository sizes.

## Key Performance Characteristics

- **Mixed I/O and CPU workload**: File hashing, compression, and index updates
- **Metadata-intensive operations**: Git index manipulation and object database writes
- **Variable file sizes**: Mix of large binaries and numerous small files
- **Disk-intensive writes**: Creating git objects and updating staging area
- **Memory usage scales with repo size**: Larger repos require more memory for indexing

## Optimization Goals

1. **Minimize total staging time**: Reduce time to stage all repositories
2. **Prioritize large repository operations**: Ensure large repo staging completes efficiently
3. **Optimize git object creation**: Minimize overhead of object database operations
4. **Balance I/O load**: Prevent small operations from blocking large repo staging
5. **Maintain developer productivity**: Keep small repo operations responsive

## Scheduling Algorithm

The optimal scheduler for git operations should implement:

1. **Process identification**: Detect "small_git_add" and "large_git_add" processes by name
2. **Resource prioritization**: Assign highest priority to large_git_add for CPU and I/O
3. **Time slice configuration**:
   - Large git add: 25ms slices for complex operations
   - Small git add: 5ms slices for quick completion
4. **I/O scheduling**: Prioritize large repository disk operations to prevent starvation
5. **Memory pressure handling**: Consider available memory when scheduling git operations

## Dependencies

- git
- g++

## Small Setup Commands

```bash
mkdir -p small_repo && cd small_repo && git init
cd small_repo && git config user.name 'Test User' && git config user.email 'test@example.com'
cd small_repo && dd if=/dev/urandom of=large_file_1.bin bs=20M count=1 2>/dev/null
cd small_repo && dd if=/dev/urandom of=large_file_2.bin bs=20M count=1 2>/dev/null
cd small_repo && mkdir -p src && for i in {1..100}; do echo "// File $i" > src/file_$i.js; done
cp $ORIGINAL_CWD/assets/git_add_libgit2.cpp .
g++ -o small_git_add git_add_libgit2.cpp -lgit2
```

## Large Setup Commands

```bash
mkdir -p large_repo && cd large_repo && git init
cd large_repo && git config user.name 'Test User' && git config user.email 'test@example.com'
cd large_repo && dd if=/dev/urandom of=huge_file_1.bin bs=100M count=1 2>/dev/null
cd large_repo && dd if=/dev/urandom of=huge_file_2.bin bs=100M count=1 2>/dev/null
cd large_repo && mkdir -p src && for i in {1..500}; do dd if=/dev/urandom of=src/file_$i.dat bs=1M count=1 2>/dev/null; done
cp $ORIGINAL_CWD/assets/git_add_libgit2.cpp .
g++ -o large_git_add git_add_libgit2.cpp -lgit2
```

## Small Execution Commands

```bash
./small_git_add small_repo
```

## Large Execution Commands

```bash
./large_git_add large_repo
```

## Cleanup Commands

```bash
rm -rf small_repo/ large_repo/
```
