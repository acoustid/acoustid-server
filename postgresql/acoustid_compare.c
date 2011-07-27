/* acoustid_compare.c */

#include "postgres.h"
#include "fmgr.h"
#include "utils/array.h"
#include "catalog/pg_type.h"
#include "popcount.h"

/* fingerprint matcher settings */
#define ACOUSTID_MAX_BIT_ERROR 2
#define ACOUSTID_MAX_ALIGN_OFFSET 120
#define ACOUSTID_QUERY_START 80
#define ACOUSTID_QUERY_LENGTH 120
#define ACOUSTID_QUERY_BITS 28
#define ACOUSTID_QUERY_MASK (((1<<ACOUSTID_QUERY_BITS)-1)<<(32-ACOUSTID_QUERY_BITS))
#define ACOUSTID_QUERY_STRIP(x) ((x) & ACOUSTID_QUERY_MASK)

PG_MODULE_MAGIC;

PG_FUNCTION_INFO_V1(acoustid_compare);
Datum       acoustid_compare(PG_FUNCTION_ARGS);

PG_FUNCTION_INFO_V1(acoustid_extract_query);
Datum       acoustid_extract_query(PG_FUNCTION_ARGS);

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

static ArrayType *
new_intArrayType(int num)
{
	ArrayType  *r;
	int nbytes = ARR_OVERHEAD_NONULLS(1) + sizeof(int) * num;

	r = (ArrayType *) palloc0(nbytes);

	SET_VARSIZE(r, nbytes);
	ARR_NDIM(r) = 1;
	r->dataoffset = 0;          /* marker for no null bitmap */
	ARR_ELEMTYPE(r) = INT4OID;
	ARR_DIMS(r)[0] = num;
	ARR_LBOUND(r)[0] = 1;

	return r;
}

Datum
acoustid_extract_query(PG_FUNCTION_ARGS)
{
	ArrayType *a = PG_GETARG_ARRAYTYPE_P(0), *q;
	int4 *orig, *query;
	int i, j, size, cleansize, querysize;

	CHECKARRVALID(a);
	size = ARRNELEMS(a);
	orig = ARRPTR(a);

	cleansize = 0;
	for (i = 0; i < size; i++) {
		if (orig[i] != 627964279) {
			cleansize++;
		}
	}

	if (cleansize <= 0) {
		PG_RETURN_ARRAYTYPE_P(new_intArrayType(0));
	}

	q = new_intArrayType(120);
	query = ARRPTR(q);
	querysize = 0;
	for (i = Max(0, Min(cleansize - ACOUSTID_QUERY_LENGTH, ACOUSTID_QUERY_START)); i < size && querysize < ACOUSTID_QUERY_LENGTH; i++) {
		int4 x = ACOUSTID_QUERY_STRIP(orig[i]);
		if (orig[i] == 627964279) {
			goto next; // silence
		}
		for (j = 0; j < querysize; j++) { // XXX O(N^2) dupe detection, try if O(N*logN) sorting works better on the tiny array
			if (query[j] == x) {
				goto next; // duplicate
			}
		}
		query[querysize++] = x;
	next: ;
	}
	ARR_DIMS(q)[0] = querysize;

	PG_RETURN_ARRAYTYPE_P(q);
}

