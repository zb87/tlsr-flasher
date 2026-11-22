#pragma once

/* System clock: 32 MHz PLL (TLSR8269) */
#define CLOCK_SYS_CLOCK_HZ          32000000

/* TLSRPGM Protocol & Programmer Identity */
#define PGM_FW_VERSION_MAJOR        0x00
#define PGM_FW_VERSION_MINOR        0x08    /* >= 0.0.0.8 for RDCRC, WAIT_RESP, SWS_PRINTF */
#define PGM_CHIP_ID                 0x5327  /* TLSR8269 */
#define PGM_DEFAULT_SWDIV           7       /* 32 MHz / 5 / 7 = 0.914 Mbps */
#define PGM_DEFAULT_ADDRLEN         3       /* 24-bit default (TLSR825x), 16-bit via CMDF_SWIRE_CFG */

/* USB-CDC Descriptor Identity */
#define ID_VENDOR                   0x248A
#define ID_PRODUCT                  0x8269
#define ID_VERSION                  0x0100

#define STRING_VENDOR               {'T', 'e', 'l', 'i', 'n', 'k'}
#define STRING_VENDOR_LEN           (6 * 2)
#define STRING_PRODUCT              {'T', 'L', 'S', 'R', ' ', 'S', 'W', 'i', 'r', 'e', ' ', 'F', 'l', 'a', 's', 'h', 'e', 'r'}
#define STRING_PRODUCT_LEN          (18 * 2)
#define STRING_SERIAL               {'T', 'L', 'S', 'R', '8', '2', '6', '9', '-', 'P', 'G', 'M'}
#define STRING_SERIAL_LEN           (12 * 2)

/* Hardware Pin Mapping (tlsr-flasher PCB: E180-Z6907A / TLSR8269)
 *
 *  U1.4  (PC4) -> PWR_EN  (Active-HIGH via Q2 S8050 + Q1 AO3401A; also drives LED2)
 *  U1.10 (PE2) -> USB DM
 *  U1.12 (PE3) -> USB DP  (v1.0 PCB has DP on U1.11/PE0 -> bridged to U1.12/PE3)
 *  U1.11 (PE0) -> High-Z float so v1.0 pad 11-12 bridge has zero contention
 *  U1.18 (PA7) -> SWM     (Single-Wire Master to H1.4, no external pull-up)
 *  U1.21 (PB1) -> EXT_RST (Open-drain target reset to H1.5)
 *  U1.26 (PB0) -> SWS     (Self-programming slave on H2.3)
 *  U1.37 (nRST)-> SW1     (Reset button + H2.4)
 */
#define PIN_PWR_EN                  GPIO_PC4
#define PIN_EXT_RST                 GPIO_PB1
#define PIN_SWM                     GPIO_PA7
#define PIN_USB_COMPAT_PE0          GPIO_PE0

/* gpio_default.h overrides */
#define PA7_FUNC                    AS_GPIO
#define PA7_INPUT_ENABLE            0
#define PA7_OUTPUT_ENABLE           0
#define PA7_DATA_OUT                0
#define PULL_WAKEUP_SRC_PA7         0

#define PB0_FUNC                    AS_SWS
#define PB0_INPUT_ENABLE            1
#define PB0_OUTPUT_ENABLE           0
#define PULL_WAKEUP_SRC_PB0         PM_PIN_PULLUP_1M

#define PB1_FUNC                    AS_GPIO
#define PB1_INPUT_ENABLE            0
#define PB1_OUTPUT_ENABLE           0
#define PB1_DATA_OUT                0
#define PULL_WAKEUP_SRC_PB1         PM_PIN_PULLUP_10K

#define PC4_FUNC                    AS_GPIO
#define PC4_INPUT_ENABLE            0
#define PC4_OUTPUT_ENABLE           1
#define PC4_DATA_OUT                0
#define PULL_WAKEUP_SRC_PC4         0

#define PE0_FUNC                    AS_GPIO
#define PE0_INPUT_ENABLE            0
#define PE0_OUTPUT_ENABLE           0
#define PE0_DATA_OUT                0
#define PULL_WAKEUP_SRC_PE0         0

#define PE2_FUNC                    AS_USB
#define PE2_INPUT_ENABLE            1
#define PE2_OUTPUT_ENABLE           0

#define PE3_FUNC                    AS_USB
#define PE3_INPUT_ENABLE            1
#define PE3_OUTPUT_ENABLE           0

/* SW1 double-reset detection window (1.5 seconds) */
#define SW1_DOUBLE_WINDOW_US        1500000UL
