#include "usb_cdc.h"
#include "drv_usb.h"
#include "usbstd/usbstd.h"

#define CDC_NOTIFICATION_EPNUM  2
#define CDC_TX_EPNUM            USB_EDP_CDC_IN   /* EP4 IN  (64B HW buffer) */
#define CDC_RX_EPNUM            USB_EDP_CDC_OUT  /* EP5 OUT (64B HW buffer) */
#define CDC_NOTIFICATION_EPSIZE 8
#define CDC_TXRX_EPSIZE         64

#define RX_RING_SIZE            2048 /* Must be power of 2 */
#define RX_RING_MASK            (RX_RING_SIZE - 1)

enum {
    USB_STR_LANG = 0,
    USB_STR_VENDOR,
    USB_STR_PRODUCT,
    USB_STR_SERIAL,
};

typedef struct {
    USB_Descriptor_Configuration_Header_t   Config;
    USB_Descriptor_Interface_Association_t  CDC_IAD;
    USB_Descriptor_Interface_t              CDC_CCI_Interface;
    USB_CDC_Descriptor_FunctionalHeader_t   CDC_Functional_Header;
    USB_CDC_Descriptor_FunctionalACM_t      CDC_Functional_ACM;
    USB_CDC_Descriptor_FunctionalUnion_t    CDC_Functional_Union;
    USB_CDC_Descriptor_FunctionalUnion_t    CDC_CallManagement;
    USB_Descriptor_Endpoint_t               CDC_NotificationEndpoint;
    USB_Descriptor_Interface_t              CDC_DCI_Interface;
    USB_Descriptor_Endpoint_t               CDC_DataOutEndpoint;
    USB_Descriptor_Endpoint_t               CDC_DataInEndpoint;
} usb_cdc_cfg_desc_t;

typedef struct {
    USB_Descriptor_Header_t Header;
    u16 UnicodeString[];
} usb_str_desc_t;

static const usb_str_desc_t s_lang_desc = {
    {sizeof(USB_Descriptor_Header_t) + 2, DTYPE_String},
    {LANGUAGE_ID_ENG}
};

static const usb_str_desc_t s_vendor_desc = {
    {sizeof(USB_Descriptor_Header_t) + STRING_VENDOR_LEN, DTYPE_String},
    STRING_VENDOR
};

static const usb_str_desc_t s_product_desc = {
    {sizeof(USB_Descriptor_Header_t) + STRING_PRODUCT_LEN, DTYPE_String},
    STRING_PRODUCT
};

static const usb_str_desc_t s_serial_desc = {
    {sizeof(USB_Descriptor_Header_t) + STRING_SERIAL_LEN, DTYPE_String},
    STRING_SERIAL
};

static const USB_Descriptor_Device_t s_device_desc = {
    {sizeof(USB_Descriptor_Device_t), DTYPE_Device},
    0x0110,                     /* USB 1.1 */
    USB_CSCP_IADDeviceClass,
    USB_CSCP_IADDeviceSubclass,
    USB_CSCP_IADDeviceProtocol,
    8,                          /* EP0 max packet size */
    ID_VENDOR,
    ID_PRODUCT,
    ID_VERSION,
    USB_STR_VENDOR,
    USB_STR_PRODUCT,
    USB_STR_SERIAL,
    1
};

