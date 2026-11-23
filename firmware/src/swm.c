#include "swm.h"
#include "board_tlsr_flasher.h"
#include "usb_cdc.h"

static u8 s_swdiv     = PGM_DEFAULT_SWDIV;
static u8 s_swaddrlen = PGM_DEFAULT_ADDRLEN;
static u8 s_swbuf[6]  = {0x5A, 0x00, 0x06, 0x02, 0x00, 0x05};

static void swm_hw_reset(void)
{
    reg_swire_ctrl1 = 0;
    reg_rst0_16 |= FLD_RST_SWR_M;
    reg_rst0_16 &= (u16)(~FLD_RST_SWR_M);
    reg_swire_clk_div = s_swdiv & 0x7F;
}

static void swm_begin_session(void)
{
    board_swm_enable();
}

static void swm_end_session(void)
{
    if (!board_get_pwr_en()) {
        board_swm_float();
    }
}

static u8 swm_wait_wr(void)
{
    u32 t0 = clock_time();
    while (reg_swire_ctrl1 & FLD_SWIRE_WR) {
        if (clock_time_exceed(t0, 500)) {
            swm_hw_reset();
            return 0;
        }
    }
    return 1;
}

static u8 swm_tx_cmd(u8 b)
{
    reg_swire_data  = b;
    reg_swire_ctrl1 = FLD_SWIRE_CMD | FLD_SWIRE_WR;
    return swm_wait_wr();
}

static u8 swm_tx_data(u8 b)
{
    reg_swire_data  = b;
    reg_swire_ctrl1 = FLD_SWIRE_WR;
    return swm_wait_wr();
}

static u8 swm_rx_data(u8 *out)
{
    u32 timeout_us = 250U + ((u32)s_swdiv * 40U);
    reg_swire_ctrl1 = FLD_SWIRE_RD;
    u32 t0 = clock_time();
    while (reg_swire_ctrl1 & FLD_SWIRE_RD) {
        if (clock_time_exceed(t0, timeout_us)) {
            swm_hw_reset();
            return 0;
        }
    }
    *out = reg_swire_data;
    return 1;
}

static u8 swm_send_hdr(u32 addr, u8 op_byte)
{
    if (!swm_tx_cmd(0x5A)) {
        return 0;
    }
    if (s_swaddrlen == 3) {
        if (!swm_tx_data((u8)((addr >> 16) & 0xFF))) {
            return 0;
        }
    }
    if (!swm_tx_data((u8)((addr >> 8) & 0xFF))) {
        return 0;
    }
    if (!swm_tx_data((u8)(addr & 0xFF))) {
        return 0;
    }
    /* Preserve slave_id[4:0] from s_swbuf[4] while setting bit 7 for read (0x80) vs write (0x00) */
    if (!swm_tx_data((u8)((op_byte & 0x80) | (s_swbuf[4] & 0x1F)))) {
        return 0;
    }
    return 1;
}

static void swm_stop(void)
{
    swm_tx_cmd(0xFF);
}

static u8 swm_write_raw(u32 addr, const u8 *buf, u16 len)
{
    if (!swm_send_hdr(addr, 0x00)) {
        swm_stop();
        return PGM_ERR_READ;
    }
    for (u16 i = 0; i < len; i++) {
        if (!swm_tx_data(buf[i])) {
            swm_stop();
            return PGM_ERR_READ;
        }
    }
    swm_stop();
    return PGM_ERR_NONE;
}

static u8 swm_read_raw(u32 addr, u8 *buf, u16 len)
{
    if (!swm_send_hdr(addr, 0x80)) {
        swm_stop();
        return PGM_ERR_READ;
    }
    for (u16 i = 0; i < len; i++) {
        if (!swm_rx_data(&buf[i])) {
            swm_stop();
            return PGM_ERR_READ;
        }
    }
    swm_stop();
    return PGM_ERR_NONE;
}

static u8 swm_write_u8_raw(u32 addr, u8 val)
{
    return swm_write_raw(addr, &val, 1);
}

static u8 swm_read_u8_raw(u32 addr, u8 *val)
{
    return swm_read_raw(addr, val, 1);
}

static u8 swm_set_target_fifo(u8 en)
{
    return swm_write_u8_raw(0x00B3, en ? 0x80 : 0x00);
}

static u8 swm_flash_wren(void)
{
    u8 err = swm_write_u8_raw(0x000D, 0x00);
    if (err != PGM_ERR_NONE) {
        return err;
    }
    err = swm_write_u8_raw(0x000C, 0x06);
    swm_write_u8_raw(0x000D, 0x01);
    return err;
}

