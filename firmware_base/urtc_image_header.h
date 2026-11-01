// =============================================================================
// URTC-COMMON - firmware_base/urtc_image_header.h
// Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
// GPL-3.0-or-later - see LICENSE
// =============================================================================
// The header that goes in front of a firmware image, so a board, a bootloader or a tool can tell what a binary is before it trusts it: which hardware it is
// for, which version it is (four components: major.minor.patch.build), how long it is and what its CRC-32 is. 32 bytes, all multi-byte fields big-endian like
// the bus:
//
//    0  magic            4  "URIH" (0x55 0x52 0x49 0x48)
//    4  header_version   1  1
//    5  header_size      1  32
//    6  flags            2  bit 0: a 32-byte HMAC-SHA256 trailer follows the payload
//    8  hardware_id      4  the HardwareID the image is built for (src/common/urtc_can_ids.h)
//   12  version_major    2
//   14  version_minor    1
//   15  version_patch    1
//   16  version_build    2  the fourth component
//   18  reserved         2  0
//   20  payload_length   4  bytes of the image that follow the header (the trailer is not counted)
//   24  payload_crc32    4  CRC-32 (zlib: polynomial 0xEDB88320 reflected, start 0xFFFFFFFF, final XOR) of the payload
//   28  header_crc32     4  CRC-32 of bytes 0..27
//
// The signed metadata: the signature of an image (HMAC-SHA256) covers bytes 0..27 of the header followed by the payload, so the identity, the length and the
// CRC that the header states cannot be changed without invalidating it. The signature is made by the tooling that builds the release, never by this file.
//
// Header only, no library; the checks never read past the bytes they are given. Copied into the firmware repositories by tools/vendor_copy.py (set
// "firmware_image_header"); the reference in Python is src/urtc_common/image_header.py and the shared vectors are conformance/image_header_vectors.json. Nothing
// puts this header in an image yet: that is a change of the linker scripts and the post-build step of each firmware, to be made with a build on the bench.
#ifndef URTC_IMAGE_HEADER_H
#define URTC_IMAGE_HEADER_H

#include <stddef.h>
#include <stdint.h>

#define URTC_IMAGE_MAGIC            0x55524948u   // "URIH"
#define URTC_IMAGE_HEADER_VERSION   1u
#define URTC_IMAGE_HEADER_SIZE      32u
#define URTC_IMAGE_FLAG_SIGNED      0x0001u       // a 32-byte HMAC-SHA256 trailer follows the payload
#define URTC_IMAGE_SIGNATURE_SIZE   32u
#define URTC_IMAGE_SIGNED_HEADER    28u           // the bytes of the header the signature covers (all but the header CRC)

typedef enum {
    URTC_IMAGE_OK = 0,
    URTC_IMAGE_SHORT,             // fewer bytes than a header
    URTC_IMAGE_BAD_MAGIC,
    URTC_IMAGE_BAD_VERSION,       // a header version this reader does not know
    URTC_IMAGE_BAD_SIZE,          // the header does not say it is 32 bytes
    URTC_IMAGE_BAD_HEADER_CRC,
    URTC_IMAGE_BAD_LENGTH,        // the bytes after the header are not the payload (and trailer) the header announces
    URTC_IMAGE_BAD_PAYLOAD_CRC
} urtc_image_status_t;

typedef struct {
    uint32_t hardware_id;
    uint16_t version_major;
    uint8_t version_minor;
    uint8_t version_patch;
    uint16_t version_build;
    uint16_t flags;
    uint32_t payload_length;
    uint32_t payload_crc32;
} urtc_image_info_t;

// CRC-32 as zlib computes it: start the running value with 0xFFFFFFFF, feed the bytes, then XOR the result with 0xFFFFFFFF.
static inline uint32_t urtc_image_crc32_update(uint32_t crc, const uint8_t *data, size_t length)
{
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8u; bit++) {
            crc = (crc & 1u) ? ((crc >> 1) ^ 0xEDB88320u) : (crc >> 1);
        }
    }
    return crc;
}

static inline uint32_t urtc_image_crc32(const uint8_t *data, size_t length)
{
    return urtc_image_crc32_update(0xFFFFFFFFu, data, length) ^ 0xFFFFFFFFu;
}

