/*
 * test_encode_decode.c — Encode/Decode Roundtrip Tests
 *
 * Verifies that the Cauchy RS encoding followed by decoding
 * correctly recovers the original message under various loss
 * scenarios.
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

/* Helper: run a full encode -> simulate loss -> decode cycle */
static int run_roundtrip(const rs_config_t *cfg, int loss_start)
{
    rs_ctx_t ctx;
    int ret = rs_init(&ctx, cfg);
    if (ret != 0) return -1;

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    if (!message || !rec_message || !packets || !rec_packets) {
        free(message); free(rec_message); free(packets); free(rec_packets);
        rs_free(&ctx);
        return -2;
    }

    /* Generate, encode, lose, decode */
    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    int nrec = 0;
    rs_simulate_loss(&ctx, packets, rec_packets, &nrec, loss_start);

    int decode_ret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    int miss = 0;
    if (decode_ret == 0) {
        miss = rs_compare_message(&ctx, message, rec_message);
    }

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);

    return (decode_ret == 0 && miss == 0) ? 0 : 1;
}

/* ----- Test: default config roundtrip ----- */
static void test_default_roundtrip(void)
{
    rs_config_t cfg = RS_CONFIG_DEFAULTS;
    cfg.print_debug = 0;

    int ret = run_roundtrip(&cfg, -1);
    TEST_ASSERT(ret == 0, "default config encode/decode roundtrip");
}

/* ----- Test: small config roundtrip ----- */
static void test_small_config(void)
{
    rs_config_t cfg = {
        .lfield = 4,
        .nsegs = 2,
        .mpackets = 4,
        .rpackets = 4,
        .print_debug = 0
    };

    int ret = run_roundtrip(&cfg, -1);
    TEST_ASSERT(ret == 0, "small config (4+4) encode/decode roundtrip");
}

/* ----- Test: different loss patterns ----- */
static void test_loss_patterns(void)
{
    rs_config_t cfg = {
        .lfield = 6,
        .nsegs = 4,
        .mpackets = 8,
        .rpackets = 8,
        .print_debug = 0
    };

    rs_ctx_t ctx;
    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "init for loss pattern test");

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    rs_generate_message(&ctx, message);
    rs_encode(&ctx, message, packets);

    /* Pattern 1: lose all message packets, keep only parity */
    {
        int nrec = 0;
        /* Keep the last mpackets packets (all parity) */
        rs_simulate_loss(&ctx, packets, rec_packets, &nrec, ctx.cfg.mpackets);
        TEST_ASSERT(nrec == ctx.cfg.mpackets, "loss pattern 1: received packet count");

        int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
        TEST_ASSERT(dret == 0, "loss pattern 1: decode succeeds");

        int miss = rs_compare_message(&ctx, message, rec_message);
        TEST_ASSERT(miss == 0, "loss pattern 1: message matches (all parity recovery)");
    }

    /* Pattern 2: lose all parity packets, keep only message */
    {
        int nrec = 0;
        rs_simulate_loss(&ctx, packets, rec_packets, &nrec, 0);
        TEST_ASSERT(nrec == ctx.cfg.mpackets, "loss pattern 2: received packet count");

        int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
        TEST_ASSERT(dret == 0, "loss pattern 2: decode succeeds");

        int miss = rs_compare_message(&ctx, message, rec_message);
        TEST_ASSERT(miss == 0, "loss pattern 2: message matches (all message recovery)");
    }

    /* Pattern 3: lose first half of message + first half of parity */
    {
        int nrec = 0;
        /* Keep packets from index mpackets/2 to mpackets/2 + mpackets */
        int start = ctx.cfg.mpackets / 2;
        rs_simulate_loss(&ctx, packets, rec_packets, &nrec, start);

        int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
        TEST_ASSERT(dret == 0, "loss pattern 3: decode succeeds");

        int miss = rs_compare_message(&ctx, message, rec_message);
        TEST_ASSERT(miss == 0, "loss pattern 3: message matches (mixed loss)");
    }

    free(message); free(rec_message); free(packets); free(rec_packets);
    rs_free(&ctx);
}

/* ----- Test: insufficient packets for recovery ----- */
static void test_insufficient_packets(void)
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
    TEST_ASSERT(ret == 0, "init for insufficient packets test");

    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));

    /* Only provide mpackets - 1 packets — should fail */
    int nrec = cfg.mpackets - 1;
    int dret = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    TEST_ASSERT(dret == 1, "insufficient packets should return 1");

    free(rec_packets); free(rec_message);
    rs_free(&ctx);
}

/* ----- Test: message generate and compare consistency ----- */
static void test_msg_generate_compare(void)
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
    TEST_ASSERT(ret == 0, "init for msg test");

    uint32_t *a = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *b = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));

    rs_generate_message(&ctx, a);
    rs_generate_message(&ctx, b);

    /* Two generated messages should be identical */
    int miss = rs_compare_message(&ctx, a, b);
    TEST_ASSERT(miss == 0, "two generated messages should be identical");

    /* Corrupt one word and verify mismatch detected */
    b[0] ^= 0xFFFFFFFF;
    miss = rs_compare_message(&ctx, a, b);
    TEST_ASSERT(miss > 0, "corrupted message should be detected");

    free(a); free(b);
    rs_free(&ctx);
}

/* ----- Test: medium config roundtrip ----- */
static void test_medium_config(void)
{
    rs_config_t cfg = {
        .lfield = 8,
        .nsegs = 10,
        .mpackets = 50,
        .rpackets = 50,
        .print_debug = 0
    };

    int ret = run_roundtrip(&cfg, -1);
    TEST_ASSERT(ret == 0, "medium config (50+50) encode/decode roundtrip");
}

int main(void)
{
    printf("=== Encode/Decode Roundtrip Tests ===\n\n");

    test_default_roundtrip();
    test_small_config();
    test_loss_patterns();
    test_insufficient_packets();
    test_msg_generate_compare();
    test_medium_config();

    printf("\n=== Results: %d passed, %d failed ===\n",
           tests_passed, tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
