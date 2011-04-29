/* acoustid_compare.c */

#include "postgres.h"
#include "fmgr.h"
#include "utils/array.h"
#include "popcount.h"

/* fingerprint matcher settings */
#define ACOUSTID_MAX_BIT_ERROR 2
#define ACOUSTID_MAX_ALIGN_OFFSET 120

PG_MODULE_MAGIC;

PG_FUNCTION_INFO_V1(acoustid_compare);
Datum       acoustid_compare(PG_FUNCTION_ARGS);

/* dimension of array */
#define NDIM 1

/* useful macros for accessing int4 arrays */
#define ARRPTR(x)  ( (int4 *) ARR_DATA_PTR(x) )
#define ARRNELEMS(x)  ArrayGetNItems(ARR_NDIM(x), ARR_DIMS(x))

/* reject arrays we can't handle; but allow a NULL or empty array */
#define CHECKARRVALID(x) \
	do { \
		if (x) { \
			if (ARR_NDIM(x) != NDIM && ARR_NDIM(x) != 0) \
				ereport(ERROR, \
						(errcode(ERRCODE_ARRAY_SUBSCRIPT_ERROR), \
						 errmsg("array must be one-dimensional"))); \
			if (ARR_HASNULL(x)) \
				ereport(ERROR, \
						(errcode(ERRCODE_NULL_VALUE_NOT_ALLOWED), \
						 errmsg("array must not contain nulls"))); \
		} \
	} while(0)

#define ARRISVOID(x)  ((x) == NULL || ARRNELEMS(x) == 0)

#define BITCOUNT(x)  popcount_lookup8(x)

static float4
match_fingerprints(int4 *a, int asize, int4 *b, int bsize)
{
	int i, j, topcount;
	int numcounts = asize + bsize + 1;
	int *counts = palloc0(sizeof(int) * numcounts);

	for (i = 0; i < asize; i++) {
		int jbegin = Max(0, i - ACOUSTID_MAX_ALIGN_OFFSET);
		int jend = Min(bsize, i + ACOUSTID_MAX_ALIGN_OFFSET);
		for (j = jbegin; j < jend; j++) {
			int biterror = BITCOUNT(a[i] ^ b[j]);
			/* ereport(DEBUG5, (errmsg("comparing %d and %d with error %d", i, j, biterror))); */
			if (biterror <= ACOUSTID_MAX_BIT_ERROR) {
				int offset = i - j + bsize;
				counts[offset]++;			
			}
		}
	}

	topcount = 0;
	for (i = 0; i < numcounts; i++) {
		if (counts[i] > topcount) {
			topcount = counts[i];
		}
	}

	pfree(counts);

	return (float4)topcount / Min(asize, bsize);
}

/* PostgreSQL functions */

Datum
acoustid_compare(PG_FUNCTION_ARGS)
{
	ArrayType *a = PG_GETARG_ARRAYTYPE_P(0);
	ArrayType *b = PG_GETARG_ARRAYTYPE_P(1);
	float4 result;

	CHECKARRVALID(a);
	CHECKARRVALID(b);
	if (ARRISVOID(a) || ARRISVOID(b))
		PG_RETURN_FLOAT4(0.0f);

	result = match_fingerprints(
		ARRPTR(a), ARRNELEMS(a),
		ARRPTR(b), ARRNELEMS(b));

	PG_RETURN_FLOAT4(result);
}

