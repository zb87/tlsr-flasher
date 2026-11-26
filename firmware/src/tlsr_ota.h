#pragma once

/**
 * @file tlsr_ota.h
 * @brief Shared dual-bank (0x00000 / 0x40000) OTA state machine and Telink image validator.
 *
 * Shared identically by:
 *   - oepl-ap/tlsr (TLSR8258 over OEPL v2 COBS UART)
 *   - oepl-ap/esp32 (ESP32 host pre-validator & streamer)
 *   - tlsr-flasher/firmware (TLSR8269 over USB-CDC TLSRPGM)
 */

#if defined(MCU_CORE_826x)
#include "types.h"
#include <stdint.h>
#else
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

#define TLSR_OTA_PROTO_VER          1U

#define TLSR_OTA_BANK0_ADDR         0x00000UL
#define TLSR_OTA_BANK1_ADDR         0x40000UL
#define TLSR_OTA_MID_PROBE_ADDR     0x20000UL
#define TLSR_OTA_MAX_IMAGE_SIZE     0x20000UL /* 128 KB max per bank */
#define TLSR_OTA_SECTOR_SIZE        0x1000UL  /* 4 KB SPI flash sector */
#define TLSR_OTA_PAGE_SIZE          0x100UL   /* 256 B SPI flash page */
#define TLSR_OTA_FLAG_OFFSET        0x08UL
#define TLSR_OTA_FLAG_VALID         0x4BU

#define TLSR_OTA_TELINK_MAGIC0      0x5DU
#define TLSR_OTA_TELINK_MAGIC1      0x02U
#define TLSR_OTA_MFR_TELINK         0x1141U
#define TLSR_OTA_MAX_CHUNK_CAP      256U

enum tlsr_ota_cmd {
    TLSR_OTA_CMD_INFO   = 0x01,
    TLSR_OTA_CMD_BEGIN  = 0x02,
    TLSR_OTA_CMD_DATA   = 0x03,
    TLSR_OTA_CMD_COMMIT = 0x04,
    TLSR_OTA_CMD_ABORT  = 0x05,
};

enum tlsr_ota_state {
    TLSR_OTA_STATE_IDLE      = 0,
    TLSR_OTA_STATE_RECEIVING = 1,
    TLSR_OTA_STATE_COMMITTED = 2,
};

enum tlsr_ota_status {
    TLSR_OTA_OK             = 0,
    TLSR_OTA_ERR_STATE      = 1,
    TLSR_OTA_ERR_BAD_PARAM  = 2,
    TLSR_OTA_ERR_SIZE       = 3,
    TLSR_OTA_ERR_MAGIC      = 4,
    TLSR_OTA_ERR_IMAGE_TYPE = 5,
    TLSR_OTA_ERR_OFFSET     = 6,
    TLSR_OTA_ERR_CRC        = 7,
    TLSR_OTA_ERR_FLASH      = 8,
};

#define TLSR_OTA_FLAG_FORCE_TYPE         0x01U
#define TLSR_OTA_INFO_FLAG_SUPPORTS_FORCE 0x01U

#ifndef __packed
#define __packed __attribute__((packed))
#endif

struct __packed tlsr_ota_info_resp {
    uint8_t proto_ver;
    uint8_t active_bank;
    uint8_t state;
    uint8_t flags;
    uint16_t chip_id;
    uint16_t image_type;
    uint16_t max_chunk_size;
    uint16_t reserved;
    uint32_t max_image_size;
    uint32_t active_file_version;
    uint32_t bytes_received;
};

struct __packed tlsr_ota_begin_req {
    uint32_t total_size;
    uint32_t expected_crc32;
    uint16_t image_type;
    uint8_t flags;
    uint8_t reserved;
};

struct __packed tlsr_ota_begin_resp {
    uint8_t status;
    uint8_t target_bank;
    uint16_t max_chunk_size;
    uint32_t target_addr;
};

struct __packed tlsr_ota_data_req {
    uint32_t offset;
    uint8_t bytes[];
};

struct __packed tlsr_ota_data_resp {
    uint8_t status;
    uint8_t reserved[3];
    uint32_t next_offset;
};

struct __packed tlsr_ota_commit_req {
    uint32_t expected_crc32;
};

struct __packed tlsr_ota_commit_resp {
    uint8_t status;
    uint8_t new_bank;
    uint8_t reserved[2];
    uint32_t calc_crc32;
};

