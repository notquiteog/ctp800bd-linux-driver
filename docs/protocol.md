# Protocol and implementation notes

## Identification

The development device enumerated as `5958:0130`, manufacturer `YXWL`, product
`CTP800BD`. It exposes USB printer class 7, subclass 1, protocol 2, with bulk OUT
endpoint `0x02` and bulk IN endpoint `0x81`. CUPS's standard USB backend discovers
it automatically. The IEEE-1284 device ID leaves the command-language field
empty, so USB discovery alone does not prove TSPL compatibility.

The manufacturer's publicly downloadable CTP800BD Mac driver 1.0.9 provides
additional protocol evidence: its PPD selects 203 DPI grayscale, and its filter
contains TSPL `SIZE`, `GAP`, `DENSITY`, `SPEED`, `BITMAP`, and `PRINT` command
templates. The installer was inspected as data and was not executed. This
repository's source and PPD are independently written; no vendor files are
included. Physical results remain important because product revisions can vary.

## Page conversion

The filter accepts CUPS raster via libcups, including its compressed format.
It validates the page dimensions, 203 DPI resolution, chunked single-channel
layout, stride, copy count, and 1-bit or 8-bit W/SW/K color space. It converts to
a monochrome MSB-first bitmap with **0 = printed dot, 1 = white**, including white
padding in the last byte. This follows TSC's BITMAP diagram on printed page 38
of the 2009 programming manual.

Each complete page is buffered before emitting its commands:

```text
SIZE <width-mm> mm,<height-mm> mm
GAP <gap-mm> mm,0 mm
DIRECTION <0-or-1>
REFERENCE 0,0
DENSITY <0-to-15>
SPEED <1-to-5>
CLS
BITMAP 0,0,<row-bytes>,<height-dots>,0,<binary pixels>
PRINT 1,<raster-header-copies>
```

Lines end with CRLF; pixel data is binary, not hexadecimal text. Mode 0 means
overwrite. The driver does not send a cut, factory reset, firmware update,
automatic media calibration, cash-drawer command, or Bluetooth configuration.

CUPS handles collation and copy expansion with `cupsManualCopies: True`; the
filter honors raster `NumCopies` and does not multiply by the command-line copy
argument. The program expects raster produced by a CUPS rasterizer. It does not
implement document-level collation when invoked directly on an arbitrary raster
file. CUPS also handles PDF layout, USB transport, queueing, and IPP networking.

## References

- [Core Innovations CTP800BD specifications](https://www.coreinnovationsinc.com/product/ctp800bd/)
- [Manufacturer driver downloads](https://www.coreinnovationsinc.com/drivers/)
- [TSC manual download portal](https://usca.tscprinters.com/en/downloads)
- [TSC 2009 TSPL/TSPL2 manual, archived copy](https://github.com/littlecxm/tspl-manual/blob/master/docs/tspl_tspl2_programming_2009.pdf)
- [OpenPrinting CUPS Raster API](https://openprinting.github.io/cups/doc/api-raster.html)
- [CUPS filter and backend interface](https://openprinting.github.io/cups/doc/api-filter.html)
- [CUPS printer sharing](https://openprinting.github.io/cups/doc/sharing.html)
