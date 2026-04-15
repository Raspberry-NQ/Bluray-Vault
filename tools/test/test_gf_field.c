/*
 * test_gf_field.c — Galois Field Initialization Tests
 *
 * Validates that rs_init correctly builds GF(2^w) lookup tables
 * for various field sizes, and that the exponent/element round-trips
 * are consistent.
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

/* ----- Test: basic init / free lifecycle ----- */
static void test_init_free(void)
{
    rs_ctx_t ctx;
    rs_config_t cfg = RS_CONFIG_DEFAULTS;

    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "rs_init with default config should succeed");
    TEST_ASSERT(ctx.exptoFE != NULL, "exptoFE should be allocated");
    TEST_ASSERT(ctx.fetoExp != NULL, "fetoExp should be allocated");
    TEST_ASSERT(ctx.par.npackets == cfg.mpackets + cfg.rpackets,
                "npackets should be mpackets + rpackets");
    TEST_ASSERT(ctx.par.table_length == (1 << cfg.lfield),
                "table_length should be 2^lfield");

    rs_free(&ctx);
    TEST_ASSERT(ctx.exptoFE == NULL, "rs_free should zero exptoFE");
    TEST_ASSERT(ctx.fetoExp == NULL, "rs_free should zero fetoExp");
}

/* ----- Test: invalid configurations ----- */
static void test_invalid_config(void)
{
    rs_ctx_t ctx;
    rs_config_t cfg;
    int ret;

    /* lfield = 0 */
    cfg = (rs_config_t){ .lfield = 0, .nsegs = 25, .mpackets = 200, .rpackets = 200, .print_debug = 0 };
    ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == -1, "lfield=0 should be rejected");

    /* lfield = 16 */
    cfg = (rs_config_t){ .lfield = 16, .nsegs = 25, .mpackets = 200, .rpackets = 200, .print_debug = 0 };
    ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == -1, "lfield=16 should be rejected");

    /* nsegs = 0 */
    cfg = (rs_config_t){ .lfield = 10, .nsegs = 0, .mpackets = 200, .rpackets = 200, .print_debug = 0 };
    ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == -1, "nsegs=0 should be rejected");

    /* mpackets > 2^(lfield-1) */
    cfg = (rs_config_t){ .lfield = 4, .nsegs = 1, .mpackets = 100, .rpackets = 1, .print_debug = 0 };
    ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == -1, "mpackets > 2^(lfield-1) should be rejected");

    /* NULL ctx */
    ret = rs_init(NULL, &cfg);
    TEST_ASSERT(ret == -1, "NULL ctx should be rejected");

    /* NULL cfg */
    ret = rs_init(&ctx, NULL);
    TEST_ASSERT(ret == -1, "NULL cfg should be rejected");
}

/* ----- Test: GF table round-trip consistency ----- */
static void test_gf_roundtrip(void)
{
    rs_ctx_t ctx;
    rs_config_t cfg = RS_CONFIG_DEFAULTS;
    cfg.print_debug = 0;

    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "init for roundtrip test");

    /* Every non-zero element in GF(2^w) should satisfy:
     *   fetoExp[exptoFE[i]] == i   for i in [0, smult_field)
     *   exptoFE[fetoExp[a]] == a   for a in the field */
    int ok = 1;
    for (int i = 0; i < ctx.par.smult_field; i++) {
        uint32_t fe = ctx.exptoFE[i];
        if (ctx.fetoExp[fe] != (uint32_t)i) {
            ok = 0;
            break;
        }
    }
    TEST_ASSERT(ok, "exptoFE -> fetoExp round-trip for all exponents");

    /* exptoFE[0] should be 1 (the multiplicative identity) */
    TEST_ASSERT(ctx.exptoFE[0] == 1, "exptoFE[0] should be 1");

    /* fetoExp[0] should be 0xFFFFFFFF (sentinel for the zero element) */
    TEST_ASSERT(ctx.fetoExp[0] == (uint32_t)-1, "fetoExp[0] should be -1 sentinel");

    /* exptoFE[i] should never be 0 for valid exponents */
    ok = 1;
    for (int i = 0; i < ctx.par.smult_field; i++) {
        if (ctx.exptoFE[i] == 0) { ok = 0; break; }
    }
    TEST_ASSERT(ok, "no zero in exptoFE for valid exponents");

    rs_free(&ctx);
}

/* ----- Test: multiple field sizes ----- */
static void test_various_lfield(void)
{
    /* Test GF(2^w) for w = 4, 8, 10 */
    int lfields[] = {4, 8, 10};
    int n = sizeof(lfields) / sizeof(lfields[0]);

    for (int idx = 0; idx < n; idx++) {
        rs_ctx_t ctx;
        rs_config_t cfg = {
            .lfield = lfields[idx],
            .nsegs = 1,
            .mpackets = 2,
            .rpackets = 2,
            .print_debug = 0
        };
        int ret = rs_init(&ctx, &cfg);
        TEST_ASSERT(ret == 0, "init with various lfield values");

        /* Verify table sizes */
        TEST_ASSERT((int)ctx.par.table_length == (1 << lfields[idx]),
                     "table_length matches 2^lfield");

        /* Verify round-trip for this field size */
        int ok = 1;
        for (int i = 0; i < ctx.par.smult_field; i++) {
            if (ctx.fetoExp[ctx.exptoFE[i]] != (uint32_t)i) {
                ok = 0; break;
            }
        }
        TEST_ASSERT(ok, "round-trip consistency for varying lfield");

        rs_free(&ctx);
    }
}

/* ----- Test: GF multiplicative identity property ----- */
static void test_gf_identity(void)
{
    rs_ctx_t ctx;
    rs_config_t cfg = RS_CONFIG_DEFAULTS;
    cfg.print_debug = 0;

    int ret = rs_init(&ctx, &cfg);
    TEST_ASSERT(ret == 0, "init for identity test");

    /* exptoFE[0] == 1 (identity element) */
    TEST_ASSERT(ctx.exptoFE[0] == 1, "GF identity: exptoFE[0] == 1");

    /* COLBIT should be 2^(lfield-1) */
    uint32_t expected_colbit = 1u << (cfg.lfield - 1);
    TEST_ASSERT(ctx.colbit == expected_colbit, "COLBIT should be 2^(lfield-1)");

    rs_free(&ctx);
}

int main(void)
{
    printf("=== GF Field Initialization Tests ===\n\n");

    test_init_free();
    test_invalid_config();
    test_gf_roundtrip();
    test_various_lfield();
    test_gf_identity();

    printf("\n=== Results: %d passed, %d failed ===\n",
           tests_passed, tests_failed);

    return tests_failed > 0 ? 1 : 0;
}
