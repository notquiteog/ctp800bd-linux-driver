/* SPDX-License-Identifier: MIT */
#define _POSIX_C_SOURCE 200809L
#include <cups/cups.h>
#include <cups/ppd.h>
#include <cups/raster.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Four inches at 203 dpi; thirteen inches maximum label length. */
#define MAX_WIDTH 812u
#define MAX_HEIGHT 2639u
static volatile sig_atomic_t cancelled;
static void stop_job(int sig) { (void)sig; cancelled = 1; }

static const char *choice(ppd_file_t *ppd, int count, cups_option_t *options,
                          const char *name, const char *fallback) {
    const char *value = cupsGetOption(name, count, options);
    if (value) return value;
    ppd_choice_t *marked = ppd ? ppdFindMarkedChoice(ppd, name) : NULL;
    return marked ? marked->choice : fallback;
}

static int number(const char *value, int low, int high, const char *name) {
    char *end;
    errno = 0;
    long n = strtol(value, &end, 10);
    if (errno || !*value || *end || n < low || n > high) {
        fprintf(stderr, "ERROR: Invalid %s; expected %d..%d.\n", name, low, high);
        return -1;
    }
    return (int)n;
}

int main(int argc, char **argv) {
    if (argc != 6 && argc != 7) {
        fputs("Usage: rastertoctp800bd job-id user title copies options [raster-file]\n", stderr);
        return 1;
    }
    struct sigaction action = {0};
    action.sa_handler = stop_job;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    signal(SIGPIPE, SIG_IGN);
    cups_option_t *options = NULL;
    int count = cupsParseOptions(argv[5], 0, &options);
    const char *path = getenv("PPD");
    ppd_file_t *ppd = path ? ppdOpenFile(path) : NULL;
    int result = 1, fd = STDIN_FILENO;
    cups_raster_t *raster = NULL;
    unsigned char *row = NULL, *bitmap = NULL;
    if (path && !ppd) { fputs("ERROR: Cannot read PPD.\n", stderr); goto done; }
    if (ppd) { ppdMarkDefaults(ppd); cupsMarkOptions(ppd, count, options); }
#define OPT(name, fallback) choice(ppd, count, options, name, fallback)
    int density = number(OPT("Darkness", "8"), 0, 15, "Darkness");
    int speed = number(OPT("PrintSpeed", "3"), 1, 5, "PrintSpeed");
    int gap = number(OPT("LabelGap", "3"), 0, 6, "LabelGap");
    int threshold = number(OPT("Threshold", "128"), 1, 255, "Threshold");
    int direction = number(OPT("Direction", "0"), 0, 1, "Direction");
    const char *media = OPT("MediaType", "Labels");
    const char *mode = OPT("Dither", "Threshold");
    if (density < 0 || speed < 0 || gap < 0 || threshold < 0 || direction < 0) goto done;
    if (strcmp(media, "Labels") && strcmp(media, "Continuous")) {
        fputs("ERROR: MediaType must be Labels or Continuous.\n", stderr); goto done;
    }
    if (strcmp(mode, "Threshold") && strcmp(mode, "Ordered")) {
        fputs("ERROR: Dither must be Threshold or Ordered.\n", stderr); goto done;
    }
    if (argc == 7 && (fd = open(argv[6], O_RDONLY)) < 0) {
        perror("ERROR: Cannot open raster input"); goto done;
    }
    raster = cupsRasterOpen(fd, CUPS_RASTER_READ);
    if (!raster) { fputs("ERROR: Cannot open raster stream.\n", stderr); goto done; }
    cups_page_header2_t h;
    unsigned pages = 0;
    while (!cancelled && cupsRasterReadHeader2(raster, &h)) {
        if (!h.cupsWidth || h.cupsWidth > MAX_WIDTH || !h.cupsHeight ||
            h.cupsHeight > MAX_HEIGHT || h.HWResolution[0] != 203 || h.HWResolution[1] != 203 ||
            h.cupsColorOrder != CUPS_ORDER_CHUNKED || h.cupsNumColors != 1 ||
            (h.cupsBitsPerPixel != 1 && h.cupsBitsPerPixel != 8) ||
            h.cupsBitsPerColor != h.cupsBitsPerPixel ||
            (h.cupsColorSpace != CUPS_CSPACE_W && h.cupsColorSpace != CUPS_CSPACE_SW &&
             h.cupsColorSpace != CUPS_CSPACE_K) ||
            h.cupsBytesPerLine < (h.cupsWidth * h.cupsBitsPerPixel + 7) / 8 ||
            h.cupsBytesPerLine > 4096 || h.NumCopies > 999) {
            fputs("ERROR: Unsupported raster: use 203 dpi grayscale, width <= 4in, height <= 13in.\n", stderr);
            goto done;
        }
        unsigned stride = (h.cupsWidth + 7) / 8;
        size_t size = (size_t)stride * h.cupsHeight;
        row = malloc(h.cupsBytesPerLine);
        bitmap = malloc(size);
        if (!row || !bitmap) { fputs("ERROR: Out of memory.\n", stderr); goto done; }
        /* TSPL BITMAP uses 0 for a printed dot, 1 for white (MSB first).
           Initialize unused bits at the right edge to white. */
        memset(bitmap, 0xff, size);
        static const unsigned bayer[4][4] = {
            {0,8,2,10}, {12,4,14,6}, {3,11,1,9}, {15,7,13,5}
        };
        for (unsigned y = 0; y < h.cupsHeight; ++y) {
            if (cancelled) goto done;
            if (cupsRasterReadPixels(raster, row, h.cupsBytesPerLine) != h.cupsBytesPerLine) {
                fputs("ERROR: Truncated raster page; page was not sent.\n", stderr); goto done;
            }
            for (unsigned x = 0; x < h.cupsWidth; ++x) {
                unsigned gray = h.cupsBitsPerPixel == 8 ? row[x] :
                    ((row[x / 8] & (0x80u >> (x % 8))) ? 255u : 0u);
                if (h.cupsColorSpace == CUPS_CSPACE_K) gray = 255 - gray;
                unsigned cutoff = !strcmp(mode, "Ordered") ? bayer[y % 4][x % 4] * 16 + 8 : (unsigned)threshold;
                if (gray < cutoff) bitmap[(size_t)y * stride + x / 8] &= (unsigned char)~(0x80u >> (x % 8));
            }
        }
        if (cancelled) goto done;
        /* Buffer a complete, validated page before writing any command. CUPS
           expands collated copies with cupsManualCopies; honor raster NumCopies
           only, never multiply it by argv[4]. */
        unsigned copies = h.NumCopies ? h.NumCopies : 1;
        printf("SIZE %.3f mm,%.3f mm\r\nGAP %d mm,0 mm\r\n"
               "DIRECTION %d\r\nREFERENCE 0,0\r\nDENSITY %d\r\nSPEED %d\r\n"
               "CLS\r\nBITMAP 0,0,%u,%u,0,",
               h.cupsWidth * 25.4 / 203, h.cupsHeight * 25.4 / 203,
               !strcmp(media, "Continuous") ? 0 : gap, direction, density, speed, stride, h.cupsHeight);
        if (ferror(stdout) || fwrite(bitmap, 1, size, stdout) != size ||
            printf("\r\nPRINT 1,%u\r\n", copies) < 0 || fflush(stdout)) {
            fputs("ERROR: Cannot write printer data.\n", stderr); goto done;
        }
        ++pages;
        fprintf(stderr, "PAGE: %u %u\n", pages, copies);
        free(row); row = NULL;
        free(bitmap); bitmap = NULL;
    }
    if (cancelled) goto done;
    if (!pages) { fputs("ERROR: No raster pages found.\n", stderr); goto done; }
    if (cupsRasterErrorString() && *cupsRasterErrorString()) {
        fprintf(stderr, "ERROR: Raster read failed: %s\n", cupsRasterErrorString()); goto done;
    }
    result = 0;
done:
    free(row); free(bitmap);
    if (raster) cupsRasterClose(raster);
    if (fd != STDIN_FILENO && fd >= 0) close(fd);
    if (ppd) ppdClose(ppd);
    cupsFreeOptions(count, options);
    return cancelled ? 0 : result;
}