static inline void urtc_image_put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }
static inline void urtc_image_put32(uint8_t *p, uint32_t v) { p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16); p[2] = (uint8_t)(v >> 8); p[3] = (uint8_t)v; }
static inline uint16_t urtc_image_get16(const uint8_t *p) { return (uint16_t)(((unsigned)p[0] << 8) | p[1]); }
static inline uint32_t urtc_image_get32(const uint8_t *p) { return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3]; }

// Writes the 32 bytes of the header of `info` (the header CRC included) into `out`.
static inline void urtc_image_header_pack(const urtc_image_info_t *info, uint8_t out[URTC_IMAGE_HEADER_SIZE])
{
    urtc_image_put32(out, URTC_IMAGE_MAGIC);
    out[4] = (uint8_t)URTC_IMAGE_HEADER_VERSION;
    out[5] = (uint8_t)URTC_IMAGE_HEADER_SIZE;
    urtc_image_put16(out + 6, info->flags);
    urtc_image_put32(out + 8, info->hardware_id);
    urtc_image_put16(out + 12, info->version_major);
    out[14] = info->version_minor;
    out[15] = info->version_patch;
    urtc_image_put16(out + 16, info->version_build);
    urtc_image_put16(out + 18, 0u);
    urtc_image_put32(out + 20, info->payload_length);
    urtc_image_put32(out + 24, info->payload_crc32);
    urtc_image_put32(out + 28, urtc_image_crc32(out, URTC_IMAGE_SIGNED_HEADER));
}

// Reads a header: checks the magic, the version, the size and the header CRC, and fills `info` only when they all hold. `length` is the number of bytes at
// `header` (at least URTC_IMAGE_HEADER_SIZE). The payload is not looked at.
static inline urtc_image_status_t urtc_image_header_parse(const uint8_t *header, size_t length, urtc_image_info_t *info)
{
    if (header == NULL || info == NULL || length < URTC_IMAGE_HEADER_SIZE) {
        return URTC_IMAGE_SHORT;
    }
    if (urtc_image_get32(header) != URTC_IMAGE_MAGIC) {
        return URTC_IMAGE_BAD_MAGIC;
    }
    if (header[4] != URTC_IMAGE_HEADER_VERSION) {
        return URTC_IMAGE_BAD_VERSION;
    }
    if (header[5] != URTC_IMAGE_HEADER_SIZE) {
        return URTC_IMAGE_BAD_SIZE;
    }
    if (urtc_image_get32(header + 28) != urtc_image_crc32(header, URTC_IMAGE_SIGNED_HEADER)) {
        return URTC_IMAGE_BAD_HEADER_CRC;
    }
    info->flags = urtc_image_get16(header + 6);
    info->hardware_id = urtc_image_get32(header + 8);
    info->version_major = urtc_image_get16(header + 12);
    info->version_minor = header[14];
    info->version_patch = header[15];
    info->version_build = urtc_image_get16(header + 16);
    info->payload_length = urtc_image_get32(header + 20);
    info->payload_crc32 = urtc_image_get32(header + 24);
    return URTC_IMAGE_OK;
}

// Reads the header and checks the whole image: `total` bytes must be exactly the header, the payload the header announces and, when the signed flag is set,
// the 32-byte trailer; and the payload must have the CRC-32 the header states. The trailer (the signature) is not checked here: that needs the key.
static inline urtc_image_status_t urtc_image_verify(const uint8_t *image, size_t total, urtc_image_info_t *info)
{
    urtc_image_info_t parsed;
    const urtc_image_status_t status = urtc_image_header_parse(image, total, &parsed);
    if (status != URTC_IMAGE_OK) {
        return status;
    }
    const size_t trailer = (parsed.flags & URTC_IMAGE_FLAG_SIGNED) ? URTC_IMAGE_SIGNATURE_SIZE : 0u;
    if ((uint64_t)parsed.payload_length + URTC_IMAGE_HEADER_SIZE + trailer != (uint64_t)total) {
        return URTC_IMAGE_BAD_LENGTH;
    }
    if (urtc_image_crc32(image + URTC_IMAGE_HEADER_SIZE, parsed.payload_length) != parsed.payload_crc32) {
        return URTC_IMAGE_BAD_PAYLOAD_CRC;
    }
    *info = parsed;
    return URTC_IMAGE_OK;
}

#endif // URTC_IMAGE_HEADER_H
