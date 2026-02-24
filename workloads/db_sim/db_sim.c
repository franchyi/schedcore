/*
 * db_sim - Multi-threaded database simulation workload
 *
 * Simulates a database with latency-sensitive "query" threads and
 * CPU-heavy "compaction" threads. Used to demonstrate thread-level
 * scheduling with sched-ext.
 *
 * Query threads: sleep briefly (simulating IO), then do a short CPU burst.
 * Compaction threads: continuous CPU-bound work.
 *
 * Usage: ./db_sim -q 8 -c 8 -d 10 -s 2000
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <unistd.h>
#include <time.h>
#include <math.h>
#include <getopt.h>
#include <signal.h>
#include <errno.h>

#define MAX_SAMPLES 1000000

static volatile int running = 1;

/* Configuration */
static int num_query = 8;
static int num_compact = 8;
static int duration_sec = 10;
static int sleep_us = 2000;  /* query thread sleep between iterations */

/* Per-thread stats */
struct query_stats {
    double *latencies_us;
    int count;
    int capacity;
};

struct compact_stats {
    unsigned long ops;
};

/* Thread arguments */
struct query_arg {
    int id;
    struct query_stats stats;
};

struct compact_arg {
    int id;
    struct compact_stats stats;
};

static void signal_handler(int sig)
{
    (void)sig;
    running = 0;
}

static double timespec_diff_us(struct timespec *start, struct timespec *end)
{
    return (end->tv_sec - start->tv_sec) * 1e6 +
           (end->tv_nsec - start->tv_nsec) / 1e3;
}

/* Short CPU burst ~0.5ms of math work */
static void cpu_burst(void)
{
    volatile double x = 1.0;
    for (int i = 0; i < 5000; i++) {
        x = sin(x) * cos(x) + sqrt(fabs(x));
    }
}

/* Heavy CPU work for compaction threads */
static void cpu_heavy_work(void)
{
    volatile double x = 1.0;
    for (int i = 0; i < 100000; i++) {
        x = sin(x) * cos(x) + sqrt(fabs(x));
    }
}

static void *query_thread(void *arg)
{
    struct query_arg *qa = (struct query_arg *)arg;
    char name[16];
    snprintf(name, sizeof(name), "query-%d", qa->id);
    pthread_setname_np(pthread_self(), name);

    qa->stats.capacity = MAX_SAMPLES;
    qa->stats.latencies_us = malloc(sizeof(double) * qa->stats.capacity);
    qa->stats.count = 0;

    struct timespec ts_sleep;
    ts_sleep.tv_sec = 0;

    while (running) {
        /* Simulate IO wait with variable sleep (sleep_us to sleep_us*2.5) */
        int jitter = sleep_us + (rand() % (sleep_us * 3 / 2));
        ts_sleep.tv_nsec = jitter * 1000L;
        nanosleep(&ts_sleep, NULL);

        /* Measure wakeup-to-completion latency */
        struct timespec t_start, t_end;
        clock_gettime(CLOCK_MONOTONIC, &t_start);
        cpu_burst();
        clock_gettime(CLOCK_MONOTONIC, &t_end);

        double lat = timespec_diff_us(&t_start, &t_end);

        if (qa->stats.count < qa->stats.capacity) {
            qa->stats.latencies_us[qa->stats.count++] = lat;
        }
    }

    return NULL;
}

static void *compact_thread(void *arg)
{
    struct compact_arg *ca = (struct compact_arg *)arg;
    char name[16];
    snprintf(name, sizeof(name), "compact-%d", ca->id);
    pthread_setname_np(pthread_self(), name);

    ca->stats.ops = 0;

    while (running) {
        cpu_heavy_work();
        ca->stats.ops++;
    }

    return NULL;
}

static int cmp_double(const void *a, const void *b)
{
    double da = *(const double *)a;
    double db = *(const double *)b;
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
}

static double percentile(double *sorted, int n, double p)
{
    if (n == 0) return 0.0;
    double idx = (p / 100.0) * (n - 1);
    int lo = (int)idx;
    int hi = lo + 1;
    if (hi >= n) return sorted[n - 1];
    double frac = idx - lo;
    return sorted[lo] * (1.0 - frac) + sorted[hi] * frac;
}

