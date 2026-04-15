/*
 * test_edge_cases.c — Edge Case & Boundary Condition Tests
 *
 * Tests minimal configurations, maximum loss tolerance,
 * extreme parameters, and boundary conditions.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "rs_code.h"

static int tests_passed = 0;
static int tests_failed = 0;

#define TEST_ASSERT(cond, msg) do {                         \
    if (cond) { tests_passed++; }                           \
    else { tests_failed++; fprintf(stderr, "FAIL: %s\n", msg); } \
} while (0)

/* ----- Test: minimal viable config (1 message + 1 redundancy) ----- */
static void test_minimal_config(void)
{
    rs_config_t cfg = {
        .lfield = 2,
        .nsegs = 1,
        .mpackets = 1,
        .rpackets = 1,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "minimal config (1+1) init should succeed");

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    /* Lose the message packet, keep the parity */
    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, 1);

    int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    TEST_ASSERT(dret == 0, "minimal config: decode succeeds from parity only");

    int miss = rs_compare_message(&ctx, message, rec_message);
    TEST_ASSERT(miss == 0, "minimal config: message recovered correctly");

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
}

/* ----- Test: maximum loss tolerance (lose all message, keep all parity) ----- */
static void test_max_loss_tolerance(void)
{
    rs_config_t cfg = {
        .lfield = 6,
        .nsegs = 3,
        .mpackets = 8,
        .rpackets = 8,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "max loss config init");

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    /* Keep only the last mpackets = parity packets */
    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, cfg.mpackets);

    int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    TEST_ASSERT(dret == 0, "max loss: decode from parity only succeeds");

    int miss = rs_compare_message(&ctx, message, rec_message);
    TEST_ASSERT(miss == 0, "max loss: message recovered from parity only");

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
}

/* ----- Test: zero loss (all message packets received) ----- */
static void test_zero_loss(void)
{
    rs_config_t cfg = {
        .lfield = 4,
        .nsegs = 2,
        .mpackets = 4,
        .rpackets = 4,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "zero loss config init");

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    /* Keep only the first mpackets = message packets */
    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, 0);

    int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    TEST_ASSERT(dret == 0, "zero loss: decode trivially succeeds");

    int miss = rs_compare_message(&ctx, message, rec_message);
    TEST_ASSERT(miss == 0, "zero loss: message matches");

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
}

/* ----- Test: boundary lfield = 1 ----- */
static void test_lfield_1(void)
{
    rs_config_t cfg = {
        .lfield = 1,
        .nsegs = 1,
        .mpackets = 1,
        .rpackets = 1,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    /* lfield=1 means max(mpackets, rpackets) <= 2^0 = 1, this should work */
    TEST_ASSERT(ret == 0, "lfield=1 config init");

    if (ret == 0) {
        TEST_ASSERT(ctx.par.table_length == 2, "lfield=1 table_length == 2");
        TEST_ASSERT(ctx.par.smult_field == 1, "lfield=1 smult_field == 1");
        rs_free(&ctx);
    }
}

/* ----- Test: high redundancy ratio (8 data + 16 parity) ----- */
static void test_high_redundancy(void)
{
    rs_config_t cfg = {
        .lfield = 5,
        .nsegs = 2,
        .mpackets = 4,
        .rpackets = 12,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "high redundancy config init");

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    /* Lose all message packets — recover from parity */
    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, cfg.mpackets);

    int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    TEST_ASSERT(dret == 0, "high redundancy: decode succeeds");

    int miss = rs_compare_message(&ctx, message, rec_message);
    TEST_ASSERT(miss == 0, "high redundancy: message matches");

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
}

/* ----- Test: rs_free on zeroed context (should not crash) ----- */
static void test_free_zeroed(void)
{
    rs_ctx_t ctx;
    memset(&ctx, 0, sizeof(ctx));
    /* Should be a safe no-op */
    rs_free(&ctx);
    TEST_ASSERT(1, "rs_free on zeroed context does not crash");
}

/* ----- Test: repeated init/free cycles ----- */
static void test_repeated_init_free(void)
{
    rs_config_t cfg = RS_CONFIG_DEFAULTS;
    cfg.print_debug = 0;

    for (int cycle = 0; cycle < 5; cycle++) {
        rs_ctx_t ctx;
        int ret = rs_init(&ctx, &cfg);
        TEST_ASSERT(ret == 0, "repeated init/free cycle should succeed");
        rs_free(&ctx);
    }
}

/* ----- Test: nsegs = 1 ----- */
static void test_nsegs_1(void)
{
    rs_config_t cfg = {
        .lfield = 4,
        .nsegs = 1,
        .mpackets = 4,
        .rpackets = 4,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "nsegs=1 config init");

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, -1);

    int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    TEST_ASSERT(dret == 0, "nsegs=1: decode succeeds");

    int miss = rs_compare_message(&ctx, message, rec_message);
    TEST_ASSERT(miss == 0, "nsegs=1: message matches");

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
}

int main(void)
{
    printf("=== Edge Case & Boundary Tests ===\n\n");

    test_minimal_config();
    test_max_loss_tolerance();
    test_zero_loss();
    test_lfield_1();
    test_high_redundancy();
    test_free_zeroed();
    test_repeated_init_free();
    test_nsegs_1();

    printf("\n=== Results: %d passed, %d failed ===\n",
           tests_passed, tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
