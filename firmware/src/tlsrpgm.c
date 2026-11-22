#include "tlsrpgm.h"
#include "board_tlsr_flasher.h"
#include "swm.h"
#include "usb_cdc.h"

enum {
    CMD_FUNCS              = 0,
    CMD_FLASH_READ         = 1,
    CMD_FLASH_WRITE        = 2,
    CMD_FLASH_SECT_ERASE   = 3,
    CMD_FLASH_ALL_ERASE    = 4,
    CMD_FLASH_GET_JEDEC_ID = 5,
    CMD_FLASH_GET_STATUS   = 6,
    CMD_SWIRE_READ         = 7,
    CMD_SWIRE_WRITE        = 8,
    CMD_SWIRE_AREAD        = 9,
    CMD_SWIRE_AWRITE       = 10,
    CMD_SWIRE_FIFO_READ    = 11,
    CMD_SWIRE_FIFO_FWRITE  = 12,
    CMD_FLASH_WRRD         = 13,
    CMD_FLASH_RDCRC        = 14,
    CMD_SWS_PRINTF         = 15,
    CMD_WAIT_RESP          = 16,
};

enum {
    CMDF_GET_VERSION    = 0,
    CMDF_MCU_REBOOT     = 1,
    CMDF_SWIRE_CFG      = 2,
    CMDF_EXT_POWER      = 3,
    CMDF_SWIRE_ACTIVATE = 4,
    CMDF_UART_BAUD      = 5,
};

#define MAX_DATA_SIZE   1024
#define RX_PKT_MAX      (16 + MAX_DATA_SIZE)
#define TX_PKT_MAX      (6 + MAX_DATA_SIZE)

typedef enum {
    MODE_CMD = 0,
    MODE_SWS_PRINTF,
    MODE_WAIT_RESP,
} pgm_mode_t;

static u8  s_rx_buf[RX_PKT_MAX];
static u16 s_rx_len = 0;
static u8  s_tx_buf[TX_PKT_MAX];

static pgm_mode_t s_mode = MODE_CMD;

/* SWS_PRINTF state */
static u32 s_sws_printf_addr = 0;

/* WAIT_RESP state */
static u32 s_wait_addr    = 0;
static u32 s_wait_wr_addr = 0;
static u8  s_wait_wr_data[64];
static u16 s_wait_wr_len  = 0;