static const usb_cdc_cfg_desc_t s_cfg_desc = {
    .Config = {
        {sizeof(USB_Descriptor_Configuration_Header_t), DTYPE_Configuration},
        sizeof(usb_cdc_cfg_desc_t),
        2,
        1,
        NO_DESCRIPTOR,
        USB_CONFIG_ATTR_RESERVED,
        USB_CONFIG_POWER_MA(100)
    },
    .CDC_IAD = {
        {sizeof(USB_Descriptor_Interface_Association_t), DTYPE_InterfaceAssociation},
        0,
        2,
        CDC_CSCP_CDCClass,
        CDC_CSCP_ACMSubclass,
        CDC_CSCP_ATCommandProtocol,
        NO_DESCRIPTOR
    },
    .CDC_CCI_Interface = {
        {sizeof(USB_Descriptor_Interface_t), DTYPE_Interface},
        0,
        0,
        1,
        CDC_CSCP_CDCClass,
        CDC_CSCP_ACMSubclass,
        CDC_CSCP_ATCommandProtocol,
        NO_DESCRIPTOR
    },
    .CDC_Functional_Header = {
        {sizeof(USB_CDC_Descriptor_FunctionalHeader_t), DTYPE_CSInterface},
        CDC_DSUBTYPE_CSInterface_Header,
        0x0110
    },
    .CDC_Functional_ACM = {
        {sizeof(USB_CDC_Descriptor_FunctionalACM_t), DTYPE_CSInterface},
        CDC_DSUBTYPE_CSInterface_ACM,
        0x02
    },
    .CDC_Functional_Union = {
        {sizeof(USB_CDC_Descriptor_FunctionalUnion_t), DTYPE_CSInterface},
        CDC_DSUBTYPE_CSInterface_Union,
        0,
        1
    },
    .CDC_CallManagement = {
        {sizeof(USB_CDC_Descriptor_FunctionalUnion_t), DTYPE_CSInterface},
        CDC_DSUBTYPE_CSInterface_CallManagement,
        0,
        1
    },
    .CDC_NotificationEndpoint = {
        {sizeof(USB_Descriptor_Endpoint_t), DTYPE_Endpoint},
        (ENDPOINT_DIR_IN | CDC_NOTIFICATION_EPNUM),
        (EP_TYPE_INTERRUPT | ENDPOINT_ATTR_NO_SYNC | ENDPOINT_USAGE_DATA),
        CDC_NOTIFICATION_EPSIZE,
        0x40
    },
    .CDC_DCI_Interface = {
        {sizeof(USB_Descriptor_Interface_t), DTYPE_Interface},
        1,
        0,
        2,
        CDC_CSCP_CDCDataClass,
        CDC_CSCP_NoDataSubclass,
        CDC_CSCP_NoDataProtocol,
        NO_DESCRIPTOR
    },
    .CDC_DataOutEndpoint = {
        {sizeof(USB_Descriptor_Endpoint_t), DTYPE_Endpoint},
        (ENDPOINT_DIR_OUT | CDC_RX_EPNUM),
        (EP_TYPE_BULK | ENDPOINT_ATTR_NO_SYNC | ENDPOINT_USAGE_DATA),
        CDC_TXRX_EPSIZE,
        0x00
    },
    .CDC_DataInEndpoint = {
        {sizeof(USB_Descriptor_Endpoint_t), DTYPE_Endpoint},
        (ENDPOINT_DIR_IN | CDC_TX_EPNUM),
        (EP_TYPE_BULK | ENDPOINT_ATTR_NO_SYNC | ENDPOINT_USAGE_DATA),
        CDC_TXRX_EPSIZE,
        0x00
    }
};

static USB_Request_Header_t s_ctrl_req;
static const u8 *s_resp_ptr = 0;
static u16 s_resp_len = 0;
static u8 s_stall = 0;

static u32 s_baud_rate = 230400;
static u8  s_char_fmt  = CDC_LINEENCODING_OneStopBit;
static u8  s_parity    = CDC_PARITY_None;
static u8  s_data_bits = 8;
static u16 s_ctrl_line = 0;

static u8  s_rx_ring[RX_RING_SIZE];
static volatile u16 s_rx_head = 0;
static volatile u16 s_rx_tail = 0;
static u32 s_rx_last_tick = 0;
static u8  s_rx_short_pkt = 0;

static void ep0_send_chunk(void)
{
    u16 n = (s_resp_len < 8) ? s_resp_len : 8;
    s_resp_len -= n;
    usbhw_reset_ctrl_ep_ptr();
    while (n-- > 0) {
        usbhw_write_ctrl_ep_data(*s_resp_ptr++);
    }
}

