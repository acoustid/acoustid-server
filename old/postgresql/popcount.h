#ifndef ACOUSTID_POPCOUNT_H_
#define ACOUSTID_POPCOUNT_H_

#include "popcount-table8.h"
#include "popcount-table16.h"

static inline int popcount_lookup8(unsigned int x)
{
	return
		popcount_table_8bit[x & 0xffu] +
		popcount_table_8bit[(x >> 8) & 0xffu] +
		popcount_table_8bit[(x >> 16) & 0xffu] +
		popcount_table_8bit[x >> 24];
}

static inline int popcount_lookup16(unsigned int x)
{
	return
		popcount_table_16bit[x & 0xffffu] +
		popcount_table_16bit[x >> 16];
}

#endif

