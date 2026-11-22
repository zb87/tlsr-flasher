#pragma once

#include "tl_common.h"

/* TLSRPGM error codes (must match TlsrPgm.py) */
enum {
    PGM_ERR_NONE = 0,
    PGM_ERR_FUNC = 1,
    PGM_ERR_LEN  = 2,
    PGM_ERR_READ = 3,
    PGM_ERR_BUSY = 4,
    PGM_ERR_CRC  = 5,
    PGM_ERR_BAUD = 6,
};

void swm_init(void);
void swm_set_cfg(u8 swdiv, u8 addrlen, const u8 swbuf[6]);
u8   swm_get_swdiv(void);
u8   swm_get_addrlen(void);
void swm_get_swbuf(u8 out[6]);

u8 swm_activate(u16 count, u8 out_pc[4]);

u8 swm_read(u32 addr, u8 *buf, u16 len, u8 fifo_mode);
u8 swm_write(u32 addr, const u8 *buf, u16 len, u8 fifo_mode);

u8 swm_aread(u8 addr, u8 *buf, u16 len);
u8 swm_awrite(u8 addr, const u8 *buf, u16 len);

u8 swm_flash_read(u32 addr, u8 *buf, u16 len);
u8 swm_flash_write(u32 addr, const u8 *buf, u16 len);
u8 swm_flash_erase_sector(u32 addr);
u8 swm_flash_erase_all(void);
u8 swm_flash_jedec_id(u8 out_id[3]);
u8 swm_flash_status(u8 *out_status);
u8 swm_flash_wrrd(const u8 *wr, u16 wr_len, u8 *rd, u16 rd_len);