int main(int argc, char **argv)
{
    int opt;
    while ((opt = getopt(argc, argv, "q:c:d:s:h")) != -1) {
        switch (opt) {
        case 'q': num_query = atoi(optarg); break;
        case 'c': num_compact = atoi(optarg); break;
        case 'd': duration_sec = atoi(optarg); break;
        case 's': sleep_us = atoi(optarg); break;
        case 'h':
        default:
            fprintf(stderr, "Usage: %s [-q query_threads] [-c compact_threads] "
                    "[-d duration_sec] [-s sleep_us]\n", argv[0]);
            return opt == 'h' ? 0 : 1;
        }
    }

    fprintf(stderr, "db_sim: %d query threads, %d compact threads, %ds duration, %dus sleep\n",
            num_query, num_compact, duration_sec, sleep_us);

    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    srand(time(NULL));

    /* Allocate thread data */
    struct query_arg *qargs = calloc(num_query, sizeof(struct query_arg));
    struct compact_arg *cargs = calloc(num_compact, sizeof(struct compact_arg));
    pthread_t *query_tids = malloc(sizeof(pthread_t) * num_query);
    pthread_t *compact_tids = malloc(sizeof(pthread_t) * num_compact);

    /* Start threads */
    for (int i = 0; i < num_compact; i++) {
        cargs[i].id = i;
        pthread_create(&compact_tids[i], NULL, compact_thread, &cargs[i]);
    }
    for (int i = 0; i < num_query; i++) {
        qargs[i].id = i;
        pthread_create(&query_tids[i], NULL, query_thread, &qargs[i]);
    }

    /* Wait for duration */
    struct timespec ts_wait = { .tv_sec = 1, .tv_nsec = 0 };
    for (int t = 0; t < duration_sec && running; t++) {
        nanosleep(&ts_wait, NULL);
    }
    running = 0;

    /* Join threads */
    for (int i = 0; i < num_query; i++)
        pthread_join(query_tids[i], NULL);
    for (int i = 0; i < num_compact; i++)
        pthread_join(compact_tids[i], NULL);

    /* Aggregate query latencies */
    int total_samples = 0;
    for (int i = 0; i < num_query; i++)
        total_samples += qargs[i].stats.count;

    double *all_lat = malloc(sizeof(double) * (total_samples > 0 ? total_samples : 1));
    int idx = 0;
    for (int i = 0; i < num_query; i++) {
        for (int j = 0; j < qargs[i].stats.count; j++)
            all_lat[idx++] = qargs[i].stats.latencies_us[j];
    }

    qsort(all_lat, total_samples, sizeof(double), cmp_double);

    double avg = 0;
    for (int i = 0; i < total_samples; i++)
        avg += all_lat[i];
    if (total_samples > 0) avg /= total_samples;

    double p50 = percentile(all_lat, total_samples, 50);
    double p99 = percentile(all_lat, total_samples, 99);
    double max_lat = total_samples > 0 ? all_lat[total_samples - 1] : 0;
    double min_lat = total_samples > 0 ? all_lat[0] : 0;

    /* Aggregate compaction throughput */
    unsigned long total_ops = 0;
    for (int i = 0; i < num_compact; i++)
        total_ops += cargs[i].stats.ops;

    /* Output JSON to stdout */
    printf("{\n");
    printf("  \"config\": {\n");
    printf("    \"query_threads\": %d,\n", num_query);
    printf("    \"compact_threads\": %d,\n", num_compact);
    printf("    \"duration_sec\": %d,\n", duration_sec);
    printf("    \"sleep_us\": %d\n", sleep_us);
    printf("  },\n");
    printf("  \"query_latency_us\": {\n");
    printf("    \"samples\": %d,\n", total_samples);
    printf("    \"avg\": %.1f,\n", avg);
    printf("    \"min\": %.1f,\n", min_lat);
    printf("    \"p50\": %.1f,\n", p50);
    printf("    \"p99\": %.1f,\n", p99);
    printf("    \"max\": %.1f\n", max_lat);
    printf("  },\n");
    printf("  \"compaction_throughput\": {\n");
    printf("    \"total_ops\": %lu,\n", total_ops);
    printf("    \"ops_per_sec\": %.1f\n", (double)total_ops / duration_sec);
    printf("  }\n");
    printf("}\n");

    /* Cleanup */
    for (int i = 0; i < num_query; i++)
        free(qargs[i].stats.latencies_us);
    free(all_lat);
    free(qargs);
    free(cargs);
    free(query_tids);
    free(compact_tids);

    return 0;
}