void swm_init(void)
{
    reg_clk_en |= FLD_CLK_SWIRE_EN;
    s_swdiv     = PGM_DEFAULT_SWDIV;
    s_swaddrlen = PGM_DEFAULT_ADDRLEN;
    swm_hw_reset();
}

void swm_set_cfg(u8 swdiv, u8 addrlen, const u8 swbuf[6])
{
    if (swdiv < 1) {
        swdiv = 1;
    } else if (swdiv > 127) {
        swdiv = 127;
    }
    s_swdiv     = swdiv;
    s_swaddrlen = (addrlen == 2) ? 2 : 3;
    memcpy(s_swbuf, swbuf, 6);
    reg_swire_clk_div = s_swdiv;
}

u8 swm_get_swdiv(void)
{
    return s_swdiv;
}

u8 swm_get_addrlen(void)
{
    return s_swaddrlen;
}

void swm_get_swbuf(u8 out[6])
{
    memcpy(out, s_swbuf, 6);
}

u8 swm_activate(u16 count, u8 out_pc[4])
{
    board_set_ext_rst(1);
    board_set_pwr_en(1);
    swm_begin_session();
    sleep_us(2000);

    for (u16 i = 0; i < count; i++) {
        swm_tx_cmd(s_swbuf[0]);
        if (s_swaddrlen == 3) {
            swm_tx_data(s_swbuf[1]);
        }
        swm_tx_data(s_swbuf[2]);
        swm_tx_data(s_swbuf[3]);
        swm_tx_data(s_swbuf[4]);
        swm_tx_data(s_swbuf[5]);
        swm_stop();
        if ((i & 0x7F) == 0x7F) {
            usb_cdc_poll();
        }
    }

    sleep_us(1000);
    u8 err = swm_read_raw(0x06BC, out_pc, 4);
    swm_end_session();
    return err;
}

u8 swm_read(u32 addr, u8 *buf, u16 len, u8 fifo_mode)
{
    if (len == 0) {
        return PGM_ERR_NONE;
    }
    swm_begin_session();
    u8 err = PGM_ERR_NONE;
    if (fifo_mode) {
        err = swm_set_target_fifo(1);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_read_raw(addr, buf, len);
    }
    if (fifo_mode) {
        swm_set_target_fifo(0);
    }
    swm_end_session();
    return err;
}

u8 swm_write(u32 addr, const u8 *buf, u16 len, u8 fifo_mode)
{
    if (len == 0) {
        return PGM_ERR_NONE;
    }
    swm_begin_session();
    u8 err = PGM_ERR_NONE;
    if (fifo_mode) {
        err = swm_set_target_fifo(1);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_raw(addr, buf, len);
    }
    if (fifo_mode) {
        swm_set_target_fifo(0);
    }
    swm_end_session();
    return err;
}

u8 swm_aread(u8 addr, u8 *buf, u16 len)
{
    swm_begin_session();
    u8 err = PGM_ERR_NONE;

    for (u16 i = 0; i < len; i++) {
        u8 req[3] = {(u8)(addr + i), 0x00, 0x40};
        err = swm_write_raw(0x00B8, req, 3);
        if (err != PGM_ERR_NONE) {
            break;
        }

        u8 ctrl = 0x01;
        u8 tries = 64;
        while (tries--) {
            err = swm_read_u8_raw(0x00BA, &ctrl);
            if (err != PGM_ERR_NONE) {
                break;
            }
            if ((ctrl & 0x01) == 0) {
                break;
            }
        }
        if (err != PGM_ERR_NONE) {
            break;
        }
        if (ctrl & 0x01) {
            err = PGM_ERR_BUSY;
            break;
        }

        err = swm_read_u8_raw(0x00B9, &buf[i]);
        swm_write_u8_raw(0x00BA, 0x00);
        if (err != PGM_ERR_NONE) {
            break;
        }
    }

    swm_end_session();
    return err;
}

u8 swm_awrite(u8 addr, const u8 *buf, u16 len)
{
    swm_begin_session();
    u8 err = PGM_ERR_NONE;

    for (u16 i = 0; i < len; i++) {
        u8 req[3] = {(u8)(addr + i), buf[i], 0x60};
        err = swm_write_raw(0x00B8, req, 3);
        if (err != PGM_ERR_NONE) {
            break;
        }

        u8 ctrl = 0x01;
        u8 tries = 64;
        while (tries--) {
            err = swm_read_u8_raw(0x00BA, &ctrl);
            if (err != PGM_ERR_NONE) {
                break;
            }
            if ((ctrl & 0x01) == 0) {
                break;
            }
        }
        if (err != PGM_ERR_NONE) {
            break;
        }
        if (ctrl & 0x01) {
            swm_write_u8_raw(0x00BA, 0x00);
            err = PGM_ERR_BUSY;
            break;
        }
        swm_write_u8_raw(0x00BA, 0x00);
    }

    swm_end_session();
    return err;
}