static u16 crc16_modbus(const u8 *data, u16 len)
{
    u16 crc = 0xFFFF;
    for (u16 i = 0; i < len; i++) {
        crc ^= data[i];
        for (u8 b = 0; b < 8; b++) {
            if (crc & 1) {
                crc = (u16)((crc >> 1) ^ 0xA001);
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

static u8 crc16_check(const u8 *pkt, u16 len)
{
    if (len < 6) {
        return 0;
    }
    u16 calc = crc16_modbus(pkt, (u16)(len - 2));
    u16 got  = (u16)(pkt[len - 2] | (pkt[len - 1] << 8));
    return (calc == got) ? 1 : 0;
}

static void send_response(u8 cmd, u8 err, u16 wcnt, u16 payload_len)
{
    s_tx_buf[0] = cmd;
    s_tx_buf[1] = err;
    s_tx_buf[2] = (u8)(wcnt & 0xFF);
    s_tx_buf[3] = (u8)((wcnt >> 8) & 0xFF);
    u16 body_len = (u16)(4 + payload_len);
    u16 crc = crc16_modbus(s_tx_buf, body_len);
    s_tx_buf[body_len]     = (u8)(crc & 0xFF);
    s_tx_buf[body_len + 1] = (u8)((crc >> 8) & 0xFF);
    usb_cdc_write(s_tx_buf, (u16)(body_len + 2));
}

static u32 unpack_u24(const u8 *p)
{
    return (u32)p[0] | ((u32)p[1] << 8) | ((u32)p[2] << 16);
}

static u16 unpack_u16(const u8 *p)
{
    return (u16)p[0] | ((u16)p[1] << 8);
}

static void handle_funcs(const u8 *pkt, u16 len)
{
    u8 sub   = pkt[1];
    u16 arg  = unpack_u16(&pkt[2]);

    switch (sub) {
    case CMDF_GET_VERSION:
        if (len != 6) {
            send_response(CMD_FUNCS, PGM_ERR_LEN, 0, 0);
            return;
        }
        s_tx_buf[4]  = PGM_FW_VERSION_MINOR;
        s_tx_buf[5]  = PGM_FW_VERSION_MAJOR;
        s_tx_buf[6]  = (u8)(PGM_CHIP_ID & 0xFF);
        s_tx_buf[7]  = (u8)((PGM_CHIP_ID >> 8) & 0xFF);
        s_tx_buf[8]  = board_get_pwr_en();
        s_tx_buf[9]  = swm_get_swdiv();
        s_tx_buf[10] = swm_get_addrlen();
        swm_get_swbuf(&s_tx_buf[11]);
        send_response(CMD_FUNCS, PGM_ERR_NONE, 13, 13);
        break;

    case CMDF_MCU_REBOOT:
        if (len != 6) {
            send_response(CMD_FUNCS, PGM_ERR_LEN, 0, 0);
            return;
        }
        send_response(CMD_FUNCS, PGM_ERR_NONE, 0, 0);
        sleep_us(5000);
        board_mark_soft_reboot();
        mcu_reset();
        break;

    case CMDF_SWIRE_CFG:
        if (len != 14) {
            send_response(CMD_FUNCS, PGM_ERR_LEN, 0, 0);
            return;
        }
        swm_set_cfg(pkt[4], pkt[5], &pkt[6]);
        s_tx_buf[4] = swm_get_swdiv();
        s_tx_buf[5] = swm_get_addrlen();
        swm_get_swbuf(&s_tx_buf[6]);
        send_response(CMD_FUNCS, PGM_ERR_NONE, 8, 8);
        break;

    case CMDF_EXT_POWER:
        if (len != 6) {
            send_response(CMD_FUNCS, PGM_ERR_LEN, 0, 0);
            return;
        }
        if (arg == 0) {
            board_set_pwr_en(0);
            board_set_ext_rst(0);
            board_swm_clamp_low();
        } else {
            board_set_ext_rst(1);
            board_set_pwr_en(1);
            board_swm_enable();
        }
        s_tx_buf[4] = board_get_pwr_en();
        send_response(CMD_FUNCS, PGM_ERR_NONE, 1, 1);
        break;

    case CMDF_SWIRE_ACTIVATE: {
        if (len != 6) {
            send_response(CMD_FUNCS, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 pc[4] = {0};
        u8 err = swm_activate(arg, pc);
        if (err != PGM_ERR_NONE) {
            send_response(CMD_FUNCS, err, 0, 0);
        } else {
            memcpy(&s_tx_buf[4], pc, 4);
            send_response(CMD_FUNCS, PGM_ERR_NONE, 4, 4);
        }
        break;
    }

    case CMDF_UART_BAUD:
        if (len != 6) {
            send_response(CMD_FUNCS, PGM_ERR_LEN, 0, 0);
            return;
        }
        if (arg >= 9) {
            send_response(CMD_FUNCS, PGM_ERR_BAUD, 0, 0);
        } else {
            send_response(CMD_FUNCS, PGM_ERR_NONE, 0, 0);
        }
        break;

    default:
        send_response(CMD_FUNCS, PGM_ERR_FUNC, 0, 0);
        break;
    }
}

static void dispatch_packet(const u8 *pkt, u16 len)
{
    u8 cmd = pkt[0];
    u32 addr = unpack_u24(&pkt[1]);

    switch (cmd) {
    case CMD_FUNCS:
        handle_funcs(pkt, len);
        break;

    case CMD_FLASH_READ: {
        if (len != 8) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 rdlen = unpack_u16(&pkt[4]);
        if (rdlen > MAX_DATA_SIZE) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_read(addr, &s_tx_buf[4], rdlen);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? rdlen : 0, (err == PGM_ERR_NONE) ? rdlen : 0);
        break;
    }

    case CMD_FLASH_WRITE: {
        if (len < 7 || (len - 6) > 256) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 wrlen = (u16)(len - 6);
        u8 err = swm_flash_write(addr, &pkt[4], wrlen);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? wrlen : 0, 0);
        break;
    }

    case CMD_FLASH_SECT_ERASE: {
        if (len != 6) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_erase_sector(addr);
        send_response(cmd, err, 0, 0);
        break;
    }

    case CMD_FLASH_ALL_ERASE: {
        if (len != 6) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_erase_all();
        send_response(cmd, err, 0, 0);
        break;
    }

    case CMD_FLASH_GET_JEDEC_ID: {
        if (len != 6) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_jedec_id(&s_tx_buf[4]);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? 3 : 0, (err == PGM_ERR_NONE) ? 3 : 0);
        break;
    }

    case CMD_FLASH_GET_STATUS: {
        if (len != 6) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_status(&s_tx_buf[4]);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? 1 : 0, (err == PGM_ERR_NONE) ? 1 : 0);
        break;
    }

    case CMD_SWIRE_READ:
    case CMD_SWIRE_FIFO_READ: {
        if (len != 8) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 rdlen = unpack_u16(&pkt[4]);
        if (rdlen > MAX_DATA_SIZE) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 fifo = (cmd == CMD_SWIRE_FIFO_READ) ? 1 : 0;
        u8 err = swm_read(addr, &s_tx_buf[4], rdlen, fifo);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? rdlen : 0, (err == PGM_ERR_NONE) ? rdlen : 0);
        break;
    }

    case CMD_SWIRE_WRITE:
    case CMD_SWIRE_FIFO_FWRITE: {
        if (len < 7 || (len - 6) > MAX_DATA_SIZE) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 wrlen = (u16)(len - 6);
        u8 fifo = (cmd == CMD_SWIRE_FIFO_FWRITE) ? 1 : 0;
        u8 err = swm_write(addr, &pkt[4], wrlen, fifo);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? wrlen : 0, 0);
        break;
    }

    case CMD_SWIRE_AREAD: {
        if (len != 8) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 rdlen = unpack_u16(&pkt[4]);
        if (rdlen > 256) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_aread((u8)(addr & 0xFF), &s_tx_buf[4], rdlen);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? rdlen : 0, (err == PGM_ERR_NONE) ? rdlen : 0);
        break;
    }

    case CMD_SWIRE_AWRITE: {
        if (len < 7 || (len - 6) > 256) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 wrlen = (u16)(len - 6);
        u8 err = swm_awrite((u8)(addr & 0xFF), &pkt[4], wrlen);
        send_response(cmd, err, (err == PGM_ERR_NONE) ? wrlen : 0, 0);
        break;
    }

    case CMD_FLASH_WRRD: {
        if (len < 9) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 rdlen = unpack_u16(&pkt[4]);
        u16 wrlen = (u16)(len - 8);
        if (rdlen > MAX_DATA_SIZE || wrlen == 0) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_wrrd(&pkt[6], wrlen, &s_tx_buf[4], rdlen);
        u16 wcnt = (err == PGM_ERR_NONE) ? (u16)(rdlen + wrlen) : 0;
        send_response(cmd, err, wcnt, (err == PGM_ERR_NONE) ? rdlen : 0);
        break;
    }

    case CMD_FLASH_RDCRC: {
        if (len != 8) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u16 rdlen = unpack_u16(&pkt[4]);
        if (rdlen > MAX_DATA_SIZE) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        u8 err = swm_flash_read(addr, &s_tx_buf[4], rdlen);
        u16 blk_crc = (err == PGM_ERR_NONE) ? crc16_modbus(&s_tx_buf[4], rdlen) : 0;
        send_response(cmd, err, blk_crc, 0);
        break;
    }

    case CMD_SWS_PRINTF: {
        if (len != 7) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        s_sws_printf_addr = addr;
        s_mode = MODE_SWS_PRINTF;
        send_response(cmd, PGM_ERR_NONE, 1, 0);
        break;
    }

    case CMD_WAIT_RESP: {
        if (len != 6 && len < 10) {
            send_response(cmd, PGM_ERR_LEN, 0, 0);
            return;
        }
        s_wait_addr = addr;
        if (len >= 10) {
            u16 wlen = (u16)(len - 9);
            if (wlen > sizeof(s_wait_wr_data)) {
                send_response(cmd, PGM_ERR_LEN, 0, 0);
                return;
            }
            s_wait_wr_addr = unpack_u24(&pkt[4]);
            s_wait_wr_len  = wlen;
            memcpy(s_wait_wr_data, &pkt[7], wlen);
        } else {
            s_wait_wr_len = 0;
        }
        s_mode = MODE_WAIT_RESP;
        send_response(cmd, PGM_ERR_NONE, 0, 0);
        break;
    }

    default:
        send_response(cmd, PGM_ERR_FUNC, 0, 0);
        break;
    }
}

