# SPDX-License-Identifier: MIT
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
FILTER = ROOT / 'build/rastertoctp800bd'
PPD = ROOT / 'ppd/ctp800bd.ppd'


def fixture(width=9, height=2, bits=8, color=0, dpi=203, copies=1, pages=1, compressed=0):
    return subprocess.check_output([str(ROOT / 'build/mkraster'),
        *map(str, (width, height, bits, color, dpi, copies, pages, compressed))])


def convert(data, options='', ppd=PPD):
    return subprocess.run([str(FILTER), '1', 'tester', 'Test', '1', options],
        input=data, capture_output=True, env={**os.environ, 'PPD': str(ppd)}, timeout=10)


def bitmap(output, width=9, height=2):
    marker = f'BITMAP 0,0,{(width + 7) // 8},{height},0,'.encode()
    return output.split(marker, 1)[1][:((width + 7) // 8) * height]


class DriverTests(unittest.TestCase):
    def test_pixel_polarity_colorspaces_depths_and_compression(self):
        for bits in (1, 8):
            for color in (0, 3, 18):  # W, K, SW
                for compressed in (0, 1):
                    with self.subTest(bits=bits, color=color, compressed=compressed):
                        p = convert(fixture(bits=bits, color=color, compressed=compressed))
                        self.assertEqual(p.returncode, 0, p.stderr)
                        # Black first dot is zero; seven pad bits remain white.
                        self.assertEqual(bitmap(p.stdout), b'\x55\x7f' * 2)
                        self.assertTrue(p.stdout.endswith(b'\r\nPRINT 1,1\r\n'))

    def test_multiple_pages_and_header_copies(self):
        p = convert(fixture(copies=2, pages=3))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.count(b'PRINT 1,2'), 3)
        self.assertIn(b'PAGE: 3 2', p.stderr)

    def test_ppd_defaults_and_job_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppd = Path(tmp) / 'test.ppd'
            ppd.write_text(PPD.read_text().replace('*DefaultDarkness: 8', '*DefaultDarkness: 12'))
            self.assertIn(b'DENSITY 12', convert(fixture(), ppd=ppd).stdout)
            p = convert(fixture(), 'Darkness=4 LabelGap=2 PrintSpeed=2 Direction=1', ppd)
            self.assertEqual(p.returncode, 0, p.stderr)
            for value in (b'DENSITY 4', b'GAP 2 mm,0 mm', b'SPEED 2', b'DIRECTION 1'):
                self.assertIn(value, p.stdout)

    def test_continuous_media(self):
        self.assertIn(b'GAP 0 mm,0 mm', convert(fixture(), 'MediaType=Continuous').stdout)

    def test_ordered_dither_preserves_black_and_white(self):
        p = convert(fixture(), 'Dither=Ordered')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(bitmap(p.stdout), b'\x55\x7f' * 2)

    def test_unsupported_raster_is_rejected_before_output(self):
        for kwargs in ({'width': 813}, {'height': 2640}, {'dpi': 300}, {'color': 1}, {'copies': 1000}):
            with self.subTest(kwargs=kwargs):
                p = convert(fixture(**kwargs))
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, b'')

    def test_truncated_and_invalid_input_cannot_print(self):
        for data in (b'', b'not raster', fixture()[:-1], fixture()[:100]):
            with self.subTest(length=len(data)):
                p = convert(data)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, b'')

    def test_invalid_and_injected_options(self):
        for option in ('Darkness=16', 'PrintSpeed=0', 'LabelGap=-1', 'Threshold=0',
                       'Direction=2', 'Dither=nope', 'MediaType=nope', 'Darkness="8\r\nPRINT 9,9"'):
            with self.subTest(option=option):
                p = convert(fixture(), option)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(p.stdout, b'')

    def test_output_failure(self):
        with open('/dev/full', 'wb') as full:
            p = subprocess.run([str(FILTER), '1', 'tester', 'Test', '1', ''],
                input=fixture(), stdout=full, stderr=subprocess.PIPE, timeout=10)
        self.assertNotEqual(p.returncode, 0)

    def test_full_size_label(self):
        p = convert(fixture(width=812, height=1218, compressed=1))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(b'SIZE 101.600 mm,152.400 mm', p.stdout)
        self.assertEqual(len(bitmap(p.stdout, 812, 1218)), 102 * 1218)

    def test_file_input(self):
        with tempfile.NamedTemporaryFile() as file:
            file.write(fixture()); file.flush()
            p = subprocess.run([str(FILTER), '1', 'tester', 'Test', '1', '', file.name], capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(bitmap(p.stdout), b'\x55\x7f' * 2)


class IntegrationTests(unittest.TestCase):
    def test_pdf_cups_raster_filter_and_copy_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf = str(Path(tmp) / 'label.pdf')
            subprocess.run(['gs', '-q', '-dSAFER', '-dBATCH', '-dNOPAUSE', '-sDEVICE=pdfwrite',
                '-sOutputFile=' + pdf, str(ROOT / 'examples/calibration.ps')], check=True, timeout=20)
            for copies in (1, 2):
                raster = subprocess.run(['cupsfilter', '-p', str(PPD), '-i', 'application/pdf',
                    '-m', 'application/vnd.cups-raster', '-n', str(copies), '-o', 'Collate=true', pdf],
                    capture_output=True, timeout=30)
                self.assertEqual(raster.returncode, 0, raster.stderr.decode())
                p = convert(raster.stdout)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertEqual(p.stdout.count(b'PRINT 1,1'), copies)
                self.assertIn(b'BITMAP 0,0,102,1218,0,', p.stdout)

    def test_real_cups_socket_backend(self):
        payload = convert(fixture()).stdout
        received = bytearray()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen(1); listener.settimeout(10)
            port = listener.getsockname()[1]
            def receive():
                conn, _ = listener.accept()
                with conn:
                    conn.settimeout(10)
                    while chunk := conn.recv(65536):
                        received.extend(chunk)
            thread = threading.Thread(target=receive, daemon=True)
            thread.start()
            # CUPS supplies back/side-channel descriptors 3/4. Standalone
            # backend execution must reserve them too, or select() sees EBADF.
            launcher = ('import os,sys; fd=os.open(os.devnull,os.O_RDWR); '
                        'os.dup2(fd,3); os.dup2(fd,4); '
                        'os.set_inheritable(3,True); os.set_inheritable(4,True); '
                        'os.execv(sys.argv[1],sys.argv[1:])')
            p = subprocess.run([sys.executable, '-c', launcher, '/usr/lib/cups/backend/socket', '1', 'tester', 'Test', '1', ''],
                input=payload, capture_output=True, timeout=15,
                env={**os.environ, 'DEVICE_URI': f'socket://127.0.0.1:{port}/?waiteof=false&snmp=false'})
            thread.join(timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertFalse(thread.is_alive())
        self.assertEqual(received, payload)


loader = importlib.machinery.SourceFileLoader('ctp800bd_cli', str(ROOT / 'scripts/ctp800bd'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


class SetupTests(unittest.TestCase):
    def test_names_and_hosts(self):
        self.assertEqual(cli.validate_name('CTP800BD-USB'), 'CTP800BD-USB')
        for value in ('-queue', 'bad/queue', 'x;reboot', 'a b'):
            with self.assertRaises(Exception): cli.validate_name(value)
        suffix = '/?waiteof=false&snmp=false&contimeout=15'
        self.assertEqual(cli.socket_uri('printer.local', 9100), 'socket://printer.local:9100' + suffix)
        self.assertEqual(cli.socket_uri('::1', 9100), 'socket://[::1]:9100' + suffix)
        for host, port in (('host/path', 9100), ('user@host', 9100), ('host', 65536)):
            with self.assertRaises(ValueError): cli.socket_uri(host, port)

    def test_sharing_commands_are_local_subnet_only(self):
        with patch.object(cli, 'existing', return_value=True), patch.object(cli, 'run') as run:
            self.assertEqual(cli.main(['share']), 0)
            self.assertEqual([c.args[0] for c in run.call_args_list], [
                ['cupsctl', '--share-printers'],
                ['lpadmin', '-p', 'CTP800BD', '-o', 'printer-is-shared=true']])

    def test_existing_queue_is_never_overwritten(self):
        with patch.object(cli, 'existing', return_value=True), patch.object(cli, 'run') as run:
            self.assertEqual(cli.main(['network', '--host', 'printer.local']), 1)
            run.assert_not_called()

    def test_usb_uri_must_be_discovered(self):
        with patch.object(cli, 'usb_uris', return_value=['usb://YXWL/CTP800BD?serial=test']), patch.object(cli, 'configure') as configure:
            self.assertEqual(cli.main(['usb', '--uri', 'usb://Unrelated/Printer']), 1)
            configure.assert_not_called()


if __name__ == '__main__':
    unittest.main()
