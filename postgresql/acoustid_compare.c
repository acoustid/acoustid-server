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

#define MATCH_BITS 14
#define MATCH_MASK ((1 << MATCH_BITS) - 1)
#define MATCH_STRIP(x) ((uint32_t)(x) >> (32 - MATCH_BITS))

PG_MODULE_MAGIC;

PG_FUNCTION_INFO_V1(acoustid_compare);
Datum       acoustid_compare(PG_FUNCTION_ARGS);

PG_FUNCTION_INFO_V1(acoustid_compare2);
Datum       acoustid_compare2(PG_FUNCTION_ARGS);

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

/* From http://en.wikipedia.org/wiki/Hamming_weight */

const uint64_t m1  = 0x5555555555555555; /* binary: 0101... */
const uint64_t m2  = 0x3333333333333333; /* binary: 00110011.. */
const uint64_t m4  = 0x0f0f0f0f0f0f0f0f; /* binary:  4 zeros,  4 ones ... */
const uint64_t m8  = 0x00ff00ff00ff00ff; /* binary:  8 zeros,  8 ones ... */
const uint64_t m16 = 0x0000ffff0000ffff; /* binary: 16 zeros, 16 ones ... */
const uint64_t m32 = 0x00000000ffffffff; /* binary: 32 zeros, 32 ones */
const uint64_t hff = 0xffffffffffffffff; /* binary: all ones */
const uint64_t h01 = 0x0101010101010101; /* the sum of 256 to the power of 0,1,2,3... */

inline static int
popcount_3(uint64_t x)
{
	x -= (x >> 1) & m1;             /* put count of each 2 bits into those 2 bits */
	x = (x & m2) + ((x >> 2) & m2); /* put count of each 4 bits into those 4 bits */
	x = (x + (x >> 4)) & m4;        /* put count of each 8 bits into those 8 bits */
	return (x * h01) >> 56;         /* returns left 8 bits of x + (x<<8) + (x<<16) + (x<<24) + ...  */
}

#define BITCOUNT(x)  popcount_lookup8(x)
#define BITCOUNT64(x)  popcount_3(x)


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

static float4
match_fingerprints2(int4 *a, int asize, int4 *b, int bsize, int maxoffset)
{
	int i, topcount, topoffset, size, biterror, minsize;
	int numcounts = asize + bsize + 1;
	unsigned short *counts = palloc0(sizeof(unsigned short) * numcounts);
	uint16_t *aoffsets = palloc0(sizeof(uint16_t) * MATCH_MASK), *boffsets = palloc0(sizeof(uint16_t) * MATCH_MASK);
	uint64_t *adata, *bdata;
	float4 score;

	for (i = 0; i < asize; i++) {
		aoffsets[MATCH_STRIP(a[i])] = i;
	}
	for (i = 0; i < bsize; i++) {
		boffsets[MATCH_STRIP(b[i])] = i;
	}

	topcount = 0;
	topoffset = 0;
	for (i = 0; i < MATCH_MASK; i++) {
		if (aoffsets[i] && boffsets[i]) {
			int offset = aoffsets[i] - boffsets[i];
			if (maxoffset == 0 || (-maxoffset <= offset && offset <= maxoffset)) {
				offset += bsize;
				counts[offset]++;
				if (counts[offset] > topcount) {
					topcount = counts[offset];
					topoffset = offset;
				}
			}
		}
	}

	topoffset -= bsize;
	pfree(boffsets);
	pfree(aoffsets);
	pfree(counts);

	minsize = Min(asize, bsize) & ~1;
	if (topoffset < 0) {
		b -= topoffset;
		bsize = Max(0, bsize + topoffset);
	}
	else {
		a += topoffset;
		asize = Max(0, asize - topoffset);
	}

	size = Min(asize, bsize) / 2;
	if (!size) {
		return 0.0;
	}

	ereport(DEBUG5, (errmsg("offset %d, offset score %d, size %d", topoffset, topcount, size * 2)));
	adata = (uint64_t *)a;
	bdata = (uint64_t *)b;
	biterror = 0;
	for (i = 0; i < size; i++, adata++, bdata++) {
		biterror += BITCOUNT64(*adata ^ *bdata);
	}
	score = (size * 2.0 / minsize) * (1.0 - 2.0 * (float4)biterror / (64 * size));
	if (size < 200) {
		score *= pow(log(size) / log(200), 1.5);
	}
	return score;
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

Datum
acoustid_compare2(PG_FUNCTION_ARGS)
{
	ArrayType *a = PG_GETARG_ARRAYTYPE_P(0);
	ArrayType *b = PG_GETARG_ARRAYTYPE_P(1);
	int maxoffset = PG_GETARG_INT32(2);
	float4 result;

	CHECKARRVALID(a);
	CHECKARRVALID(b);
	if (ARRISVOID(a) || ARRISVOID(b))
		PG_RETURN_FLOAT4(0.0f);

	result = match_fingerprints2(
		ARRPTR(a), ARRNELEMS(a),
		ARRPTR(b), ARRNELEMS(b),
		maxoffset);

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

