#include "tlsr_ota.h"

#if defined(MCU_CORE_826x)
#include "string.h"
#else
#include <string.h>
#endif

static uint16_t read_le16(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static uint32_t read_le32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

uint32_t tlsr_ota_crc32_update(uint32_t crc, const uint8_t *data, size_t len) {
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint32_t)data[i];
        for (uint8_t b = 0; b < 8; b++) {
            if (crc & 1U) {
                crc = (crc >> 1) ^ 0xEDB88320UL;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

uint8_t tlsr_ota_parse_header(const uint8_t hdr[32], struct tlsr_ota_image_meta *out) {
    if (hdr == NULL) {
        return TLSR_OTA_ERR_BAD_PARAM;
    }
    if (hdr[6] != TLSR_OTA_TELINK_MAGIC0 || hdr[7] != TLSR_OTA_TELINK_MAGIC1) {
        return TLSR_OTA_ERR_MAGIC;
    }
    /* Bytes 8..11 are 'K','N','L','T' (0x544C4E4B); byte 8 may be deferred (0xFF) in flash */
    if (hdr[9] != 0x4EU || hdr[10] != 0x4CU || hdr[11] != 0x54U) {
        return TLSR_OTA_ERR_MAGIC;
    }
    const uint32_t fw_size = read_le32(hdr + 0x18);
    if (fw_size < 64U || fw_size > TLSR_OTA_MAX_IMAGE_SIZE || (fw_size % 16U) != 4U) {
        return TLSR_OTA_ERR_SIZE;
    }
    if (out != NULL) {
        out->file_version = read_le32(hdr + 0x02);
        out->manufacturer_code = read_le16(hdr + 0x12);
        out->image_type = read_le16(hdr + 0x14);
        out->fw_size = fw_size;
        out->crc32 = 0;
    }
    return TLSR_OTA_OK;
}

uint8_t tlsr_ota_validate_buffer(const uint8_t *buf, size_t len,
                                 uint16_t expected_image_type, bool force_type,
                                 struct tlsr_ota_image_meta *out) {
    if (buf == NULL || len < 64U) {
        return TLSR_OTA_ERR_SIZE;
    }
    if (buf[TLSR_OTA_FLAG_OFFSET] != TLSR_OTA_FLAG_VALID) {
        return TLSR_OTA_ERR_MAGIC;
    }
    struct tlsr_ota_image_meta meta;
    const uint8_t st = tlsr_ota_parse_header(buf, &meta);
    if (st != TLSR_OTA_OK) {
        return st;
    }
    if ((size_t)meta.fw_size != len) {
        return TLSR_OTA_ERR_SIZE;
    }
    if (meta.manufacturer_code != TLSR_OTA_MFR_TELINK) {
        return TLSR_OTA_ERR_MAGIC;
    }
    if (!force_type && expected_image_type != 0U && meta.image_type != expected_image_type) {
        return TLSR_OTA_ERR_IMAGE_TYPE;
    }
    const uint32_t calc_crc = tlsr_ota_crc32_update(0xFFFFFFFFUL, buf, len - 4U);
    const uint32_t file_crc = read_le32(buf + len - 4U);
    if (calc_crc != file_crc) {
        return TLSR_OTA_ERR_CRC;
    }
    meta.crc32 = file_crc;
    if (out != NULL) {
        *out = meta;
    }
    return TLSR_OTA_OK;
}

static void notify_state(const struct tlsr_ota_ctx *ctx, bool active) {
    if (ctx->hal.on_state_change != NULL) {
        ctx->hal.on_state_change(active);
    }
}

static void wd_kick(const struct tlsr_ota_ctx *ctx) {
    if (ctx->hal.wd_clear != NULL) {
        ctx->hal.wd_clear();
    }
}

static void flash_write_paged(const struct tlsr_ota_ctx *ctx, uint32_t addr,
                              const uint8_t *buf, size_t len) {
    size_t off = 0;
    while (off < len) {
        const uint32_t page_rem = (uint32_t)(TLSR_OTA_PAGE_SIZE - (addr & (TLSR_OTA_PAGE_SIZE - 1U)));
        size_t chunk = len - off;
        if (chunk > page_rem) {
            chunk = page_rem;
        }
        ctx->hal.flash_write(addr, buf + off, chunk);
        addr += (uint32_t)chunk;
        off += chunk;
    }
}

void tlsr_ota_init(struct tlsr_ota_ctx *ctx, const tlsr_ota_hal_t *hal) {
    memset(ctx, 0, sizeof(*ctx));
    if (hal != NULL) {
        ctx->hal = *hal;
    }
    if (ctx->hal.max_chunk_size == 0U || ctx->hal.max_chunk_size > TLSR_OTA_MAX_CHUNK_CAP) {
        ctx->hal.max_chunk_size = TLSR_OTA_MAX_CHUNK_CAP;
    }
    ctx->state = TLSR_OTA_STATE_IDLE;
    ctx->last_erased_sector = 0xFFFFFFFFUL;
}

uint8_t tlsr_ota_active_bank(const struct tlsr_ota_ctx *ctx) {
    if (ctx == NULL || ctx->hal.flash_read == NULL) {
        return 0;
    }
    uint8_t flag = 0;
    ctx->hal.flash_read(TLSR_OTA_BANK0_ADDR + TLSR_OTA_FLAG_OFFSET, &flag, 1U);
    return (flag == TLSR_OTA_FLAG_VALID) ? 0U : 1U;
}

bool tlsr_ota_is_active(const struct tlsr_ota_ctx *ctx) {
    return ctx != NULL && ctx->state == TLSR_OTA_STATE_RECEIVING;
}

bool tlsr_ota_reboot_pending(const struct tlsr_ota_ctx *ctx) {
    return ctx != NULL && ctx->reboot_pending;
}

void tlsr_ota_handle_info(const struct tlsr_ota_ctx *ctx, struct tlsr_ota_info_resp *resp) {
    memset(resp, 0, sizeof(*resp));
    const uint8_t bank = tlsr_ota_active_bank(ctx);
    const uint32_t bank_addr = (bank == 0U) ? TLSR_OTA_BANK0_ADDR : TLSR_OTA_BANK1_ADDR;
    uint8_t ver_bytes[4] = {0};
    if (ctx->hal.flash_read != NULL) {
        ctx->hal.flash_read(bank_addr + 0x02UL, ver_bytes, 4U);
    }

    resp->proto_ver = TLSR_OTA_PROTO_VER;
    resp->active_bank = bank;
    resp->state = ctx->state;
    resp->flags = TLSR_OTA_INFO_FLAG_SUPPORTS_FORCE;
    resp->chip_id = ctx->hal.chip_id;
    resp->image_type = ctx->hal.image_type;
    resp->max_chunk_size = ctx->hal.max_chunk_size;
    resp->max_image_size = TLSR_OTA_MAX_IMAGE_SIZE;
    resp->active_file_version = read_le32(ver_bytes);
    resp->bytes_received = ctx->bytes_received;
}

void tlsr_ota_handle_begin(struct tlsr_ota_ctx *ctx, const struct tlsr_ota_begin_req *req,
                           struct tlsr_ota_begin_resp *resp) {
    memset(resp, 0, sizeof(*resp));
    if (ctx == NULL || req == NULL ||
        ctx->hal.flash_read == NULL || ctx->hal.flash_write == NULL ||
        ctx->hal.flash_erase_sector == NULL) {
        resp->status = TLSR_OTA_ERR_BAD_PARAM;
        return;
    }
    if (ctx->state == TLSR_OTA_STATE_COMMITTED) {
        resp->status = TLSR_OTA_ERR_STATE;
        return;
    }
    if (req->total_size < 64U || req->total_size > TLSR_OTA_MAX_IMAGE_SIZE ||
        (req->total_size % 16U) != 4U) {
        resp->status = TLSR_OTA_ERR_SIZE;
        return;
    }
    if ((req->flags & TLSR_OTA_FLAG_FORCE_TYPE) == 0U &&
        ctx->hal.image_type != 0U && req->image_type != ctx->hal.image_type) {
        resp->status = TLSR_OTA_ERR_IMAGE_TYPE;
        return;
    }

    const uint8_t active = tlsr_ota_active_bank(ctx);
    ctx->target_bank = (uint8_t)(active ^ 1U);
    ctx->target_addr = (ctx->target_bank == 0U) ? TLSR_OTA_BANK0_ADDR : TLSR_OTA_BANK1_ADDR;
    ctx->total_size = req->total_size;
    ctx->expected_crc32 = req->expected_crc32;
    ctx->flags = req->flags;
    ctx->bytes_received = 0;
    ctx->last_erased_sector = 0xFFFFFFFFUL;
    ctx->header_checked = false;
    ctx->reboot_pending = false;
    ctx->state = TLSR_OTA_STATE_RECEIVING;

    notify_state(ctx, true);

    resp->status = TLSR_OTA_OK;
    resp->target_bank = ctx->target_bank;
    resp->max_chunk_size = ctx->hal.max_chunk_size;
    resp->target_addr = ctx->target_addr;
}

static void abort_internal(struct tlsr_ota_ctx *ctx) {
    const bool was_active = (ctx->state == TLSR_OTA_STATE_RECEIVING);
    ctx->state = TLSR_OTA_STATE_IDLE;
    ctx->bytes_received = 0;
    ctx->header_checked = false;
    ctx->last_erased_sector = 0xFFFFFFFFUL;
    if (was_active) {
        notify_state(ctx, false);
    }
}

void tlsr_ota_handle_data(struct tlsr_ota_ctx *ctx, uint32_t offset, const uint8_t *data,
                          size_t data_len, struct tlsr_ota_data_resp *resp) {
    memset(resp, 0, sizeof(*resp));
    if (ctx == NULL || data == NULL || ctx->state != TLSR_OTA_STATE_RECEIVING) {
        resp->status = TLSR_OTA_ERR_STATE;
        if (ctx != NULL) resp->next_offset = ctx->bytes_received;
        return;
    }
    if (data_len == 0U || data_len > ctx->hal.max_chunk_size ||
        data_len > TLSR_OTA_MAX_CHUNK_CAP ||
        offset > ctx->total_size || data_len > (size_t)(ctx->total_size - offset)) {
        resp->status = TLSR_OTA_ERR_BAD_PARAM;
        resp->next_offset = ctx->bytes_received;
        return;
    }
    if (offset != ctx->bytes_received) {
        resp->status = TLSR_OTA_ERR_OFFSET;
        resp->next_offset = ctx->bytes_received;
        return;
    }

    uint8_t staged[TLSR_OTA_MAX_CHUNK_CAP];
    memcpy(staged, data, data_len);

    /* Defer boot flag 0x4B at image offset 0x08 until commit CRC-32 passes */
    if (offset <= TLSR_OTA_FLAG_OFFSET &&
        (offset + (uint32_t)data_len) > TLSR_OTA_FLAG_OFFSET) {
        const size_t flag_idx = (size_t)(TLSR_OTA_FLAG_OFFSET - offset);
        if (staged[flag_idx] != TLSR_OTA_FLAG_VALID) {
            abort_internal(ctx);
            resp->status = TLSR_OTA_ERR_MAGIC;
            resp->next_offset = 0;
            return;
        }
        staged[flag_idx] = 0xFFU;
    }

    const uint32_t write_start = ctx->target_addr + offset;
    const uint32_t write_end = write_start + (uint32_t)data_len;
    const uint32_t first_sec = write_start & ~(TLSR_OTA_SECTOR_SIZE - 1UL);
    const uint32_t last_sec = (write_end - 1UL) & ~(TLSR_OTA_SECTOR_SIZE - 1UL);
    for (uint32_t sec = first_sec; sec <= last_sec; sec += TLSR_OTA_SECTOR_SIZE) {
        if (sec != ctx->last_erased_sector) {
            wd_kick(ctx);
            ctx->hal.flash_erase_sector(sec);
            wd_kick(ctx);
            ctx->last_erased_sector = sec;
        }
    }

    flash_write_paged(ctx, write_start, staged, data_len);
    ctx->bytes_received += (uint32_t)data_len;

    /* Early header validation once first 32 bytes are in flash */
    if (!ctx->header_checked && ctx->bytes_received >= 32U) {
        uint8_t hdr[32];
        ctx->hal.flash_read(ctx->target_addr, hdr, sizeof(hdr));
        struct tlsr_ota_image_meta meta;
        uint8_t hst = tlsr_ota_parse_header(hdr, &meta);
        if (hst == TLSR_OTA_OK) {
            if (meta.fw_size != ctx->total_size) {
                hst = TLSR_OTA_ERR_SIZE;
            } else if (meta.manufacturer_code != TLSR_OTA_MFR_TELINK) {
                hst = TLSR_OTA_ERR_MAGIC;
            } else if ((ctx->flags & TLSR_OTA_FLAG_FORCE_TYPE) == 0U &&
                       ctx->hal.image_type != 0U &&
                       meta.image_type != ctx->hal.image_type) {
                hst = TLSR_OTA_ERR_IMAGE_TYPE;
            }
        }
        if (hst != TLSR_OTA_OK) {
            abort_internal(ctx);
            resp->status = hst;
            resp->next_offset = 0;
            return;
        }
        ctx->header_checked = true;
    }

    resp->status = TLSR_OTA_OK;
    resp->next_offset = ctx->bytes_received;
}

void tlsr_ota_handle_commit(struct tlsr_ota_ctx *ctx, const struct tlsr_ota_commit_req *req,
                            struct tlsr_ota_commit_resp *resp) {
    memset(resp, 0, sizeof(*resp));
    if (ctx == NULL || req == NULL || ctx->state != TLSR_OTA_STATE_RECEIVING) {
        resp->status = TLSR_OTA_ERR_STATE;
        return;
    }
    if (ctx->bytes_received != ctx->total_size || ctx->total_size < 64U) {
        resp->status = TLSR_OTA_ERR_SIZE;
        return;
    }

    /* Full flash read-back CRC-32 verification (with boot flag 0x4B restored at byte 8) */
    uint8_t buf[256];
    uint32_t crc = 0xFFFFFFFFUL;
    uint32_t rem = ctx->total_size - 4U;
    uint32_t addr = ctx->target_addr;
    bool first = true;
    while (rem > 0U) {
        const size_t chunk = (rem > sizeof(buf)) ? sizeof(buf) : (size_t)rem;
        wd_kick(ctx);
        ctx->hal.flash_read(addr, buf, chunk);
        if (first) {
            buf[TLSR_OTA_FLAG_OFFSET] = TLSR_OTA_FLAG_VALID;
            const uint8_t hst = tlsr_ota_parse_header(buf, NULL);
            if (hst != TLSR_OTA_OK) {
                abort_internal(ctx);
                resp->status = hst;
                return;
            }
            first = false;
        }
        crc = tlsr_ota_crc32_update(crc, buf, chunk);
        addr += (uint32_t)chunk;
        rem -= (uint32_t)chunk;
    }

    uint8_t tail[4] = {0};
    ctx->hal.flash_read(ctx->target_addr + ctx->total_size - 4U, tail, 4U);
    const uint32_t stored_crc = read_le32(tail);

    resp->calc_crc32 = crc;
    if (crc != stored_crc || crc != req->expected_crc32 || crc != ctx->expected_crc32) {
        abort_internal(ctx);
        resp->status = TLSR_OTA_ERR_CRC;
        return;
    }

    /* When committing Bank 1 (0x40000), ensure hardware ROM probe at 0x20008 is not 0x4B */
    if (ctx->target_addr == TLSR_OTA_BANK1_ADDR) {
        uint8_t mid_flag = 0xFFU;
        ctx->hal.flash_read(TLSR_OTA_MID_PROBE_ADDR + TLSR_OTA_FLAG_OFFSET, &mid_flag, 1U);
        if (mid_flag == TLSR_OTA_FLAG_VALID) {
            wd_kick(ctx);
            ctx->hal.flash_erase_sector(TLSR_OTA_MID_PROBE_ADDR);
            wd_kick(ctx);
        }
    }

    /* Activate target bank first, read-verify 0x4B, then invalidate old bank */
    const uint8_t flag_valid = TLSR_OTA_FLAG_VALID;
    uint8_t verify_flag = 0;
    ctx->hal.flash_write(ctx->target_addr + TLSR_OTA_FLAG_OFFSET, &flag_valid, 1U);
    ctx->hal.flash_read(ctx->target_addr + TLSR_OTA_FLAG_OFFSET, &verify_flag, 1U);
    if (verify_flag != TLSR_OTA_FLAG_VALID) {
        abort_internal(ctx);
        resp->status = TLSR_OTA_ERR_FLASH;
        return;
    }

    const uint32_t old_addr = (ctx->target_bank == 0U) ? TLSR_OTA_BANK1_ADDR : TLSR_OTA_BANK0_ADDR;
    const uint8_t zero4[4] = {0, 0, 0, 0};
    uint8_t verify_old = 0xFFU;
    ctx->hal.flash_write(old_addr + TLSR_OTA_FLAG_OFFSET, zero4, sizeof(zero4));
    ctx->hal.flash_read(old_addr + TLSR_OTA_FLAG_OFFSET, &verify_old, 1U);
    if (verify_old != 0x00U) {
        abort_internal(ctx);
        resp->status = TLSR_OTA_ERR_FLASH;
        return;
    }

    ctx->state = TLSR_OTA_STATE_COMMITTED;
    ctx->reboot_pending = true;

    resp->status = TLSR_OTA_OK;
    resp->new_bank = ctx->target_bank;
}

void tlsr_ota_handle_abort(struct tlsr_ota_ctx *ctx) {
    if (ctx == NULL) {
        return;
    }
    abort_internal(ctx);
}