static u16 expected_fixed_len(const u8 *buf, u16 len)
{
    if (len == 0) {
        return 0;
    }
    switch (buf[0]) {
    case CMD_FUNCS:
        if (len >= 2 && buf[1] == CMDF_SWIRE_CFG) {
            return 14;
        }
        return (len >= 2) ? 6 : 0;
    case CMD_FLASH_READ:
    case CMD_SWIRE_READ:
    case CMD_SWIRE_AREAD:
    case CMD_SWIRE_FIFO_READ:
    case CMD_FLASH_RDCRC:
        return 8;
    case CMD_FLASH_SECT_ERASE:
    case CMD_FLASH_ALL_ERASE:
    case CMD_FLASH_GET_JEDEC_ID:
    case CMD_FLASH_GET_STATUS:
        return 6;
    case CMD_SWS_PRINTF:
        return 7;
    default:
        return 0; /* Variable-length command */
    }
}

static void poll_sws_printf(void)
{
    if (usb_cdc_rx_available() > 0) {
        s_mode = MODE_CMD;
        return;
    }

    u8 hdr[2] = {0, 0};
    if (swm_read(s_sws_printf_addr, hdr, 2, 0) != PGM_ERR_NONE) {
        return;
    }
    if (hdr[0] != 0x55) {
        return;
    }
    u8 slen = hdr[1];
    if (slen >= 1 && slen <= 253) {
        u8 txt[256];
        if (swm_read(s_sws_printf_addr + 2, txt, slen, 0) == PGM_ERR_NONE) {
            u8 zero = 0;
            swm_write(s_sws_printf_addr + 1, &zero, 1, 0);
            usb_cdc_write(txt, slen);
        }
    } else if (slen == 255) {
        u8 zero = 0;
        swm_write(s_sws_printf_addr + 1, &zero, 1, 0);
    }
}