static void prepare_descriptor(void)
{
    u8 idx  = (u8)(s_ctrl_req.wValue & 0xFF);
    u8 type = (u8)((s_ctrl_req.wValue >> 8) & 0xFF);

    s_resp_ptr = 0;
    s_resp_len = 0;

    switch (type) {
    case DTYPE_Device:
        s_resp_ptr = (const u8 *)&s_device_desc;
        s_resp_len = sizeof(s_device_desc);
        break;
    case DTYPE_Configuration:
        s_resp_ptr = (const u8 *)&s_cfg_desc;
        s_resp_len = sizeof(s_cfg_desc);
        break;
    case DTYPE_String:
        if (idx == USB_STR_LANG) {
            s_resp_ptr = (const u8 *)&s_lang_desc;
            s_resp_len = s_resp_ptr[0];
        } else if (idx == USB_STR_VENDOR) {
            s_resp_ptr = (const u8 *)&s_vendor_desc;
            s_resp_len = s_resp_ptr[0];
        } else if (idx == USB_STR_PRODUCT) {
            s_resp_ptr = (const u8 *)&s_product_desc;
            s_resp_len = s_resp_ptr[0];
        } else if (idx == USB_STR_SERIAL) {
            s_resp_ptr = (const u8 *)&s_serial_desc;
            s_resp_len = s_resp_ptr[0];
        } else {
            s_stall = 1;
        }
        break;
    default:
        s_stall = 1;
        break;
    }

    if (s_ctrl_req.wLength < s_resp_len) {
        s_resp_len = s_ctrl_req.wLength;
    }
}

static void handle_cdc_ctrl_req(u8 is_data_stage)
{
    if (s_ctrl_req.wIndex != 0) {
        return;
    }

    switch (s_ctrl_req.bRequest) {
    case CDC_REQ_GetLineEncoding:
        usbhw_write_ctrl_ep_data((u8)(s_baud_rate & 0xFF));
        usbhw_write_ctrl_ep_data((u8)((s_baud_rate >> 8) & 0xFF));
        usbhw_write_ctrl_ep_data((u8)((s_baud_rate >> 16) & 0xFF));
        usbhw_write_ctrl_ep_data((u8)((s_baud_rate >> 24) & 0xFF));
        usbhw_write_ctrl_ep_data(s_char_fmt);
        usbhw_write_ctrl_ep_data(s_parity);
        usbhw_write_ctrl_ep_data(s_data_bits);
        break;
    case CDC_REQ_SetLineEncoding:
        if (is_data_stage) {
            u32 b0 = usbhw_read_ctrl_ep_data();
            u32 b1 = usbhw_read_ctrl_ep_data();
            u32 b2 = usbhw_read_ctrl_ep_data();
            u32 b3 = usbhw_read_ctrl_ep_data();
            s_baud_rate = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
            s_char_fmt  = usbhw_read_ctrl_ep_data();
            s_parity    = usbhw_read_ctrl_ep_data();
            s_data_bits = usbhw_read_ctrl_ep_data();
        }
        break;
    case CDC_REQ_SetControlLineState:
        s_ctrl_line = s_ctrl_req.wValue;
        break;
    case CDC_REQ_SendBreak:
        break;
    default:
        s_stall = 1;
        break;
    }
}

