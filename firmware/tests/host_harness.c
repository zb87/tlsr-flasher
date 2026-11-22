#include "tl_common.h"
#include "../src/board_tlsr_flasher.h"
#include "../src/swm.h"
#include "../src/usb_cdc.h"
#include "../src/tlsrpgm.h"

#include <stdio.h>

/* Host mock state inspected by Python tests */
u8  mock_ana_regs[256];
u8  mock_reg_5b0 = 0x80;
u32 mock_time_us = 0;
int mock_reboot_count = 0;

typedef struct {
    u32 func;
    u32 oen;
    u32 ien;
    u32 out;
    u32 pull;
} mock_gpio_t;

mock_gpio_t mock_pwr_gpio;
mock_gpio_t mock_rst_gpio;
mock_gpio_t mock_swm_gpio;
mock_gpio_t mock_pe0_gpio;

static mock_gpio_t *find_gpio(u32 pin)
{
    if (pin == PIN_PWR_EN) return &mock_pwr_gpio;
    if (pin == PIN_EXT_RST) return &mock_rst_gpio;
    if (pin == PIN_SWM) return &mock_swm_gpio;
    if (pin == PIN_USB_COMPAT_PE0) return &mock_pe0_gpio;
    return &mock_pe0_gpio;
}

volatile u8 *host_reg8_ptr(u32 addr)
{
    (void)addr;
    return &mock_reg_5b0;
}

u8 analog_read(u8 addr) { return mock_ana_regs[addr]; }
void analog_write(u8 addr, u8 val) { mock_ana_regs[addr] = val; }
void gpio_init(int en) { (void)en; }
void gpio_set_func(u32 pin, u32 func) { find_gpio(pin)->func = func; }
void gpio_set_output_en(u32 pin, u32 en) { find_gpio(pin)->oen = en; }
void gpio_set_input_en(u32 pin, u32 en) { find_gpio(pin)->ien = en; }
void gpio_write(u32 pin, u32 val) { find_gpio(pin)->out = val ? 1 : 0; }
void gpio_setup_up_down_resistor(u32 pin, u32 pull) { find_gpio(pin)->pull = pull; }
u32 clock_time(void) { return mock_time_us; }
u32 clock_time_exceed(u32 ref, u32 span_us) { return (u32)(mock_time_us - ref) > span_us; }
void sleep_us(u32 us) { mock_time_us += us; }
void mcu_reset(void) { mock_reboot_count++; }

/* Mock USB CDC buffers */
static u8  rx_buf[4096];
static u16 rx_len = 0;
static u16 rx_pos = 0;
static u8  rx_short = 0;
static u32 rx_tick = 0;

u8  tx_buf[4096];
u16 tx_len = 0;

void host_reset_usb(void)
{
    rx_len = 0;
    rx_pos = 0;
    rx_short = 0;
    tx_len = 0;
}

void host_feed_usb(const u8 *data, u16 len, u8 is_short)
{
    memcpy(&rx_buf[rx_len], data, len);
    rx_len += len;
    rx_short = is_short;
    rx_tick = mock_time_us;
}

u16 usb_cdc_rx_available(void) { return (u16)(rx_len - rx_pos); }
u8 usb_cdc_read_byte(u8 *out)
{
    if (rx_pos >= rx_len) return 0;
    *out = rx_buf[rx_pos++];
    return 1;
}
void usb_cdc_rx_flush(void) { rx_pos = rx_len; rx_short = 0; }
u8 usb_cdc_take_short_pkt(void) { u8 v = rx_short; rx_short = 0; return v; }
u32 usb_cdc_last_rx_tick(void) { return rx_tick; }
void usb_cdc_write(const u8 *data, u16 len)
{
    memcpy(&tx_buf[tx_len], data, len);
    tx_len += len;
}

/* Mock SWM / Target Memory */
static u8 s_swdiv = PGM_DEFAULT_SWDIV;
static u8 s_addrlen = PGM_DEFAULT_ADDRLEN;
static u8 s_swbuf[6] = {0x5A, 0x00, 0x06, 0x02, 0x00, 0x05};

u8 mock_target_fail = 0;
u8 mock_target_flash[65536];
u8 mock_target_sram[65536];
u8 mock_target_aregs[256];
u8 mock_target_jedec[3] = {0x85, 0x60, 0x13};
u8 mock_target_fstatus = 0x00;
u8 mock_target_pc[4] = {0x34, 0x12, 0x00, 0x00};
u32 mock_wait_poll_until_ready = 0;
u32 mock_wait_polls = 0;

