/*
 * rs_code.c — Cauchy Reed-Solomon Erasure Code Library
 *
 * Unified implementation combining init_field, encode, decode,
 * get_msg, lose_packets, and compare_msg into a single module
 * with runtime-configurable parameters.
 *
 * Based on ICSI Tech Report TR-95-048.
 * Original code Copyright (c) 1992-1997 Michael Luby / ICSI.
 */

#include "rs_code.h"

#include <stdlib.h>
#include <string.h>
#include <sys/time.h>

/* ============================================================
 *  Internal helpers
 * ============================================================ */

/* Irreducible polynomials for GF(2^w), index = w */
static const uint32_t POLYMASK[16] = {
    0x0,     0x3,   0x7,   0xB,   0x13,   0x25,  0x43,    0x83,
    0x11D, 0x211, 0x409, 0x805, 0x1053, 0x201B, 0x402B, 0x8003
};

/* Short-hand macros — these all read from ctx, so they are safe
 * as long as rs_init has been called. */
#define LFIELD      (ctx->cfg.lfield)
#define NSEGS       (ctx->cfg.nsegs)
#define MPACKETS    (ctx->cfg.mpackets)
#define RPACKETS    (ctx->cfg.rpackets)
#define NPKTS       (ctx->par.npackets)
#define PLEN        (ctx->par.plen)
#define PLENTOT     (ctx->par.plentot)
#define MLEN        (ctx->par.mlen)
#define ELEN        (ctx->par.elen)
#define TABLE_LEN   (ctx->par.table_length)
#define SMULT       (ctx->par.smult_field)
#define COLBIT      (ctx->colbit)
#define BIT(i)      (ctx->bit[i])
#define EXPTOFE(i)  (ctx->exptoFE[i])
#define FETOEXP(i)  (ctx->fetoExp[i])

/* ============================================================
 *  Lifecycle
 * ============================================================ */

int rs_init(rs_ctx_t *ctx, const rs_config_t *cfg)
{
    int i;

    if (!ctx || !cfg)
        return -1;

    /* Validate configuration */
    if (cfg->lfield < 1 || cfg->lfield > 15)
        return -1;
    if (cfg->nsegs < 1)
        return -1;
    if (cfg->mpackets < 1 || cfg->rpackets < 1)
        return -1;

    /* max(mpackets, rpackets) must be <= 2^(lfield-1) */
    {
        int max_mr = cfg->mpackets > cfg->rpackets ? cfg->mpackets : cfg->rpackets;
        int limit  = 1 << (cfg->lfield - 1);
        if (max_mr > limit)
            return -1;
    }

    memset(ctx, 0, sizeof(*ctx));
    ctx->cfg = *cfg;

    /* Compute derived parameters */
    rs_params_t *p = &ctx->par;
    p->npackets     = cfg->mpackets + cfg->rpackets;
    p->mseglen      = cfg->mpackets * cfg->lfield;
    p->plen         = cfg->nsegs * cfg->lfield;
    p->plentot      = p->plen + 1;
    p->mlen         = p->plen * cfg->mpackets;
    p->elen         = p->plen * p->npackets;
    p->table_length = 1 << cfg->lfield;
    p->smult_field  = p->table_length - 1;

    /* Allocate GF tables */
    ctx->exptoFE = (uint32_t *)calloc(p->table_length + cfg->lfield, sizeof(uint32_t));
    if (!ctx->exptoFE)
        return -2;

    ctx->fetoExp = (uint32_t *)calloc(p->table_length, sizeof(uint32_t));
    if (!ctx->fetoExp) {
        free(ctx->exptoFE);
        ctx->exptoFE = NULL;
        return -2;
    }

    /* ---- Init_field ---- */
    uint32_t carrymask;

    ctx->bit[0] = 0x1;
    for (i = 1; i < cfg->lfield; i++)
        ctx->bit[i] = ctx->bit[i - 1] << 1;
    ctx->colbit = ctx->bit[cfg->lfield - 1];
    carrymask = ctx->colbit << 1;

    ctx->exptoFE[0] = 0x1;
    for (i = 1; i < p->smult_field + cfg->lfield - 1; i++) {
        ctx->exptoFE[i] = ctx->exptoFE[i - 1] << 1;
        if (ctx->exptoFE[i] & carrymask)
            ctx->exptoFE[i] ^= POLYMASK[cfg->lfield];
    }

    ctx->fetoExp[0] = (uint32_t)-1;
    for (i = 0; i < p->smult_field; i++)
        ctx->fetoExp[ctx->exptoFE[i]] = (uint32_t)i;

    return 0;
}