static void handle_ctrl_request(u8 is_setup)
{
    u8 req_type = s_ctrl_req.bmRequestType;
    u8 req      = s_ctrl_req.bRequest;

    usbhw_reset_ctrl_ep_ptr();

    switch (req_type) {
    case (REQDIR_DEVICETOHOST | REQTYPE_STANDARD | REQREC_DEVICE):
        if (req == REQ_GetDescriptor) {
            if (is_setup) {
                prepare_descriptor();
            }
            ep0_send_chunk();
        } else {
            s_stall = 1;
        }
        break;
    case (REQDIR_HOSTTODEVICE | REQTYPE_CLASS | REQREC_INTERFACE):
        handle_cdc_ctrl_req(!is_setup);
        break;
    case (REQDIR_DEVICETOHOST | REQTYPE_CLASS | REQREC_INTERFACE):
        if (req == CDC_REQ_SendEncapsulatedCommand) {
            usbhw_write_ctrl_ep_data(0x00);
        } else {
            handle_cdc_ctrl_req(0);
        }
        break;
    default:
        s_stall = 1;
        break;
    }
}

static void handle_rx_ep(void)
{
    u8 len = reg_usb_ep_ptr(CDC_RX_EPNUM & 0x07);
    usbhw_reset_ep_ptr(CDC_RX_EPNUM);

    for (u8 i = 0; i < len; i++) {
        u8 b = usbhw_read_ep_data(CDC_RX_EPNUM);
        u16 next = (u16)((s_rx_head + 1) & RX_RING_MASK);
        if (next != s_rx_tail) {
            s_rx_ring[s_rx_head] = b;
            s_rx_head = next;
        }
    }

    if (len > 0) {
        s_rx_last_tick = clock_time();
        if (len < CDC_TXRX_EPSIZE) {
            s_rx_short_pkt = 1;
        }
    }

    usbhw_data_ep_ack(CDC_RX_EPNUM);
}

void usb_cdc_init(void)
{
    reg_rst_clk0 |= (FLD_CLK_USB_EN | FLD_CLK_USB_PHY_EN);
    reg_rst_clk0 &= ~(FLD_RST_USB | FLD_RST_USB_PHY);
    reg_usb_ram_ctrl = FLD_USB_CEN_FUNC;
    reg_usb_mdev &= (u8)(~FLD_USB_MDEV_SELF_PWR);

    /* Force clean SE0 disconnect so host re-enumerates after reset / SW1 press */
    usb_dp_pullup_en(0);
    gpio_set_func(GPIO_PE3, AS_GPIO);
    gpio_set_output_en(GPIO_PE3, 1);
    gpio_write(GPIO_PE3, 0);
    sleep_us(20000);

    usb_set_pin_en();
    usbhw_enable_manual_interrupt(FLD_CTRL_EP_AUTO_STD | FLD_CTRL_EP_AUTO_DESC);
    usbhw_clr_eps_irq_mask(BIT(CDC_TX_EPNUM & 0x07) | BIT(CDC_RX_EPNUM & 0x07));
    usbhw_data_ep_ack(CDC_RX_EPNUM);

    s_rx_head = 0;
    s_rx_tail = 0;
    s_rx_short_pkt = 0;
}

