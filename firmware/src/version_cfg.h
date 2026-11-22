#pragma once

#define APP_RELEASE                 0x10
#define APP_BUILD                   0x01
#define STACK_RELEASE               0x00
#define STACK_BUILD                 0x08

#define MANUFACTURER_CODE_TELINK    0x1141
#define IMAGE_TYPE                  0x8269
#define FILE_VERSION                ((APP_RELEASE << 24) | (APP_BUILD << 16) | (STACK_RELEASE << 8) | STACK_BUILD)

/* Standalone flash image starting at 0x00000 */
#define IS_BOOT_LOADER_IMAGE        0
#define RESV_FOR_APP_RAM_CODE_SIZE  0
#define IMAGE_OFFSET                0
