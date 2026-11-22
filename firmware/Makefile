PROJECT_NAME := tlsr_flasher_8269

COMPILE_PREFIX ?= /opt/tc32/bin/tc32
CC      := $(COMPILE_PREFIX)-elf-gcc
LD      := $(COMPILE_PREFIX)-elf-ld
OBJCOPY := $(COMPILE_PREFIX)-elf-objcopy
OBJDUMP := $(COMPILE_PREFIX)-elf-objdump
SIZE    := $(COMPILE_PREFIX)-elf-size

SDK_PATH   := sdk
CHECK_FW   := $(SDK_PATH)/tools/tl_check_fw.py
LINK_SCRIPT := $(SDK_PATH)/platform/boot/826x/boot_826x.link

OUT_DIR := build
BIN_DIR := bin

MCU_FLAGS := -DMCU_CORE_826x=1 -DCHIP_8269=1
BOOT_FLAGS := -DMCU_CORE_826x -DMCU_STARTUP_826x -DCHIP_8269=1

INCLUDES := \
	-Isrc \
	-I$(SDK_PATH)/platform \
	-I$(SDK_PATH)/platform/chip_826x \
	-I$(SDK_PATH)/proj \
	-I$(SDK_PATH)/proj/common \
	-I$(SDK_PATH)/proj/drivers \
	-I$(SDK_PATH)/proj/drivers/usb

CFLAGS := \
	-ffunction-sections \
	-fdata-sections \
	-Wall \
	-Wextra \
	-O2 \
	-fpack-struct \
	-fshort-enums \
	-finline-small-functions \
	-std=gnu99 \
	-fshort-wchar \
	-fms-extensions \
	$(MCU_FLAGS) \
	$(INCLUDES)

C_SRCS := \
	src/main.c \
	src/board_tlsr_flasher.c \
	src/usb_cdc.c \
	src/swm.c \
	src/tlsrpgm.c \
	src/mem_util.c

SDK_S_SRCS := \
	$(SDK_PATH)/platform/boot/link_cfg.S \
	$(SDK_PATH)/platform/boot/826x/cstartup_826x.S

OBJS := \
	$(patsubst src/%.c,$(OUT_DIR)/%.o,$(C_SRCS)) \
	$(OUT_DIR)/link_cfg.o \
	$(OUT_DIR)/cstartup_826x.o

ELF := $(OUT_DIR)/$(PROJECT_NAME).elf
BIN := $(BIN_DIR)/$(PROJECT_NAME).bin
LST := $(OUT_DIR)/$(PROJECT_NAME).lst

.PHONY: all clean size

all: $(BIN) $(LST) size

$(OUT_DIR) $(BIN_DIR):
	@mkdir -p $@

$(OUT_DIR)/%.o: src/%.c | $(OUT_DIR)
	$(CC) $(CFLAGS) -c -o "$@" "$<"

$(OUT_DIR)/link_cfg.o: $(SDK_PATH)/platform/boot/link_cfg.S | $(OUT_DIR)
	$(CC) $(BOOT_FLAGS) $(INCLUDES) -c -o "$@" "$<"

$(OUT_DIR)/cstartup_826x.o: $(SDK_PATH)/platform/boot/826x/cstartup_826x.S | $(OUT_DIR)
	$(CC) $(BOOT_FLAGS) $(INCLUDES) -c -o "$@" "$<"

$(ELF): $(OBJS)
	$(LD) --gc-sections -L $(SDK_PATH)/platform/lib -T $(LINK_SCRIPT) -o "$@" $(OBJS) -ldrivers_826x

$(BIN): $(ELF) | $(BIN_DIR)
	$(OBJCOPY) -O binary "$<" "$@"
	python3 $(CHECK_FW) "$@"

$(LST): $(ELF)
	$(OBJDUMP) -x -D -l -S "$<" > "$@"

size: $(ELF)
	$(SIZE) -t "$<"

clean:
	rm -rf $(OUT_DIR) $(BIN_DIR)