void rs_free(rs_ctx_t *ctx)
{
    if (!ctx)
        return;
    free(ctx->exptoFE);
    free(ctx->fetoExp);
    memset(ctx, 0, sizeof(*ctx));
}

/* ============================================================
 *  Encode
 * ============================================================ */

void rs_encode(const rs_ctx_t *ctx, const uint32_t *message, uint32_t *packets)
{
    int i, j, k, l, m;
    int ind_seg, col_eqn, row_eqn, ind_eqn;
    int row, col, expFE;
    struct timeval start_time, end_time;

    /* Set the identifier in all packets */
    for (i = 0; i < NPKTS; i++)
        packets[i * PLENTOT] = (uint32_t)i;

    /* Copy the message into the first MPACKETS packets */
    gettimeofday(&start_time, 0);

    k = 0;
    j = 0;
    for (i = 0; i < MPACKETS; i++) {
        k++;
        for (ind_eqn = 0; ind_eqn < LFIELD; ind_eqn++) {
            for (ind_seg = 0; ind_seg < NSEGS; ind_seg++) {
                packets[k] = message[j];
                j++;
                k++;
            }
        }
    }

    /* Fill in the RPACKETS redundant packets */
    for (row = 0; row < RPACKETS; row++) {
        /* Zero out the packet */
        j = (row + MPACKETS) * PLENTOT;
        for (i = 1; i < PLENTOT; i++)
            packets[j + i] = 0;

        /* Compute Cauchy encoding */
        for (col = 0; col < MPACKETS; col++) {
            m = col * LFIELD * NSEGS;
            expFE = (SMULT - FETOEXP(row ^ col ^ COLBIT)) % SMULT;
            for (row_eqn = 0; row_eqn < LFIELD; row_eqn++) {
                k = row_eqn * NSEGS;
                for (col_eqn = 0; col_eqn < LFIELD; col_eqn++) {
                    if (EXPTOFE(expFE + row_eqn) & BIT(col_eqn)) {
                        l = col_eqn * NSEGS + m;
                        for (ind_seg = 0; ind_seg < NSEGS; ind_seg++) {
                            packets[j + 1 + ind_seg + k] ^= message[ind_seg + l];
                        }
                    }
                }
            }
        }
    }

    gettimeofday(&end_time, 0);

    if (ctx->cfg.print_debug) {
        printf("\n------------------------------------------------");
        printf("\n encode: number of seconds is %f",
               (float)(end_time.tv_sec - start_time.tv_sec) +
               (float)(end_time.tv_usec - start_time.tv_usec) / 1000000.0);
        printf("\n------------------------------------------------\n\n");
        fflush(stdout);
    }
}

/* ============================================================
 *  Decode
 * ============================================================ */

