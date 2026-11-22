#include "tl_common.h"
#include "board_tlsr_flasher.h"
#include "usb_cdc.h"
#include "swm.h"
#include "tlsrpgm.h"

void irq_handler(void)
{
}

int main(void)
{
    irq_disable();
    irq_disable_type(FLD_IRQ_ALL);

    cpu_wakeup_init();
    clock_init(SYS_CLK_32M_PLL);

    board_init();
    board_sw1_boot_check();

    swm_init();
    usb_cdc_init();
    tlsrpgm_init();

    while (1) {
        usb_cdc_poll();
        tlsrpgm_poll();
        board_sw1_tick();
    }

    return 0;
}
