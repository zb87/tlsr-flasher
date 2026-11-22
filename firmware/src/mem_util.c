#include "types.h"

void *memcpy(void *dst, const void *src, unsigned int len)
{
    u8 *d = (u8 *)dst;
    const u8 *s = (const u8 *)src;
    while (len--) {
        *d++ = *s++;
    }
    return dst;
}

void *memset(void *dst, int val, unsigned int len)
{
    u8 *d = (u8 *)dst;
    u8 v = (u8)val;
    while (len--) {
        *d++ = v;
    }
    return dst;
}

int memcmp(const void *a, const void *b, unsigned int len)
{
    const u8 *pa = (const u8 *)a;
    const u8 *pb = (const u8 *)b;
    while (len--) {
        if (*pa != *pb) {
            return (int)*pa - (int)*pb;
        }
        pa++;
        pb++;
    }
    return 0;
}