int rs_decode(const rs_ctx_t *ctx, const uint32_t *rec_packets, int *nrec,
              uint32_t *rec_message)
{
    int i, j, k, l, m;
    int index, seg_ind;
    int col_ind, row_ind, col_eqn, row_eqn;
    int Nfirstrec, Nextra;
    int *Rec_index;
    int *Col_Ind, *Row_Ind;
    int expFE;
    uint32_t *M;
    uint32_t *C, *D, *E, *F;
    struct timeval start_time, end_time;

    Rec_index = (int *)calloc(MPACKETS, sizeof(int));
    if (!Rec_index) return -1;

    Col_Ind = (int *)calloc(MPACKETS, sizeof(int));
    if (!Col_Ind) { free(Rec_index); return -1; }

    Row_Ind = (int *)calloc(RPACKETS, sizeof(int));
    if (!Row_Ind) { free(Rec_index); free(Col_Ind); return -1; }

    C = (uint32_t *)calloc(RPACKETS, sizeof(uint32_t));
    if (!C) { free(Rec_index); free(Col_Ind); free(Row_Ind); return -1; }

    D = (uint32_t *)calloc(MPACKETS, sizeof(uint32_t));
    if (!D) { free(Rec_index); free(Col_Ind); free(Row_Ind); free(C); return -1; }

    E = (uint32_t *)calloc(MPACKETS, sizeof(uint32_t));
    if (!E) { free(Rec_index); free(Col_Ind); free(Row_Ind); free(C); free(D); return -1; }

    F = (uint32_t *)calloc(RPACKETS, sizeof(uint32_t));
    if (!F) { free(Rec_index); free(Col_Ind); free(Row_Ind); free(C); free(D); free(E); return -1; }

    M = (uint32_t *)calloc(NSEGS * RPACKETS * LFIELD, sizeof(uint32_t));
    if (!M) {
        free(Rec_index); free(Col_Ind); free(Row_Ind);
        free(C); free(D); free(E); free(F);
        return -1;
    }

    if (*nrec < MPACKETS) {
        if (ctx->cfg.print_debug) {
            printf("*** Need %d packets to recover message", MPACKETS);
            printf(" but only %d packets received ***\n", *nrec);
        }
        free(Rec_index); free(Col_Ind); free(Row_Ind);
        free(C); free(D); free(E); free(F); free(M);
        return 1;
    }

    /* Initialize received message */
    for (i = 0; i < MLEN; i++)
        rec_message[i] = 0;

    gettimeofday(&start_time, 0);

    /* Move information from received packets into rec_message */
    Nfirstrec = 0;
    for (i = 0; i < MPACKETS; i++) Rec_index[i] = 0;
    m = 0;
    for (i = 0; i < *nrec; i++) {
        index = (int)rec_packets[m];
        if (index < MPACKETS) {
            j = index * PLEN;
            Rec_index[index] = 1;
            for (row_eqn = 0; row_eqn < LFIELD; row_eqn++) {
                k = row_eqn * NSEGS;
                l = j + k;
                for (seg_ind = 0; seg_ind < NSEGS; seg_ind++)
                    rec_message[seg_ind + l] = rec_packets[m + 1 + seg_ind + k];
            }
            Nfirstrec++;
        }
        m += PLENTOT;
    }

    Nextra = MPACKETS - Nfirstrec;
    if (ctx->cfg.print_debug)
        printf("Nfirstrec= %d, Nextra= %d \n", Nfirstrec, Nextra);

    /* Compute indices of missing words */
    col_ind = 0;
    for (i = 0; i < MPACKETS; i++) {
        if (Rec_index[i] == 0)
            Col_Ind[col_ind++] = i;
    }

    /* Initialize M from received extra packets */
    row_ind = 0;
    m = 0;
    for (i = 0; i < *nrec; i++) {
        if ((int)rec_packets[m] >= MPACKETS) {
            k = NSEGS * row_ind * LFIELD;
            Row_Ind[row_ind] = (int)rec_packets[m] - MPACKETS;
            for (row_eqn = 0; row_eqn < LFIELD; row_eqn++) {
                j = row_eqn * NSEGS;
                for (seg_ind = 0; seg_ind < NSEGS; seg_ind++) {
                    M[k] = rec_packets[m + 1 + seg_ind + j];
                    k++;
                }
            }
            row_ind++;
            if (row_ind >= Nextra) break;
        }
        m += PLENTOT;
    }

    /* Adjust M according to equations and rec_message */
    for (row_ind = 0; row_ind < Nextra; row_ind++) {
        for (col_ind = 0; col_ind < MPACKETS; col_ind++) {
            if (Rec_index[col_ind] == 1) {
                expFE = (SMULT - FETOEXP(Row_Ind[row_ind] ^ col_ind ^ COLBIT)) % SMULT;
                for (row_eqn = 0; row_eqn < LFIELD; row_eqn++) {
                    j = NSEGS * (row_eqn + row_ind * LFIELD);
                    for (col_eqn = 0; col_eqn < LFIELD; col_eqn++) {
                        k = NSEGS * (col_eqn + col_ind * LFIELD);
                        if (EXPTOFE(expFE + row_eqn) & BIT(col_eqn)) {
                            for (seg_ind = 0; seg_ind < NSEGS; seg_ind++) {
                                M[j + seg_ind] ^= rec_message[k + seg_ind];
                            }
                        }
                    }
                }
            }
        }
    }

    /* Compute determinant and inverse matrix */
    for (row_ind = 0; row_ind < Nextra; row_ind++) {
        for (col_ind = 0; col_ind < Nextra; col_ind++) {
            if (col_ind != row_ind) {
                C[row_ind] += FETOEXP(Row_Ind[row_ind] ^ Row_Ind[col_ind]);
                D[col_ind] += FETOEXP(Col_Ind[row_ind] ^ Col_Ind[col_ind]);
            }
            E[row_ind] += FETOEXP(Row_Ind[row_ind] ^ Col_Ind[col_ind] ^ COLBIT);
            F[col_ind] += FETOEXP(Row_Ind[row_ind] ^ Col_Ind[col_ind] ^ COLBIT);
        }
    }

    /* Recover the missing information */
    for (row_ind = 0; row_ind < Nextra; row_ind++) {
        for (col_ind = 0; col_ind < Nextra; col_ind++) {
            expFE = (int)E[col_ind] + (int)F[row_ind] - (int)C[col_ind] - (int)D[row_ind]
                  - (int)FETOEXP(Row_Ind[col_ind] ^ Col_Ind[row_ind] ^ COLBIT);
            if (expFE < 0)
                expFE = SMULT - ((-expFE) % SMULT);
            expFE = expFE % SMULT;
            j = Col_Ind[row_ind] * LFIELD * NSEGS;
            for (row_eqn = 0; row_eqn < LFIELD; row_eqn++) {
                k = row_eqn * NSEGS + j;
                for (col_eqn = 0; col_eqn < LFIELD; col_eqn++) {
                    l = NSEGS * (col_eqn + col_ind * LFIELD);
                    if (EXPTOFE(expFE + row_eqn) & BIT(col_eqn)) {
                        for (seg_ind = 0; seg_ind < NSEGS; seg_ind++) {
                            rec_message[seg_ind + k] ^= M[l];
                            l++;
                        }
                    }
                }
            }
        }
    }

    gettimeofday(&end_time, 0);

    if (ctx->cfg.print_debug) {
        printf("\n------------------------------------------------");
        printf("\n decode: number of seconds is %f",
               (float)(end_time.tv_sec - start_time.tv_sec) +
               (float)(end_time.tv_usec - start_time.tv_usec) / 1000000.0);
        printf("\n------------------------------------------------\n\n");
        fflush(stdout);
    }

    free(Rec_index); free(Col_Ind); free(Row_Ind);
    free(C); free(D); free(E); free(F); free(M);

    return 0;
}

