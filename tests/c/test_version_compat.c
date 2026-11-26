// =============================================================================
// URTC-COMMON - tests/c/test_version_compat.c
// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
// GPL-3.0-or-later - see LICENSE
// =============================================================================
// [FIRMWARE] not built for the board and not flashed: host tests of the signed command that changes the version rule (firmware_base/urtc_version_compat.h),
// held to the shared vectors (generated/version_compat_vectors.h, written by tools/make_version_compat_vectors.py). Built by tests/test_version_compat.py with
// the host compiler and firmware_base/urtc_ed25519.c.
#include <stdio.h>
#include <string.h>

#include "urtc_test.h"
#include "urtc_version_compat.h"
#include "version_compat_vectors.h"

static void test_commands(int *failures)
{
    for (size_t i = 0; i < VERSION_COMPAT_COMMAND_VECTOR_COUNT; i++) {
        const version_compat_command_vec_t *v = &VERSION_COMPAT_COMMAND_VECTORS[i];
        uint8_t keys[2][URTC_ED25519_PUBLIC_KEY_SIZE];
        uint8_t count = 0;
        for (unsigned k = 0; k < 2u; k++) {
            if (v->trusted_mask & (1u << k)) memcpy(keys[count++], VERSION_COMPAT_KEYS[k], URTC_ED25519_PUBLIC_KEY_SIZE);
        }
        uint32_t mode = 0u, counter = 0u;
        const urtc_vc_status_t got = urtc_vc_decide(v->command, v->uid, v->current_serial, (const uint8_t (*)[URTC_ED25519_PUBLIC_KEY_SIZE])keys, count,
                                                    v->stored_counter, v->enabled, v->busy, &mode, &counter);
        TEST_ASSERT((int)got == v->status, v->name);
        TEST_ASSERT(mode == v->mode && counter == v->counter, "mode and counter are written only by an accepted command");
    }
}

static void test_records(int *failures)
{
    for (size_t i = 0; i < VERSION_COMPAT_RECORD_VECTOR_COUNT; i++) {
        const version_compat_record_vec_t *v = &VERSION_COMPAT_RECORD_VECTORS[i];
        uint32_t mode = 99u, counter = 99u;
        TEST_ASSERT(urtc_vc_record_read(v->record, &mode, &counter) == v->valid, v->name);
        TEST_ASSERT(mode == v->mode && counter == v->counter, "a record that is refused reads as nothing stored");
        if (v->valid) {
            uint8_t again[URTC_VC_RECORD_SIZE];
            urtc_vc_record_pack(v->mode, v->counter, again);
            TEST_ASSERT(memcmp(again, v->record, URTC_VC_RECORD_SIZE) == 0, "the record is packed as it is read");
        }
    }
}

static void test_the_rule_in_force(int *failures)
{
    TEST_ASSERT(urtc_vc_effective_mode(URTC_VC_MODE_NONE, 1) == URTC_VC_MODE_STRICT, "nothing stored: the strict rule of the default build");
    TEST_ASSERT(urtc_vc_effective_mode(URTC_VC_MODE_NONE, 0) == URTC_VC_MODE_ACCEPT_PATCHLESS, "nothing stored in a build made lenient: lenient");
    TEST_ASSERT(urtc_vc_effective_mode(URTC_VC_MODE_ACCEPT_PATCHLESS, 1) == URTC_VC_MODE_ACCEPT_PATCHLESS, "a stored mode wins over the build");
    TEST_ASSERT(urtc_vc_effective_mode(URTC_VC_MODE_STRICT, 0) == URTC_VC_MODE_STRICT, "both ways");
    TEST_ASSERT(urtc_vc_effective_mode(77u, 1) == URTC_VC_MODE_STRICT, "a mode that does not exist is nothing stored");
    TEST_ASSERT(urtc_vc_unknown_is_zero(URTC_VC_MODE_STRICT) && !urtc_vc_unknown_is_zero(URTC_VC_MODE_ACCEPT_PATCHLESS), "only the lenient mode relaxes");

    uint8_t answer[URTC_VC_ANSWER_SIZE];
    const uint8_t expected[URTC_VC_ANSWER_SIZE] = {0xC5, 0x03, 0x02, 0x01, 0x01, 0x02, 0x03, 0x04};
    urtc_vc_answer_build(answer, URTC_VC_REPLAY, URTC_VC_MODE_ACCEPT_PATCHLESS, 1, 0x01020304u);
    TEST_ASSERT(memcmp(answer, expected, sizeof answer) == 0, "the answer frame");
}

int main(void)
{
    int failures = 0;
    printf("version rule command\n");
    test_commands(&failures);
    test_records(&failures);
    test_the_rule_in_force(&failures);
    if (failures == 0) printf("all version compatibility tests pass\n");
    return failures == 0 ? 0 : 1;
}