static void poll_wait_resp(void)
{
    if (usb_cdc_rx_available() > 0) {
        s_mode = MODE_CMD;
        return;
    }

    u8 val[4] = {0};
    if (swm_read(s_wait_addr, val, 4, 0) == PGM_ERR_NONE) {
        if (s_wait_wr_len > 0) {
            swm_write(s_wait_wr_addr, s_wait_wr_data, s_wait_wr_len, 0);
        }
        memcpy(&s_tx_buf[4], val, 4);
        s_mode = MODE_CMD;
        send_response(CMD_WAIT_RESP, PGM_ERR_NONE, 4, 4);
    }
}

void tlsrpgm_init(void)
{
    s_rx_len = 0;
    s_mode   = MODE_CMD;
}

void tlsrpgm_poll(void)
{
    if (s_mode == MODE_SWS_PRINTF) {
        poll_sws_printf();
        if (s_mode == MODE_SWS_PRINTF) {
            return;
        }
    } else if (s_mode == MODE_WAIT_RESP) {
        poll_wait_resp();
        if (s_mode == MODE_WAIT_RESP) {
            return;
        }
    }

    u8 b;
    while (usb_cdc_read_byte(&b)) {
        if (s_rx_len < RX_PKT_MAX) {
            s_rx_buf[s_rx_len++] = b;
        } else {
            s_rx_len = 0;
            send_response(s_rx_buf[0], PGM_ERR_LEN, 0, 0);
            usb_cdc_rx_flush();
            return;
        }

        u16 fixed = expected_fixed_len(s_rx_buf, s_rx_len);
        if (fixed > 0 && s_rx_len == fixed) {
            u16 pkt_len = s_rx_len;
            s_rx_len = 0;
            (void)usb_cdc_take_short_pkt();
            if (crc16_check(s_rx_buf, pkt_len)) {
                dispatch_packet(s_rx_buf, pkt_len);
            } else {
                send_response(s_rx_buf[0], PGM_ERR_CRC, 0, 0);
            }
            return;
        }
    }

    if (s_rx_len == 0) {
        return;
    }

    u8 short_pkt = usb_cdc_take_short_pkt();
    u8 idle_2ms  = clock_time_exceed(usb_cdc_last_rx_tick(), 2000);
    u8 idle_30ms = clock_time_exceed(usb_cdc_last_rx_tick(), 30000);

    if (s_rx_len >= 6 && (short_pkt || idle_2ms)) {
        if (crc16_check(s_rx_buf, s_rx_len)) {
            u16 pkt_len = s_rx_len;
            s_rx_len = 0;
            dispatch_packet(s_rx_buf, pkt_len);
            return;
        }
    }

    if (idle_30ms) {
        u8 cmd = s_rx_buf[0];
        u16 bad_len = s_rx_len;
        s_rx_len = 0;
        if (bad_len >= 6) {
            send_response(cmd, PGM_ERR_CRC, 0, 0);
        }
    }
}