/* ============================================================
 *  Utility: Generate test message
 * ============================================================ */

void rs_generate_message(const rs_ctx_t *ctx, uint32_t *message)
{
    int i;
    for (i = 0; i < MLEN; i++)
        message[i] = (uint32_t)i;
}

/* ============================================================
 *  Utility: Compare messages
 * ============================================================ */

int rs_compare_message(const rs_ctx_t *ctx, const uint32_t *a, const uint32_t *b)
{
    int i;
    int miss = 0;
    for (i = 0; i < MLEN; i++) {
        if (a[i] != b[i]) {
            miss++;
            if (ctx->cfg.print_debug) {
                printf("*** Error: mismatch between %x and %x in word %d\n",
                       a[i], b[i], i);
            }
        }
    }
    return miss;
}

/* ============================================================
 *  Utility: Simulate packet loss
 * ============================================================ */

long rs_simulate_loss(const rs_ctx_t *ctx, const uint32_t *packets,
                      uint32_t *rec_packets, int *nrec, int loss_start)
{
    int i, j, k, m;
    struct timeval tp;
    struct timezone tzp;

    gettimeofday(&tp, &tzp);

    if (loss_start < 0) {
        /* Default: keep the middle Mpackets packets (original behaviour) */
        loss_start = (NPKTS - MPACKETS) / 2;
    }

    *nrec = 0;
    k = 0;
    m = 0;
    for (i = loss_start; i < loss_start + MPACKETS; i++) {
        k = PLENTOT * i;
        m = PLENTOT * (*nrec);
        for (j = 0; j < PLENTOT; j++)
            rec_packets[m + j] = packets[k + j];
        (*nrec)++;
    }

    return tp.tv_usec;
}