void usb_cdc_poll(void)
{
    u8 ctrl_irq = (u8)usbhw_get_ctrl_ep_irq();

    if (ctrl_irq & FLD_CTRL_EP_IRQ_SETUP) {
        usbhw_clr_ctrl_ep_irq(FLD_CTRL_EP_IRQ_SETUP);
        usbhw_reset_ctrl_ep_ptr();
        s_ctrl_req.bmRequestType = usbhw_read_ctrl_ep_data();
        s_ctrl_req.bRequest      = usbhw_read_ctrl_ep_data();
        s_ctrl_req.wValue        = usbhw_read_ctrl_ep_u16();
        s_ctrl_req.wIndex        = usbhw_read_ctrl_ep_u16();
        s_ctrl_req.wLength       = usbhw_read_ctrl_ep_u16();
        s_stall = 0;
        handle_ctrl_request(1);
        usbhw_write_ctrl_ep_ctrl(s_stall ? FLD_EP_DAT_STALL : FLD_EP_DAT_ACK);
    }

    if (ctrl_irq & FLD_CTRL_EP_IRQ_DATA) {
        usbhw_clr_ctrl_ep_irq(FLD_CTRL_EP_IRQ_DATA);
        usbhw_reset_ctrl_ep_ptr();
        s_stall = 0;
        handle_ctrl_request(0);
        usbhw_write_ctrl_ep_ctrl(s_stall ? FLD_EP_DAT_STALL : FLD_EP_DAT_ACK);
    }

    if (ctrl_irq & FLD_CTRL_EP_IRQ_STA) {
        usbhw_clr_ctrl_ep_irq(FLD_CTRL_EP_IRQ_STA);
        usbhw_write_ctrl_ep_ctrl(s_stall ? FLD_EP_STA_STALL : FLD_EP_STA_ACK);
    }

    if (usb_is_irq_reset()) {
        usb_clear_irq_reset();
        for (int i = 0; i < 8; i++) {
            reg_usb_ep_ctrl(i) = 0;
        }
        usbhw_data_ep_ack(CDC_RX_EPNUM);
    }

    u8 ep_irq = (u8)usbhw_get_eps_irq();
    if (ep_irq & BIT(CDC_RX_EPNUM & 0x07)) {
        usbhw_clr_eps_irq(BIT(CDC_RX_EPNUM & 0x07));
        handle_rx_ep();
    }
    if (ep_irq & BIT(CDC_TX_EPNUM & 0x07)) {
        usbhw_clr_eps_irq(BIT(CDC_TX_EPNUM & 0x07));
    }
}

u16 usb_cdc_rx_available(void)
{
    return (u16)((s_rx_head - s_rx_tail) & RX_RING_MASK);
}

u8 usb_cdc_read_byte(u8 *out)
{
    if (s_rx_head == s_rx_tail) {
        return 0;
    }
    *out = s_rx_ring[s_rx_tail];
    s_rx_tail = (u16)((s_rx_tail + 1) & RX_RING_MASK);
    return 1;
}

void usb_cdc_rx_flush(void)
{
    s_rx_head = 0;
    s_rx_tail = 0;
    s_rx_short_pkt = 0;
}

u8 usb_cdc_take_short_pkt(void)
{
    u8 v = s_rx_short_pkt;
    s_rx_short_pkt = 0;
    return v;
}

u32 usb_cdc_last_rx_tick(void)
{
    return s_rx_last_tick;
}

static void usb_tx_wait_idle(void)
{
    u32 t0 = clock_time();
    while (usbhw_is_ep_busy(CDC_TX_EPNUM)) {
        /* Service EP0 / USB reset in case host polls control during bulk TX */
        if (reg_ctrl_ep_irq_sta || usb_is_irq_reset()) {
            usb_cdc_poll();
        }
        if (clock_time_exceed(t0, 20000)) {
            reg_usb_ep_ctrl(CDC_TX_EPNUM) &= (u8)(~FLD_USB_EP_BUSY);
            break;
        }
    }
}

void usb_cdc_write(const u8 *data, u16 len)
{
    if (len == 0) {
        return;
    }

    u16 sent = 0;
    while (sent < len) {
        usb_tx_wait_idle();
        u16 chunk = (u16)(len - sent);
        if (chunk > CDC_TXRX_EPSIZE) {
            chunk = CDC_TXRX_EPSIZE;
        }

        reg_usb_ep_ptr(CDC_TX_EPNUM) = 0;
        for (u16 i = 0; i < chunk; i++) {
            reg_usb_ep_dat(CDC_TX_EPNUM) = data[sent + i];
        }
        reg_usb_ep_ctrl(CDC_TX_EPNUM) = FLD_EP_DAT_ACK;
        sent += chunk;
    }

    /* Send ZLP if total transfer is an exact multiple of 64 bytes */
    if ((len % CDC_TXRX_EPSIZE) == 0) {
        usb_tx_wait_idle();
        reg_usb_ep_ptr(CDC_TX_EPNUM) = 0;
        reg_usb_ep_ctrl(CDC_TX_EPNUM) = FLD_EP_DAT_ACK;
    }

    usb_tx_wait_idle();
}
