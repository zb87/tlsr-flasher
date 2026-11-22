#ifndef _TL_COMMON_H_
#define _TL_COMMON_H_

#include <stdint.h>
#include <string.h>

typedef uint8_t  u8;
typedef int8_t   s8;
typedef uint16_t u16;
typedef int16_t  s16;
typedef uint32_t u32;
typedef int32_t  s32;

#ifndef BIT
#define BIT(n) (1U << (n))
#endif

#ifndef TRUE
#define TRUE 1
#endif

#include "../../src/app_cfg.h"

/* Stub GPIO identifiers for host testing */
#undef PIN_PWR_EN
#undef PIN_EXT_RST
#undef PIN_SWM
#undef PIN_USB_COMPAT_PE0
#define PIN_PWR_EN          0x210
#define PIN_EXT_RST         0x102
#define PIN_SWM             0x080
#define PIN_USB_COMPAT_PE0  0x401

#define AS_GPIO             0
#define AS_SWM              13
#define PM_PIN_UP_DOWN_FLOAT 0
#define PM_PIN_PULLUP_10K   2
#define DEEP_ANA_REG0       0x3A

#define REG_ADDR8(a)        (*host_reg8_ptr(a))

volatile u8 *host_reg8_ptr(u32 addr);
u8   analog_read(u8 addr);
void analog_write(u8 addr, u8 val);
void gpio_init(int en);
void gpio_set_func(u32 pin, u32 func);
void gpio_set_output_en(u32 pin, u32 en);
void gpio_set_input_en(u32 pin, u32 en);
void gpio_write(u32 pin, u32 val);
void gpio_setup_up_down_resistor(u32 pin, u32 pull);
u32  clock_time(void);
u32  clock_time_exceed(u32 ref, u32 span_us);
void sleep_us(u32 us);
void mcu_reset(void);

#endif
