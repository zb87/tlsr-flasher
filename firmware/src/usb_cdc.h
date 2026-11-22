#pragma once

#include "tl_common.h"

void usb_cdc_init(void);
void usb_cdc_poll(void);

u16  usb_cdc_rx_available(void);
u8   usb_cdc_read_byte(u8 *out);
void usb_cdc_rx_flush(void);

/* Returns 1 if a short (<64B) USB OUT packet arrived since last cleared */
u8   usb_cdc_take_short_pkt(void);
u32  usb_cdc_last_rx_tick(void);

void usb_cdc_write(const u8 *data, u16 len);
