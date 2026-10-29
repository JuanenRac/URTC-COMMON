// =============================================================================
// URTC-COMMON - tests/c/test_ring.c
// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
// GPL-3.0-or-later - see LICENSE
// =============================================================================
// The shared single-producer / single-consumer byte ring (firmware_base/urtc_ring.h): its rules, one at a time, and, when
// built with -DURTC_RING_THREADS -pthread, a real producer thread against a real consumer thread. Compiled and run with
// the host compiler by tests/test_ring.py (and by the CI).
#include <stdint.h>
#include <stdio.h>

#include "urtc_ring.h"
#include "urtc_test.h"

#ifdef URTC_RING_THREADS
#include <pthread.h>

#define STRESS_BYTES 3000000u
static urtc_ring_t stress_ring;
static uint8_t stress_storage[64];

static void *producer(void *arg)
{
    (void)arg;
    for (uint32_t i = 0; i < STRESS_BYTES; i++) {
        while (!urtc_ring_put(&stress_ring, (uint8_t)(i * 7u + (i >> 8)))) {
            // full: the consumer is behind; try again (the drop counter counts these)
        }
    }
    return NULL;
}

static void stress(int *failures)
{
    pthread_t thread;
    urtc_ring_init(&stress_ring, stress_storage, 64);
    pthread_create(&thread, NULL, producer, NULL);
    uint32_t seen = 0;
    bool in_order = true;
    while (seen < STRESS_BYTES) {
        uint8_t byte;
        if (urtc_ring_get(&stress_ring, &byte)) {
            if (byte != (uint8_t)(seen * 7u + (seen >> 8))) {
                in_order = false;
            }
            seen++;
        }
    }
    pthread_join(thread, NULL);
    TEST_ASSERT(in_order, "three million bytes cross two threads in order, none lost, none repeated");
    TEST_ASSERT(urtc_ring_count(&stress_ring) == 0, "the ring ends empty");
}
#endif

int main(void)
{
    int count = 0;
    int *failures = &count;
    uint8_t storage[8];
    uint8_t byte = 0;
    urtc_ring_t ring;

    TEST_ASSERT(!urtc_ring_init(NULL, storage, 8), "init refuses a NULL ring");
    TEST_ASSERT(!urtc_ring_init(&ring, NULL, 8), "init refuses NULL storage");
    TEST_ASSERT(!urtc_ring_init(&ring, storage, 0), "init refuses size 0");
    TEST_ASSERT(!urtc_ring_init(&ring, storage, 1), "init refuses size 1");
    TEST_ASSERT(!urtc_ring_init(&ring, storage, 6), "init refuses a size that is not a power of two");
    TEST_ASSERT(!urtc_ring_init(&ring, storage, 65535), "init refuses a size past 32768");
    TEST_ASSERT(!urtc_ring_put(&ring, 1), "a ring that failed to initialise accepts nothing");
    TEST_ASSERT(!urtc_ring_get(&ring, &byte), "a ring that failed to initialise returns nothing");
    TEST_ASSERT(urtc_ring_count(&ring) == 0, "a ring that failed to initialise is empty");
    TEST_ASSERT(!urtc_ring_put(NULL, 1), "put on NULL is refused");
    TEST_ASSERT(!urtc_ring_get(NULL, &byte), "get on NULL is refused");
    TEST_ASSERT(urtc_ring_count(NULL) == 0, "count on NULL is zero");
    TEST_ASSERT(urtc_ring_take_dropped(NULL) == 0, "take_dropped on NULL is zero");

    TEST_ASSERT(urtc_ring_init(&ring, storage, 8), "a power-of-two size initialises");
    TEST_ASSERT(!urtc_ring_get(&ring, &byte), "an empty ring returns nothing");
    TEST_ASSERT(!urtc_ring_get(&ring, NULL), "get refuses a NULL destination");
    for (uint8_t i = 0; i < 7; i++) {
        TEST_ASSERT(urtc_ring_put(&ring, (uint8_t)(0x10 + i)), "seven bytes fit in a ring of eight");
    }
    TEST_ASSERT(urtc_ring_count(&ring) == 7, "the count is seven");
    TEST_ASSERT(!urtc_ring_put(&ring, 0xEE), "the eighth byte is dropped: one slot stays free");
    TEST_ASSERT(!urtc_ring_put(&ring, 0xEF), "so is the ninth");
    TEST_ASSERT(urtc_ring_take_dropped(&ring) == 2, "two bytes were dropped");
    TEST_ASSERT(urtc_ring_take_dropped(&ring) == 0, "the drop count is reported once");
    for (uint8_t i = 0; i < 7; i++) {
        TEST_ASSERT(urtc_ring_get(&ring, &byte) && byte == (uint8_t)(0x10 + i), "bytes come out in the order they went in");
    }
    TEST_ASSERT(!urtc_ring_get(&ring, &byte), "the ring is empty again");

    uint8_t next_in = 0;
    uint8_t next_out = 0;
    bool in_order = true;
    for (int round = 0; round < 1000; round++) {
        for (int i = 0; i < 1 + (round % 5); i++) {
            if (urtc_ring_put(&ring, next_in)) {
                next_in++;
            }
        }
        for (int i = 0; i < 1 + (round % 3); i++) {
            if (urtc_ring_get(&ring, &byte)) {
                in_order = in_order && byte == next_out;
                next_out++;
            }
        }
    }
    while (urtc_ring_get(&ring, &byte)) {
        in_order = in_order && byte == next_out;
        next_out++;
    }
    TEST_ASSERT(in_order, "thousands of interleaved bytes keep their order across the wrap");
    TEST_ASSERT(next_in == next_out, "nothing that was accepted is lost");

    urtc_ring_t small;
    uint8_t two[2];
    TEST_ASSERT(urtc_ring_init(&small, two, 2), "the smallest ring initialises");
    TEST_ASSERT(urtc_ring_put(&small, 1), "a ring of two holds one byte");
    TEST_ASSERT(!urtc_ring_put(&small, 2), "and drops the second");
    small.dropped = 0xFFFE;
    small.dropped_seen = 0xFFFE;
    TEST_ASSERT(!urtc_ring_put(&small, 3) && !urtc_ring_put(&small, 4) && !urtc_ring_put(&small, 5), "three more drops across the 16-bit wrap");
    TEST_ASSERT(urtc_ring_take_dropped(&small) == 3, "the count survives the wrap of the running counter");

#ifdef URTC_RING_THREADS
    stress(failures);
#endif
    if (count == 0) {
        printf("all ring tests pass\n");
        return 0;
    }
    printf("%d ring test(s) failed\n", count);
    return 1;
}
