#include "board_tlsr_flasher.h"

#define SW1_REG                 DEEP_ANA_REG0
#define SW1_MAGIC_MASK          0xF0
#define SW1_MAGIC_VAL           0xA0
#define SW1_BIT_SOFT_REBOOT     BIT(3)
#define SW1_BIT_ARMED           BIT(2)
#define SW1_BIT_PRE_PWR         BIT(1)
#define SW1_BIT_CUR_PWR         BIT(0)

static u8  s_pwr_en = 0;
static u8  s_sw1_armed = 0;
static u32 s_sw1_arm_tick = 0;

void board_init(void)
{
    gpio_init(TRUE);

    /* Keep PE0 high-Z so v1.0 PCB U1.11(PE0)-U1.12(PE3) solder bridge has no contention */
    gpio_set_func(PIN_USB_COMPAT_PE0, AS_GPIO);
    gpio_set_output_en(PIN_USB_COMPAT_PE0, 0);
    gpio_set_input_en(PIN_USB_COMPAT_PE0, 0);
    gpio_setup_up_down_resistor(PIN_USB_COMPAT_PE0, PM_PIN_UP_DOWN_FLOAT);

    /* Clear UART RX / I2S_DI_DMIC pinmux on PA7 so AS_SWM controls PA7 */
    REG_ADDR8(0x5b0) &= (u8)(~BIT(7));
    REG_ADDR8(0x5b2) &= (u8)(~BIT(7));

    /* Safe defaults: PWR_EN=0, EXT_RST released (Hi-Z + 10k pull-up), SWM floating */
    board_set_ext_rst(1);
    board_swm_float();
    gpio_set_func(PIN_PWR_EN, AS_GPIO);
    gpio_set_input_en(PIN_PWR_EN, 0);
    gpio_set_output_en(PIN_PWR_EN, 1);
    gpio_write(PIN_PWR_EN, 0);
    s_pwr_en = 0;
}

void board_sw1_boot_check(void)
{
    u8 reg = analog_read(SW1_REG);

    if ((reg & SW1_MAGIC_MASK) != SW1_MAGIC_VAL) {
        /* Cold power-on reset */
        analog_write(SW1_REG, SW1_MAGIC_VAL);
        s_sw1_armed = 0;
        board_set_pwr_en(0);
        return;
    }

    if (reg & SW1_BIT_SOFT_REBOOT) {
        /* Host-initiated CMDF_MCU_REBOOT: do not treat as SW1 press */
        analog_write(SW1_REG, SW1_MAGIC_VAL);
        s_sw1_armed = 0;
        board_set_pwr_en(0);
        return;
    }

    if (reg & SW1_BIT_ARMED) {
        /* Rapid double-press on SW1 within SW1_DOUBLE_WINDOW_US: toggle target PWR_EN */
        u8 next_pwr = (reg & SW1_BIT_PRE_PWR) ? 0 : 1;
        u8 next_reg = SW1_MAGIC_VAL | (next_pwr ? (SW1_BIT_PRE_PWR | SW1_BIT_CUR_PWR) : 0);
        analog_write(SW1_REG, next_reg);
        s_sw1_armed = 0;
        board_set_ext_rst(1);
        board_set_pwr_en(next_pwr);
        if (next_pwr) {
            board_swm_enable();
        } else {
            board_swm_float();
        }
        return;
    }

    /* Single SW1 press: reset safely with PWR_EN=0 and arm double-press window */
    u8 pre_pwr = (reg & SW1_BIT_CUR_PWR) ? 1 : 0;
    analog_write(SW1_REG, SW1_MAGIC_VAL | SW1_BIT_ARMED | (pre_pwr ? SW1_BIT_PRE_PWR : 0));
    s_sw1_armed = 1;
    s_sw1_arm_tick = clock_time();
    board_set_pwr_en(0);
}

void board_sw1_tick(void)
{
    if (!s_sw1_armed) {
        return;
    }
    if (clock_time_exceed(s_sw1_arm_tick, SW1_DOUBLE_WINDOW_US)) {
        u8 reg = analog_read(SW1_REG);
        reg &= (u8)(~(SW1_BIT_ARMED | SW1_BIT_PRE_PWR));
        if (s_pwr_en) {
            reg |= SW1_BIT_PRE_PWR | SW1_BIT_CUR_PWR;
        }
        analog_write(SW1_REG, reg);
        s_sw1_armed = 0;
    }
}

void board_mark_soft_reboot(void)
{
    u8 reg = analog_read(SW1_REG);
    reg = (reg & SW1_MAGIC_MASK) == SW1_MAGIC_VAL ? reg : SW1_MAGIC_VAL;
    reg = (u8)((reg & ~SW1_BIT_ARMED) | SW1_BIT_SOFT_REBOOT);
    analog_write(SW1_REG, reg);
}

void board_set_pwr_en(u8 en)
{
    s_pwr_en = en ? 1 : 0;
    gpio_write(PIN_PWR_EN, s_pwr_en);

    u8 reg = analog_read(SW1_REG);
    if ((reg & SW1_MAGIC_MASK) != SW1_MAGIC_VAL) {
        reg = SW1_MAGIC_VAL;
    }
    if (s_pwr_en) {
        reg |= SW1_BIT_CUR_PWR;
    } else {
        reg &= (u8)(~SW1_BIT_CUR_PWR);
    }
    analog_write(SW1_REG, reg);
}

u8 board_get_pwr_en(void)
{
    return s_pwr_en;
}

void board_set_ext_rst(u8 release)
{
    gpio_set_func(PIN_EXT_RST, AS_GPIO);
    gpio_set_input_en(PIN_EXT_RST, 0);
    if (release) {
        gpio_set_output_en(PIN_EXT_RST, 0);
        gpio_setup_up_down_resistor(PIN_EXT_RST, PM_PIN_PULLUP_10K);
    } else {
        gpio_setup_up_down_resistor(PIN_EXT_RST, PM_PIN_UP_DOWN_FLOAT);
        gpio_write(PIN_EXT_RST, 0);
        gpio_set_output_en(PIN_EXT_RST, 1);
    }
}

void board_swm_enable(void)
{
    REG_ADDR8(0x5b0) &= (u8)(~BIT(7));
    REG_ADDR8(0x5b2) &= (u8)(~BIT(7));
    gpio_set_output_en(PIN_SWM, 0);
    gpio_set_input_en(PIN_SWM, 1);
    gpio_setup_up_down_resistor(PIN_SWM, PM_PIN_PULLUP_10K);
    gpio_set_func(PIN_SWM, AS_SWM);
}

void board_swm_float(void)
{
    gpio_setup_up_down_resistor(PIN_SWM, PM_PIN_UP_DOWN_FLOAT);
    gpio_set_output_en(PIN_SWM, 0);
    gpio_set_input_en(PIN_SWM, 0);
    gpio_set_func(PIN_SWM, AS_GPIO);
}

void board_swm_clamp_low(void)
{
    gpio_setup_up_down_resistor(PIN_SWM, PM_PIN_UP_DOWN_FLOAT);
    gpio_write(PIN_SWM, 0);
    gpio_set_output_en(PIN_SWM, 1);
    gpio_set_input_en(PIN_SWM, 0);
    gpio_set_func(PIN_SWM, AS_GPIO);
}
