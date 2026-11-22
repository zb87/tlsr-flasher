#pragma once

#include "tl_common.h"

void board_init(void);
void board_sw1_boot_check(void);
void board_sw1_tick(void);
void board_mark_soft_reboot(void);

void board_set_pwr_en(u8 en);
u8   board_get_pwr_en(void);

/* release=0 drives EXT_RST (PB1) LOW; release=1 sets Hi-Z with 10k pull-up */
void board_set_ext_rst(u8 release);

void board_swm_enable(void);
void board_swm_float(void);
void board_swm_clamp_low(void);