#ifdef __cplusplus
#define TLSR_OTA_STATIC_ASSERT(cond, msg) static_assert(cond, msg)
#elif defined(__STDC_VERSION__) && __STDC_VERSION__ >= 201112L
#define TLSR_OTA_STATIC_ASSERT(cond, msg) _Static_assert(cond, msg)
#else
#define TLSR_OTA_STATIC_ASSERT_CAT_(a, b) a##b
#define TLSR_OTA_STATIC_ASSERT_CAT(a, b) TLSR_OTA_STATIC_ASSERT_CAT_(a, b)
#define TLSR_OTA_STATIC_ASSERT(cond, msg) typedef char TLSR_OTA_STATIC_ASSERT_CAT(tlsr_ota_sa_, __LINE__)[(cond) ? 1 : -1]
#endif

TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_info_resp) == 24, "tlsr_ota_info_resp size");
TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_begin_req) == 12, "tlsr_ota_begin_req size");
TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_begin_resp) == 8, "tlsr_ota_begin_resp size");
TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_data_req) == 4, "tlsr_ota_data_req size");
TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_data_resp) == 8, "tlsr_ota_data_resp size");
TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_commit_req) == 4, "tlsr_ota_commit_req size");
TLSR_OTA_STATIC_ASSERT(sizeof(struct tlsr_ota_commit_resp) == 8, "tlsr_ota_commit_resp size");

struct tlsr_ota_image_meta {
    uint32_t file_version;
    uint16_t manufacturer_code;
    uint16_t image_type;
    uint32_t fw_size;
    uint32_t crc32;
};

typedef struct tlsr_ota_hal {
    void (*flash_read)(uint32_t addr, uint8_t *buf, size_t len);
    void (*flash_write)(uint32_t addr, const uint8_t *buf, size_t len);
    void (*flash_erase_sector)(uint32_t addr);
    void (*wd_clear)(void);
    void (*on_state_change)(bool ota_active);
    uint16_t chip_id;
    uint16_t image_type;
    uint16_t max_chunk_size;
} tlsr_ota_hal_t;

struct tlsr_ota_ctx {
    tlsr_ota_hal_t hal;
    uint8_t state;
    uint8_t target_bank;
    uint8_t flags;
    bool header_checked;
    bool reboot_pending;
    uint32_t target_addr;
    uint32_t total_size;
    uint32_t expected_crc32;
    uint32_t bytes_received;
    uint32_t last_erased_sector;
};

/* Host & target image validation helpers (no flash HAL required) */
uint32_t tlsr_ota_crc32_update(uint32_t crc, const uint8_t *data, size_t len);

/* Parses 32-byte Telink header; returns TLSR_OTA_OK or TLSR_OTA_ERR_MAGIC/SIZE. */
uint8_t tlsr_ota_parse_header(const uint8_t hdr[32], struct tlsr_ota_image_meta *out);

/* Validates an entire firmware buffer in memory (header, image_type, size, and CRC-32). */
uint8_t tlsr_ota_validate_buffer(const uint8_t *buf, size_t len,
                                 uint16_t expected_image_type, bool force_type,
                                 struct tlsr_ota_image_meta *out);

/* Target state machine */
void tlsr_ota_init(struct tlsr_ota_ctx *ctx, const tlsr_ota_hal_t *hal);
uint8_t tlsr_ota_active_bank(const struct tlsr_ota_ctx *ctx);
bool tlsr_ota_is_active(const struct tlsr_ota_ctx *ctx);
bool tlsr_ota_reboot_pending(const struct tlsr_ota_ctx *ctx);

void tlsr_ota_handle_info(const struct tlsr_ota_ctx *ctx, struct tlsr_ota_info_resp *resp);
void tlsr_ota_handle_begin(struct tlsr_ota_ctx *ctx, const struct tlsr_ota_begin_req *req,
                           struct tlsr_ota_begin_resp *resp);
void tlsr_ota_handle_data(struct tlsr_ota_ctx *ctx, uint32_t offset, const uint8_t *data,
                          size_t data_len, struct tlsr_ota_data_resp *resp);
void tlsr_ota_handle_commit(struct tlsr_ota_ctx *ctx, const struct tlsr_ota_commit_req *req,
                            struct tlsr_ota_commit_resp *resp);
void tlsr_ota_handle_abort(struct tlsr_ota_ctx *ctx);

#ifdef __cplusplus
}
#endif
