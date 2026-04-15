/*
 * driver_lib.c — Demo driver using the rs_code library API
 *
 * This replaces the original driver.c, demonstrating the new
 * runtime-configurable API.
 */

#include <stdio.h>
#include <stdlib.h>
#include <sys/time.h>
#include "rs_code.h"

int main(void)
{
    rs_ctx_t ctx;
    rs_config_t cfg = RS_CONFIG_DEFAULTS;
    int ret;
    int nrec;
    long seed;
    int return_code;
    struct timeval stime, etime;

    ret = rs_init(&ctx, &cfg);
    if (ret != 0) {
        fprintf(stderr, "rs_init failed: %d\n", ret);
        return 1;
    }

    uint32_t *message     = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *rec_message = (uint32_t *)calloc(ctx.par.mlen, sizeof(uint32_t));
    uint32_t *packets     = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));
    uint32_t *rec_packets = (uint32_t *)calloc(ctx.par.npackets * ctx.par.plentot, sizeof(uint32_t));

    if (!message || !rec_message || !packets || !rec_packets) {
        fprintf(stderr, "malloc failed\n");
        return 1;
    }

    printf("--------------------------------------\n");

    rs_generate_message(&ctx, message);
    printf("\nDone getting message of %d bytes \n", ctx.par.mlen * 4);

    gettimeofday(&stime, 0);

    rs_encode(&ctx, message, packets);
    printf("Done encoding %d packets\n", ctx.par.npackets);

    seed = rs_simulate_loss(&ctx, packets, rec_packets, &nrec, -1);
    printf("Received %d packets with seed %ld \n", nrec, seed);

    return_code = rs_decode(&ctx, rec_packets, &nrec, rec_message);
    printf("Done with decoding\n");

    if (return_code == 0) {
        int miss = rs_compare_message(&ctx, message, rec_message);
        printf("Done with comparison — %d mismatches\n", miss);
    }

    gettimeofday(&etime, 0);

    float total_mb = (float)ctx.par.elen * 4 / 1000000.0f;
    float total_s  = (float)(etime.tv_sec - stime.tv_sec) +
                     (float)(etime.tv_usec - stime.tv_usec) / 1000000.0f;

    printf("--------- Cauchy Code ---------------\n");
    printf("Number of Mbytes processed is %f\n", total_mb);
    printf("Time in seconds is %f\n", total_s);
    printf("MBytes per second is %f\n", total_s > 0 ? total_mb / total_s : 0.0f);
    printf("Overhead is %d\n", ctx.cfg.mpackets);
    printf("Encoding redundancy is %f\n", 1.0 + (float)ctx.cfg.rpackets / (float)ctx.cfg.mpackets);
    printf("Fraction of packets received is %f\n\n", (float)nrec / (float)ctx.par.npackets);

    free(message);
    free(rec_message);
    free(packets);
    free(rec_packets);
    rs_free(&ctx);

    return 0;
}
