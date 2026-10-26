# Verification

Development baseline: 2026-10-26, x86-64 Pop!_OS, CUPS 2.4.16,
Core Innovations / YXWL CTP800BD USB ID `5958:0130`.

## Automated checks

`make test` covers:

- Build with warnings treated as errors; PPD validation.
- 1-bit and 8-bit grayscale, W/K/SW polarity, compressed and uncompressed raster.
- Non-byte-aligned widths with white padding; full 4 × 6 label dimensions.
- Multiple pages and copy counts; PPD defaults and job overrides.
- Continuous media and ordered rendering of black/white pixels.
- Invalid settings, command injection attempts, oversized pages, wrong DPI,
  unsupported color spaces, missing/truncated data, and output failures.
- PDF conversion through the system CUPS rasterizer, including two copies.
- Actual CUPS socket backend transmission to a loopback TCP receiver.
- Queue setup validation and local-subnet sharing commands with mocked mutations.
- Explicit Letter-to-4x6 cropping, preservation of original files, validation of
  every page before output, and rendered one-inch geometry after cropping.
- Bluetooth address validation, pairing and live SPP checks, missing backend,
  service timeout, unsupported channels, and separate-queue configuration.

## Hardware and network scope

USB enumeration and CUPS discovery were verified on the connected printer.
The driver was installed with a 4 × 6 queue and IPP sharing enabled. A calibration
PDF was submitted to that USB queue and CUPS reported the job completed. On
2026-10-26, the printer owner confirmed that the physical calibration label
printed correctly: black text on a white background, upright text, and all four
border edges visible. The one-inch measurement line has not been independently
measured.

IPP attributes were queried through the host's LAN address, DNS-SD discovery
was checked, and a temporary driverless IPP client queue was created successfully
and removed without printing. A print submitted from a separate Wi-Fi client
still requires verification. The loopback TCP test is not a physical Wi-Fi test.
No native Wi-Fi radio is implemented. Direct Bluetooth SPP support is described
below.

## Shipping PDF page-size correction

A reported small-label issue was traced to 4 x 6 artwork positioned at the top
left of Letter-sized PDF pages, with the print application requesting Letter
paper. The original USB calibration was correctly sized. The `prepare-pdf`
command now provides an explicit `letter-top-left` crop for this layout,
preserving artwork at its original scale. Two corrected 4 x 6 pages were rendered
and inspected, verified through the CUPS raster/TSPL pipeline, and submitted with
4 x 6 media and no scaling; CUPS reported completion. The printer owner confirmed
that both corrected labels printed at the proper full 4 x 6 size on 2026-10-26.

## Bluetooth

The connected printer was already paired and trusted in BlueZ, advertising as
`Label Printer-xxxx`. A live SDP Serial Port query returned RFCOMM channel 1,
and an RFCOMM connection succeeded. A separate `CTP800BD-Bluetooth` queue was
configured with the same PPD and a BlueZ `bluetooth://.../spp` device URI. The
calibration PDF was submitted to that queue at 4 x 6 size with no scaling, and
CUPS reported the job completed. On 2026-10-26, the printer owner confirmed that
the Bluetooth calibration label printed correctly at full 4 x 6 size. USB is
not a fallback for this queue.

The automated Bluetooth tests mock service discovery and queue configuration;
they do not replace the physical transport check. BLE-only variants and printing
over USB and Bluetooth simultaneously have not been validated.

This is an initial driver release; other firmware revisions, external print
servers, other CPU architectures, Windows/macOS clients, and CUPS 3 have not been
hardware-tested. Keep the printer's label dimensions and gap settings matched
to the stock when validating a new setup.
