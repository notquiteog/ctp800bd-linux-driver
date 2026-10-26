# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_driver import cli


class BluetoothTests(unittest.TestCase):
    address = 'AA:BB:CC:DD:EE:FF'
    uri = 'bluetooth://AABBCCDDEEFF/spp'

    def setUp(self):
        for target, kwargs in (('shutil.which', {'return_value': '/usr/bin/tool'}),
                               ('os.access', {'return_value': True})):
            patcher = patch.object(cli.shutil if target.startswith('shutil') else cli.os,
                                   target.split('.')[1], **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)

    def replies(self, paired=True, service='  "RFCOMM" (0x0003)\n    Channel: 1\n'):
        return [subprocess.CompletedProcess([], 0, f'  Paired: {"yes" if paired else "no"}\n'),
                subprocess.CompletedProcess([], 0, service)]

    def test_address_validation_and_canonical_uri(self):
        self.assertEqual(cli.bluetooth_address(self.address.lower()), self.address)
        for value in ('', '-invalid', 'AA:BB:CC:DD:EE', self.address + '/spp', self.address + ';reboot'):
            with self.assertRaises(argparse.ArgumentTypeError):
                cli.bluetooth_address(value)
        with patch.object(cli, 'run', side_effect=self.replies()) as run:
            self.assertEqual(cli.bluetooth_uri(self.address.lower()), self.uri)
            self.assertEqual(run.call_args_list[0].args[0], ['bluetoothctl', 'info', self.address])
            self.assertEqual(run.call_args_list[1].args[0], ['sdptool', 'search', '--bdaddr', self.address, 'SP'])
            self.assertTrue(all(c.kwargs['timeout'] == 15 for c in run.call_args_list))

    def test_unpaired_device_is_not_configured(self):
        with patch.object(cli, 'run', side_effect=self.replies(paired=False)) as run:
            with self.assertRaisesRegex(ValueError, 'Pair the printer first'):
                cli.bluetooth_uri(self.address)
            self.assertEqual(run.call_count, 1)

    def test_ble_only_and_invalid_serial_channels_are_rejected(self):
        for service in ('UUID: 0xfee7\n', 'Channel: 0\n', 'Channel: 31\n'):
            with patch.object(cli, 'run', side_effect=self.replies(service=service)):
                with self.assertRaisesRegex(ValueError, 'No Bluetooth Serial Port'):
                    cli.bluetooth_uri(self.address)

    def test_missing_backend_explains_dependency(self):
        with patch.object(cli.os, 'access', return_value=False), patch.object(cli, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'bluez-cups'):
                cli.bluetooth_uri(self.address)
            run.assert_not_called()

    def test_service_timeout_does_not_create_queue(self):
        with patch.object(cli, 'run', side_effect=subprocess.TimeoutExpired('sdptool', 15)), \
                patch.object(cli, 'configure') as configure:
            self.assertEqual(cli.main(['bluetooth', '--address', self.address]), 1)
            configure.assert_not_called()

    def test_bluetooth_queue_uses_same_filter_and_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            ppd = Path(tmp) / 'driver.ppd'
            ppd.touch()
            with patch.object(cli, 'bluetooth_uri', return_value=self.uri), \
                    patch.object(cli, 'existing', return_value=False), \
                    patch.object(cli, 'PPD', ppd), patch.object(cli, 'run') as run:
                self.assertEqual(cli.main(['bluetooth', '--address', self.address]), 0)
                args = run.call_args.args[0]
                self.assertEqual(args[args.index('-p') + 1], 'CTP800BD-Bluetooth')
                self.assertEqual(args[args.index('-v') + 1], self.uri)
                self.assertEqual(args[args.index('-P') + 1], str(ppd))
                self.assertEqual(args[args.index('-D') + 1], 'Core Innovations CTP800BD (Bluetooth)')
                self.assertIn('PageSize=w288h432', args)
                self.assertIn('printer-error-policy=stop-printer', args)

    def test_existing_queue_is_not_overwritten(self):
        with patch.object(cli, 'bluetooth_uri', return_value=self.uri), \
                patch.object(cli, 'existing', return_value=True), patch.object(cli, 'run') as run:
            self.assertEqual(cli.main(['bluetooth', '--address', self.address]), 1)
            run.assert_not_called()