u8 swm_flash_read(u32 addr, u8 *buf, u16 len)
{
    if (len == 0) {
        return PGM_ERR_NONE;
    }
    swm_begin_session();

    u8 err = swm_set_target_fifo(1);
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000D, 0x00);
    }
    if (err == PGM_ERR_NONE) {
        u8 hdr[5] = {
            0x03,
            (u8)((addr >> 16) & 0xFF),
            (u8)((addr >> 8) & 0xFF),
            (u8)(addr & 0xFF),
            0x00
        };
        err = swm_write_raw(0x000C, hdr, 5);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000D, 0x0A);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_read_raw(0x000C, buf, len);
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_set_target_fifo(0);
    swm_end_session();
    return err;
}

u8 swm_flash_write(u32 addr, const u8 *buf, u16 len)
{
    if (len == 0 || len > 256) {
        return PGM_ERR_LEN;
    }
    swm_begin_session();

    u8 err = swm_flash_wren();
    if (err == PGM_ERR_NONE) {
        err = swm_set_target_fifo(1);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000D, 0x00);
    }
    if (err == PGM_ERR_NONE) {
        u8 pkt[4 + 256];
        pkt[0] = 0x02;
        pkt[1] = (u8)((addr >> 16) & 0xFF);
        pkt[2] = (u8)((addr >> 8) & 0xFF);
        pkt[3] = (u8)(addr & 0xFF);
        memcpy(&pkt[4], buf, len);
        err = swm_write_raw(0x000C, pkt, (u16)(4 + len));
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_set_target_fifo(0);
    swm_end_session();
    return err;
}

u8 swm_flash_erase_sector(u32 addr)
{
    swm_begin_session();

    u8 err = swm_flash_wren();
    if (err == PGM_ERR_NONE) {
        err = swm_set_target_fifo(1);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000D, 0x00);
    }
    if (err == PGM_ERR_NONE) {
        u8 cmd[4] = {
            0x20,
            (u8)((addr >> 16) & 0xFF),
            (u8)((addr >> 8) & 0xFF),
            (u8)(addr & 0xFF)
        };
        err = swm_write_raw(0x000C, cmd, 4);
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_set_target_fifo(0);
    swm_end_session();
    return err;
}

u8 swm_flash_erase_all(void)
{
    swm_begin_session();

    u8 err = swm_flash_wren();
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000D, 0x00);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000C, 0x60);
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_end_session();
    return err;
}

u8 swm_flash_jedec_id(u8 out_id[3])
{
    swm_begin_session();

    u8 err = swm_write_u8_raw(0x000D, 0x00);
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000C, 0x9F);
    }
    for (u8 i = 0; i < 3 && err == PGM_ERR_NONE; i++) {
        err = swm_write_u8_raw(0x000C, 0x00);
        if (err == PGM_ERR_NONE) {
            err = swm_read_u8_raw(0x000C, &out_id[i]);
        }
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_end_session();
    return err;
}

u8 swm_flash_status(u8 *out_status)
{
    swm_begin_session();

    u8 err = swm_write_u8_raw(0x000D, 0x00);
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000C, 0x05);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000C, 0x00);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_read_u8_raw(0x000C, out_status);
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_end_session();
    return err;
}

u8 swm_flash_wrrd(const u8 *wr, u16 wr_len, u8 *rd, u16 rd_len)
{
    if (wr_len == 0) {
        return PGM_ERR_LEN;
    }
    swm_begin_session();

    u8 err = swm_set_target_fifo(1);
    if (err == PGM_ERR_NONE) {
        err = swm_write_u8_raw(0x000D, 0x00);
    }
    if (err == PGM_ERR_NONE) {
        err = swm_write_raw(0x000C, wr, wr_len);
    }
    if (err == PGM_ERR_NONE && rd_len > 0) {
        /* Prime auto-read by writing 1 dummy byte then setting 0x0D = 0x0A */
        err = swm_write_u8_raw(0x000C, 0x00);
        if (err == PGM_ERR_NONE) {
            err = swm_write_u8_raw(0x000D, 0x0A);
        }
        if (err == PGM_ERR_NONE) {
            err = swm_read_raw(0x000C, rd, rd_len);
        }
    }

    swm_write_u8_raw(0x000D, 0x01);
    swm_set_target_fifo(0);
    swm_end_session();
    return err;
}
