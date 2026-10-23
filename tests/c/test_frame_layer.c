// =============================================================================
// URTC-COMMON - tests/c/test_frame_layer.c
// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
// GPL-3.0-or-later - see LICENSE
// =============================================================================
// The shared frame layer and rate limiter held to the shared vectors: every parse vector of the rack and of the vision sensor,
// every frame the reference module builds (rebuilt here byte for byte), and every decision of the rate limiter. Compiled and run
// with the host compiler by tests/test_frame_layer.py (and by the CI).
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "urtc_frame.h"
#include "urtc_rate_limiter.h"
#include "urtc_test.h"

#include "rack_vectors.h"
#include "rate_vectors.h"
#include "sensor_vectors.h"

static const urtc_frame_format_t RACK = {0xA5u, 2u, 4u, 16u};
static const urtc_frame_format_t SENSOR = {0xB6u, 2u, 8u, 16u};

static void parse_vectors(int *failures)
{
    for (int i = 0; i < RACK_VEC_COUNT(RACK_VEC_PARSE); i++) {
        const rack_vec_parse_t *v = &RACK_VEC_PARSE[i];
        uint8_t total = 0;
        const urtc_frame_status_t status = urtc_frame_validate(&RACK, v->buf, v->len, &total);
        TEST_ASSERT((int)status == v->status, v->name);
        TEST_ASSERT(status == URTC_FRAME_OK ? total == v->len : total == 0, "the length is reported only for a good frame");
    }
    for (int i = 0; i < SENSOR_VEC_COUNT(SENSOR_VEC_PARSE); i++) {
        const sensor_vec_parse_t *v = &SENSOR_VEC_PARSE[i];
        uint8_t total = 0;
        const urtc_frame_status_t status = urtc_frame_validate(&SENSOR, v->buf, v->len, &total);
        TEST_ASSERT((int)status == v->status, v->name);
        TEST_ASSERT(status == URTC_FRAME_OK ? total == v->len : total == 0, "the length is reported only for a good frame");
    }
}

static void build_vectors(int *failures)
{
    for (int i = 0; i < RACK_VEC_COUNT(RACK_VEC_FRAMES); i++) {
        const rack_vec_frame_t *v = &RACK_VEC_FRAMES[i];
        uint8_t buf[32] = {0};
        urtc_frame_start(&RACK, buf, v->payload_len);
        buf[2] = v->seq;
        buf[3] = v->cmd;
        memcpy(&buf[5], v->payload, v->payload_len);
        const uint8_t size = urtc_frame_seal(&RACK, buf, v->payload_len);
        TEST_ASSERT(size == v->frame_len && memcmp(buf, v->frame, v->frame_len) == 0, v->name);
        TEST_ASSERT(size == urtc_frame_total_size(&RACK, v->payload_len), "the total size agrees with the sealed size");
        uint8_t total = 0;
        TEST_ASSERT(urtc_frame_validate(&RACK, buf, size, &total) == URTC_FRAME_OK && total == size, "a sealed frame validates");
    }
    for (int i = 0; i < SENSOR_VEC_COUNT(SENSOR_VEC_FRAMES); i++) {
        const sensor_vec_frame_t *v = &SENSOR_VEC_FRAMES[i];
        uint8_t buf[32] = {0};
        urtc_frame_start(&SENSOR, buf, v->payload_len);
        buf[2] = v->sensor_id;
        buf[3] = v->seq;
        buf[4] = (uint8_t)(v->timestamp_ms >> 24);
        buf[5] = (uint8_t)(v->timestamp_ms >> 16);
        buf[6] = (uint8_t)(v->timestamp_ms >> 8);
        buf[7] = (uint8_t)v->timestamp_ms;
        memcpy(&buf[9], v->payload, v->payload_len);
        const uint8_t size = urtc_frame_seal(&SENSOR, buf, v->payload_len);
        TEST_ASSERT(size == v->frame_len && memcmp(buf, v->frame, v->frame_len) == 0, v->name);
        uint8_t total = 0;
        TEST_ASSERT(urtc_frame_validate(&SENSOR, buf, size, &total) == URTC_FRAME_OK && total == size, "a sealed frame validates");
    }
}

static void edges(int *failures)
{
    uint8_t total = 7;
    uint8_t frame[32];
    urtc_frame_start(&RACK, frame, 0);
    frame[2] = 1;
    frame[3] = 2;
    const uint8_t size = urtc_frame_seal(&RACK, frame, 0);
    TEST_ASSERT(size == 6u, "the smallest rack frame has six bytes");
    // bytes after the frame are not looked at
    uint8_t padded[32];
    memcpy(padded, frame, size);
    memset(&padded[size], 0xEE, 8);
    total = 0;
    TEST_ASSERT(urtc_frame_validate(&RACK, padded, (uint8_t)(size + 8u), &total) == URTC_FRAME_OK && total == size, "trailing bytes are ignored");
    // the same bytes read as the other format are refused at the start byte, not trusted
    total = 9;
    TEST_ASSERT(urtc_frame_validate(&SENSOR, frame, size, &total) == URTC_FRAME_INCOMPLETE && total == 9u, "too short for the other format");
    // a failed check leaves the length alone
    uint8_t bad[6];
    memcpy(bad, frame, 6);
    bad[5] ^= 0xFFu;
    total = 9;
    TEST_ASSERT(urtc_frame_validate(&RACK, bad, 6, &total) == URTC_FRAME_CRC_MISMATCH && total == 9u, "a refused frame leaves the length alone");
    // missing arguments fail closed
    TEST_ASSERT(urtc_frame_validate(NULL, frame, size, &total) == URTC_FRAME_INCOMPLETE, "no format");
    TEST_ASSERT(urtc_frame_validate(&RACK, NULL, size, &total) == URTC_FRAME_INCOMPLETE, "no buffer");
    TEST_ASSERT(urtc_frame_validate(&RACK, frame, size, NULL) == URTC_FRAME_INCOMPLETE, "no length");
    TEST_ASSERT(urtc_frame_header_size(&RACK) == 5u && urtc_frame_header_size(&SENSOR) == 9u, "the header sizes");
}

static void rate_vectors(int *failures)
{
    for (int i = 0; i < RATE_VEC_COUNT(RATE_VEC_CASES); i++) {
        const rate_vec_case_t *c = &RATE_VEC_CASES[i];
        urtc_rate_limiter_t limiter;
        urtc_rate_limiter_init(&limiter, c->min_interval_ms);
        for (int k = 0; k < c->count; k++) {
            const int allowed = urtc_rate_limiter_allow(&limiter, c->times_ms[k]) ? 1 : 0;
            TEST_ASSERT(allowed == c->allowed[k], c->name);
        }
    }
    urtc_rate_limiter_init(NULL, 10);  // must not crash
    TEST_ASSERT(!urtc_rate_limiter_allow(NULL, 0), "a missing limiter never allows");
}

int main(void)
{
    int failures = 0;
    parse_vectors(&failures);
    build_vectors(&failures);
    edges(&failures);
    rate_vectors(&failures);
    if (failures != 0) {
        printf("FAILED: %d assertion(s)\n", failures);
        return 1;
    }
    printf("frame layer and rate limiter: all vectors pass\n");
    return 0;
}
