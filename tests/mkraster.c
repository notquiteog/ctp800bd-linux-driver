/* SPDX-License-Identifier: MIT - synthetic CUPS raster fixtures. */
#include <cups/raster.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 9) return 2;
    cups_page_header2_t h = {0};
    h.cupsWidth = (unsigned)atoi(argv[1]);
    h.cupsHeight = (unsigned)atoi(argv[2]);
    h.cupsBitsPerColor = h.cupsBitsPerPixel = (unsigned)atoi(argv[3]);
    h.cupsColorSpace = (cups_cspace_t)atoi(argv[4]);
    h.cupsNumColors = 1;
    h.cupsColorOrder = CUPS_ORDER_CHUNKED;
    h.cupsBytesPerLine = (h.cupsWidth * h.cupsBitsPerPixel + 7) / 8;
    h.HWResolution[0] = h.HWResolution[1] = (unsigned)atoi(argv[5]);
    h.NumCopies = (unsigned)atoi(argv[6]);
    unsigned pages = (unsigned)atoi(argv[7]);
    int compressed = atoi(argv[8]);
    if (h.cupsBytesPerLine > 65536) return 2;
    unsigned char *row = malloc(h.cupsBytesPerLine);
    if (!row) return 2;
    cups_raster_t *r = cupsRasterOpen(STDOUT_FILENO, compressed ? CUPS_RASTER_WRITE_COMPRESSED : CUPS_RASTER_WRITE);
    if (!r) { free(row); return 2; }
    for (unsigned p = 0; p < pages; ++p) {
        if (!cupsRasterWriteHeader2(r, &h)) return 2;
        for (unsigned y = 0; y < h.cupsHeight; ++y) {
            /* Alternating dots: black, white, black, white... */
            if (h.cupsBitsPerPixel == 1)
                memset(row, h.cupsColorSpace == CUPS_CSPACE_K ? 0xaa : 0x55, h.cupsBytesPerLine);
            else
                for (unsigned x = 0; x < h.cupsWidth; ++x)
                    row[x] = ((x % 2) ^ (h.cupsColorSpace == CUPS_CSPACE_K)) ? 255 : 0;
            if (cupsRasterWritePixels(r, row, h.cupsBytesPerLine) != h.cupsBytesPerLine) return 2;
        }
    }
    cupsRasterClose(r);
    free(row);
    return 0;
}