void swm_init(void)
{
    s_swdiv = PGM_DEFAULT_SWDIV;
    s_addrlen = PGM_DEFAULT_ADDRLEN;
}
void swm_set_cfg(u8 swdiv, u8 addrlen, const u8 swbuf[6])
{
    s_swdiv = swdiv;
    s_addrlen = addrlen;
    memcpy(s_swbuf, swbuf, 6);
}
u8 swm_get_swdiv(void) { return s_swdiv; }
u8 swm_get_addrlen(void) { return s_addrlen; }
void swm_get_swbuf(u8 out[6]) { memcpy(out, s_swbuf, 6); }

u8 swm_activate(u16 count, u8 out_pc[4])
{
    (void)count;
    board_set_ext_rst(1);
    board_set_pwr_en(1);
    board_swm_enable();
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(out_pc, mock_target_pc, 4);
    return PGM_ERR_NONE;
}

u8 swm_read(u32 addr, u8 *buf, u16 len, u8 fifo_mode)
{
    (void)fifo_mode;
    if (mock_wait_poll_until_ready > 0) {
        mock_wait_polls++;
        if (mock_wait_polls < mock_wait_poll_until_ready) {
            return PGM_ERR_READ;
        }
        mock_wait_poll_until_ready = 0;
    }
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(buf, &mock_target_sram[addr & 0xFFFF], len);
    return PGM_ERR_NONE;
}

u8 swm_write(u32 addr, const u8 *buf, u16 len, u8 fifo_mode)
{
    (void)fifo_mode;
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(&mock_target_sram[addr & 0xFFFF], buf, len);
    return PGM_ERR_NONE;
}

u8 swm_aread(u8 addr, u8 *buf, u16 len)
{
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(buf, &mock_target_aregs[addr], len);
    return PGM_ERR_NONE;
}

u8 swm_awrite(u8 addr, const u8 *buf, u16 len)
{
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(&mock_target_aregs[addr], buf, len);
    return PGM_ERR_NONE;
}

u8 swm_flash_read(u32 addr, u8 *buf, u16 len)
{
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(buf, &mock_target_flash[addr & 0xFFFF], len);
    return PGM_ERR_NONE;
}

u8 swm_flash_write(u32 addr, const u8 *buf, u16 len)
{
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(&mock_target_flash[addr & 0xFFFF], buf, len);
    return PGM_ERR_NONE;
}

u8 swm_flash_erase_sector(u32 addr)
{
    if (mock_target_fail) return PGM_ERR_READ;
    memset(&mock_target_flash[(addr & 0xFFFF) & ~0xFFFU], 0xFF, 4096);
    return PGM_ERR_NONE;
}

u8 swm_flash_erase_all(void)
{
    if (mock_target_fail) return PGM_ERR_READ;
    memset(mock_target_flash, 0xFF, sizeof(mock_target_flash));
    return PGM_ERR_NONE;
}

u8 swm_flash_jedec_id(u8 out_id[3])
{
    if (mock_target_fail) return PGM_ERR_READ;
    memcpy(out_id, mock_target_jedec, 3);
    return PGM_ERR_NONE;
}

u8 swm_flash_status(u8 *out_status)
{
    if (mock_target_fail) return PGM_ERR_READ;
    *out_status = mock_target_fstatus;
    return PGM_ERR_NONE;
}

u8 swm_flash_wrrd(const u8 *wr, u16 wr_len, u8 *rd, u16 rd_len)
{
    (void)wr;
    if (mock_target_fail) return PGM_ERR_READ;
    for (u16 i = 0; i < rd_len; i++) {
        rd[i] = (u8)(0xA0 + i);
    }
    (void)wr_len;
    return PGM_ERR_NONE;
}

void host_boot(int cold_por)
{
    if (cold_por) {
        memset(mock_ana_regs, 0, sizeof(mock_ana_regs));
    }
    board_init();
    board_sw1_boot_check();
    swm_init();
    tlsrpgm_init();
    host_reset_usb();
}

void host_advance_us(u32 us)
{
    mock_time_us += us;
    board_sw1_tick();
    tlsrpgm_poll();
}
