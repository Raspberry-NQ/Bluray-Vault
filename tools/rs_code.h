/*
 * rs_code.h — Cauchy Reed-Solomon Erasure Code Library
 *
 * Based on ICSI Tech Report TR-95-048:
 *   "An XOR-Based Erasure-Resilient Coding Scheme"
 *   Bloemer, Kalfane, Karpinski, Karp, Luby, Zuckerman
 *
 * Original code Copyright (c) 1992-1997 Michael Luby / ICSI.
 * Refactored into a unified library with runtime-configurable parameters.
 */

#ifndef RS_CODE_H
#define RS_CODE_H

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ---------- Configuration ---------- */

typedef struct {
    int lfield;      /* log2 of Galois field size (1..15) */
    int nsegs;       /* number of segments per packet */
    int mpackets;    /* number of message packets */
    int rpackets;    /* number of redundant packets */
    int print_debug; /* non-zero to enable debug prints */
} rs_config_t;

/* Sensible defaults matching the original code */
#define RS_CONFIG_DEFAULTS { \
    .lfield    = 10,  \
    .nsegs     = 25,  \
    .mpackets  = 200, \
    .rpackets  = 200, \
    .print_debug = 1   \
}

/* ---------- Derived constants (computed by rs_init) ---------- */

typedef struct {
    int npackets;     /* mpackets + rpackets */
    int mseglen;      /* mpackets * lfield */
    int plen;         /* nsegs * lfield (payload words per packet) */
    int plentot;      /* plen + 1 (including index word) */
    int mlen;         /* plen * mpackets (message length in words) */
    int elen;         /* plen * npackets (encoding length in words) */
    int table_length; /* 1 << lfield */
    int smult_field;  /* table_length - 1 */
} rs_params_t;

/* ---------- Library context ---------- */

typedef struct {
    rs_config_t cfg;
    rs_params_t par;

    /* Galois field tables (heap-allocated) */
    uint32_t *exptoFE;  /* [table_length + lfield] */
    uint32_t *fetoExp;  /* [table_length]           */
    uint32_t  colbit;
    uint32_t  bit[16];  /* BIT array, index 0..lfield-1 */
} rs_ctx_t;

/* ---------- Lifecycle ---------- */

/*
 * rs_init — Create and initialize a library context.
 * Allocates GF lookup tables and pre-computes derived parameters.
 * Returns 0 on success, -1 on invalid config, -2 on allocation failure.
 */
int rs_init(rs_ctx_t *ctx, const rs_config_t *cfg);

/*
 * rs_free — Release resources held by a context.
 */
void rs_free(rs_ctx_t *ctx);

/* ---------- Core operations ---------- */

/*
 * rs_encode — Encode a message into packets (message + redundant).
 *
 *   message: input, length must be ctx->par.mlen uint32_t words
 *   packets: output, length must be ctx->par.npackets * ctx->par.plentot words
 */
void rs_encode(const rs_ctx_t *ctx, const uint32_t *message, uint32_t *packets);

/*
 * rs_decode — Recover the original message from a subset of received packets.
 *
 *   rec_packets: input, received packets (each Plentot words, index in [0])
 *   nrec:        in/out — on entry, number of received packets;
 *                must be >= mpackets for successful recovery.
 *   rec_message: output, length must be ctx->par.mlen words.
 *
 * Returns 0 on success, 1 if not enough packets, -1 on alloc failure.
 */
int rs_decode(const rs_ctx_t *ctx, const uint32_t *rec_packets, int *nrec,
              uint32_t *rec_message);

/* ---------- Utility operations ---------- */

/*
 * rs_generate_message — Fill a message buffer with a test pattern (0, 1, 2, ...).
 */
void rs_generate_message(const rs_ctx_t *ctx, uint32_t *message);

/*
 * rs_compare_message — Compare two message buffers word-by-word.
 * Prints mismatches to stdout.  Returns the number of mismatched words.
 */
int rs_compare_message(const rs_ctx_t *ctx, const uint32_t *a, const uint32_t *b);

/*
 * rs_simulate_loss — Simulate packet loss by selecting a contiguous block
 * of Mpackets packets from the middle of the encoded stream.
 *
 *   packets:    input, the full encoded packet array
 *   rec_packets:output, the surviving packets
 *   nrec:       output, number of packets received
 *   loss_start: index of first packet to drop (0-based). If -1, drops from
 *               the middle (default behaviour of original code).
 *
 * Returns a pseudo-random seed (tv_usec).
 */
long rs_simulate_loss(const rs_ctx_t *ctx, const uint32_t *packets,
                      uint32_t *rec_packets, int *nrec, int loss_start);

#ifdef __cplusplus
}
#endif

#endif /* RS_CODE_H */
