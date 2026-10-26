# CTP800BD Linux driver

[![Build and test](https://github.com/notquiteog/ctp800bd-linux-driver/actions/workflows/test.yml/badge.svg)](https://github.com/notquiteog/ctp800bd-linux-driver/actions/workflows/test.yml)

An independent, MIT-licensed CUPS 2.x raster driver for the **Core Innovations
CTP800BD** thermal label printer, identified over USB as **YXWL CTP800BD
(`5958:0130`)**. Converts PDFs and images through CUPS to TSPL bitmap commands.
Includes USB setup, Wi-Fi/LAN sharing, tests, and a 4 × 6 inch calibration label.

The CTP800BD's documented wireless connection is **Bluetooth, not native Wi-Fi**.
Wi-Fi printing here means a computer on your network shares the USB printer
through IPP. The host must remain on and connected to the printer. Bluetooth
printing is outside this driver's scope.

```text
Local applications ── CUPS + this driver ── USB ── CTP800BD
Wi-Fi/LAN clients ── IPP ── Linux host ── CUPS + this driver ── USB ── CTP800BD
```

## Features

- 203 DPI printing, with 4 × 6 inch labels as the default.
- 100 × 150 mm, 4 × 4, 4 × 2, 3 × 2, 2 × 4, and 2 × 1 inch presets.
- Custom labels from 1–4 inches wide and 1–13 inches long.
- Darkness, speed, gap size, direction, threshold, and ordered dithering controls.
- Standard CUPS USB transport: no new kernel module or permissive USB rules.
- IPP sharing and DNS-SD discovery using CUPS and Avahi.
- Optional raw TCP transport for a **compatible external TSPL print server**.
- Page size bounds, validated options, white padding bits, and complete-page
  buffering before output so a truncated raster page does not trigger printing.

## Install on Ubuntu, Pop!_OS, or Debian

```sh
sudo apt-get update
sudo apt-get install build-essential libcups2-dev libcupsimage2-dev \
  cups cups-client cups-filters ghostscript python3 avahi-daemon usbutils
git clone https://github.com/notquiteog/ctp800bd-linux-driver.git
cd ctp800bd-linux-driver
make
make test
sudo make install
sudo systemctl enable --now cups avahi-daemon
```

Builds natively for the host architecture. Other distributions need equivalent
CUPS 2.x development headers, raster libraries, CUPS filters, Ghostscript,
Python 3.8+, and Avahi. Their packaging and paths have not been tested.
The driver uses the PPD/filter interface, which is deprecated in CUPS 2.x and
is not a CUPS 3 Printer Application.

## USB setup

Power on the printer, connect USB, and load labels:

```sh
ctp800bd detect
sudo ctp800bd usb
ctp800bd status
lp -d CTP800BD -o PageSize=w288h432 label.pdf
```

Setup creates the queue `CTP800BD`. It does not replace existing queues or change
your default printer. Use `--name CTP800BD-USB` for another name. If multiple
printers are connected, select an exact device URI from `detect`:

```sh
sudo ctp800bd usb --name CTP800BD-USB --uri 'usb://YXWL/CTP800BD?serial=0.0'
```

That URI is an example: use the value from your own device. Queue errors stop
the printer instead of automatically repeating a possibly partially printed job.
Resolve the issue, cancel an unwanted job with `cancel JOB-ID`, and use
`sudo cupsenable CTP800BD` to resume.

## Wi-Fi / network printing

On the Linux computer connected to the printer:

```sh
sudo ctp800bd share
```

This enables CUPS sharing with its standard local-subnet access policy and marks
this queue as shared. It preserves remote-administration settings. Enabling
CUPS sharing is a server-wide setting: other queues already marked shared may
also become visible. No firewall or router configuration is changed.

Clients on the same LAN or Wi-Fi should see **Core Innovations CTP800BD** in their
printer settings. On another Linux computer, add the shared queue with:

```sh
sudo lpadmin -p CTP800BD -E \
  -v ipp://PRINT-HOST.local:631/printers/CTP800BD -m everywhere
lp -d CTP800BD label.pdf
```

Replace `PRINT-HOST` with the name printed by `ctp800bd share`, or use the host's
LAN address. Clients use the host's driver and need no copy of this repository.
For Windows or macOS, add a network printer using that IPP address. These clients
have not been hardware-tested. Select the matching label size in the application.

If discovery fails, check Avahi, that both machines are on the same subnet, and
that the Wi-Fi network does not isolate clients. With a firewall enabled, allow
TCP 631 and, for discovery, UDP 5353 from the trusted local network. Do not
forward these ports from the internet.

To stop sharing just this printer:

```sh
sudo ctp800bd unshare
```

### External TCP print server

Only use this if an external print server accepts raw TSPL on a TCP port and
forwards it to the printer. A Bluetooth connection is not a TCP print server.

```sh
sudo ctp800bd network --name CTP800BD-TCP --host printer-server.local --port 9100
```

For a shared CUPS/IPP host, use `lpadmin ... -m everywhere` above instead.

## Label options

```sh
# Preserve a PDF already laid out as a 4 x 6 inch label.
lp -d CTP800BD -o PageSize=w288h432 -o print-scaling=none label.pdf

# 100 x 150 mm stock, darker output, 2 mm gap.
lp -d CTP800BD -o PageSize=w283h425 -o Darkness=10 -o LabelGap=2 label.pdf

# Custom 75 x 100 mm label.
lp -d CTP800BD -o PageSize=Custom.75x100mm label.pdf

# Show all available options.
lpoptions -p CTP800BD -l
```

| Option | Values | Default |
| --- | --- | --- |
| `Darkness` | 0–15 | 8 |
| `PrintSpeed` | 1–5 inches/second | 3 |
| `LabelGap` | 0–6 mm | 3 |
| `MediaType` | `Labels`, `Continuous` | `Labels` |
| `Direction` | `0`, `1` (180-degree rotation) | `0` |
| `Threshold` | 64, 96, 128, 160, 192, 224 in the UI | 128 |
| `Dither` | `Threshold`, `Ordered` | `Threshold` |

The filter also accepts integer thresholds 1–255 from command-line job options.
Keep threshold rendering for shipping barcodes; ordered dithering is for images.
The PDF page should match the physical label. Letter/A4 shipping documents need
to be cropped or laid out as labels before printing. Widths over 4 inches are
rejected instead of silently clipped. Black-mark stock is not implemented.

## Calibration

The included calibration label has orientation marks, a border, a one-inch
measurement line, and a fine-line pattern. Printing it consumes one 4 × 6 label.

```sh
gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=pdfwrite \
  -sOutputFile=build/calibration.pdf examples/calibration.ps
lp -d CTP800BD -o PageSize=w288h432 -o print-scaling=none build/calibration.pdf
```

Check that the background is white, all four border edges are visible, text is
upright, and the marked line measures one inch. See [verification notes](docs/verification.md)
for what has actually been tested; a completed CUPS job alone is not proof of
physical print quality.

## Troubleshooting and removal

```sh
ctp800bd detect
ctp800bd status
lpstat -W not-completed -o CTP800BD
journalctl -u cups --since '10 minutes ago'
```

- **No USB printer:** check power/cable and `lsusb -d 5958:0130`; ensure CUPS runs.
- **Filter failed:** check `/var/log/cups/error_log`, install the CUPS PDF/raster
  filters, and rebuild after changing CPU architecture.
- **Blank/incorrect labels:** match the paper size and gap to the loaded stock,
  check paper orientation, and use the printer's documented media calibration.
  Firmware variants may need protocol adjustments; include the model/USB ID and
  symptoms in an issue, without uploading shipping addresses or private labels.
- **Network client cannot connect:** keep the USB host awake, check local network
  isolation/firewall settings, and try its LAN IP instead of `.local`.

Remove the queue before removing its driver:

```sh
sudo ctp800bd unshare
sudo lpadmin -x CTP800BD
sudo make uninstall
```

Server-wide CUPS sharing remains as configured; if no shared printers are needed,
disable it separately with `sudo cupsctl --no-share-printers`.

## Development

```sh
make test
make DESTDIR="$PWD/build/stage" install
```

Tests generate CUPS raster fixtures through libcups, exercise input and output
failures, run a real PDF → CUPS raster → TSPL pipeline, verify copy counts, and
send data through the CUPS socket backend to a loopback receiver. They do not
contact a physical printer or change CUPS configuration. GitHub Actions runs the
same checks on Ubuntu 24.04.

This is original driver code, with no proprietary executables or vendor PPD
redistributed. See [protocol and source notes](docs/protocol.md). Not affiliated
with or endorsed by Core Innovations, YXWL, or TSC. Contributions and hardware
results are welcome. [MIT license](LICENSE).
