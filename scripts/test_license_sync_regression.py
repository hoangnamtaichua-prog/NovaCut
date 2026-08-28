# -*- coding: utf-8 -*-
"""Regression tests for Trial-to-Sheet registration and managed VietQR data."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import license_manager


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise license_manager.requests.HTTPError(f'HTTP {self.status_code}')

    def json(self):
        return self._payload


class LicenseSyncRegressionTests(unittest.TestCase):
    def test_payment_config_ignores_stale_appdata_bank_details(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_dir = os.path.join(temp_dir, 'app')
            os.makedirs(app_dir)
            legacy_config = os.path.join(app_dir, 'license_config.json')
            local_config = os.path.join(temp_dir, 'appdata-license_config.json')
            with open(legacy_config, 'w', encoding='utf-8') as handle:
                json.dump({
                    'bank_code': 'OLD_BANK',
                    'bank_account': '9999999999',
                    'bank_account_name': 'OLD ACCOUNT',
                    'google_apps_script_url': 'https://legacy.invalid/license',
                }, handle)
            with open(local_config, 'w', encoding='utf-8') as handle:
                json.dump({
                    'google_apps_script_url': 'https://local-override.invalid/license',
                    'client_license_token': 'local-override-token',
                }, handle)

            with patch.object(license_manager, 'ROOT_DIR', app_dir), \
                 patch.object(license_manager, 'CONFIG_FILE', local_config), \
                 patch.dict(os.environ, {
                     'NOVACUT_BANK_CODE': '',
                     'NOVACUT_BANK_ACCOUNT': '',
                     'NOVACUT_BANK_ACCOUNT_NAME': '',
                 }, clear=False):
                config = license_manager.load_app_config()

            self.assertEqual(config['bank_code'], license_manager.MANAGED_PAYMENT_CONFIG['bank_code'])
            self.assertEqual(config['bank_account'], license_manager.MANAGED_PAYMENT_CONFIG['bank_account'])
            self.assertEqual(config['bank_account_name'], license_manager.MANAGED_PAYMENT_CONFIG['bank_account_name'])
            self.assertEqual(config['google_apps_script_url'], 'https://legacy.invalid/license')
            self.assertNotEqual(config['client_license_token'], 'local-override-token')

    def test_frozen_bootstrap_supplies_cloud_connection_for_a_fresh_machine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bootstrap_config = os.path.join(temp_dir, 'license_bootstrap.json')
            legacy_config = os.path.join(temp_dir, 'license_config.json')
            with open(bootstrap_config, 'w', encoding='utf-8') as handle:
                json.dump({
                    'google_apps_script_url': 'https://example.invalid/license',
                    'client_license_token': 'bootstrap-token',
                    'api_secret_token': 'must-not-be-bundled',
                }, handle)
            with open(legacy_config, 'w', encoding='utf-8') as handle:
                json.dump({
                    'google_apps_script_url': 'https://stale-client-config.invalid/license',
                    'client_license_token': 'stale-client-token',
                    'api_secret_token': 'legacy-admin-token',
                }, handle)

            with patch.object(license_manager, 'ROOT_DIR', temp_dir), \
                 patch.object(license_manager, 'CONFIG_FILE', os.path.join(temp_dir, 'missing.json')), \
                 patch.object(license_manager, 'BOOTSTRAP_CONFIG_FILE', bootstrap_config), \
                 patch.object(license_manager.sys, 'frozen', True, create=True):
                config = license_manager.load_app_config()

            self.assertEqual(config['google_apps_script_url'], 'https://example.invalid/license')
            self.assertEqual(config['client_license_token'], 'bootstrap-token')
            self.assertNotEqual(config['api_secret_token'], 'must-not-be-bundled')
            self.assertNotEqual(config['api_secret_token'], 'legacy-admin-token')

    def test_trial_registration_posts_the_full_hwid_and_requires_success_response(self):
        trial = {
            'tier': 'trial',
            'expire_epoch': 1_800_000_000,
            'expire_str': '01/01/2027 12:00',
            'user_name': 'Khách Dùng Thử 24h',
            'phone_zalo': '',
        }
        sent_payloads = []

        def fake_post(_url, json, timeout):
            sent_payloads.append((json, timeout))
            return _Response({'success': True})

        with patch.object(license_manager, 'load_app_config', return_value={
            'google_apps_script_url': 'https://example.invalid/license',
            'client_license_token': 'test-token',
        }), patch.object(license_manager, 'get_hardware_id', return_value='AMS-1BF9-3933-68E9'), \
             patch.object(license_manager.requests, 'post', side_effect=fake_post):
            success, error = license_manager.register_trial_in_cloud(trial)

        self.assertTrue(success, error)
        self.assertEqual(sent_payloads[0][0]['hwid'], 'AMS-1BF9-3933-68E9')
        self.assertEqual(sent_payloads[0][0]['action'], 'register_trial')

    def test_trial_registration_does_not_hide_a_server_rejection(self):
        with patch.object(license_manager, 'load_app_config', return_value={
            'google_apps_script_url': 'https://example.invalid/license',
            'client_license_token': 'test-token',
        }), patch.object(license_manager, 'get_hardware_id', return_value='AMS-1BF9-3933-68E9'), \
             patch.object(license_manager.requests, 'post', return_value=_Response({'success': False, 'error': 'Unauthorized'})):
            success, error = license_manager.register_trial_in_cloud({'tier': 'trial'})

        self.assertFalse(success)
        self.assertEqual(error, 'Unauthorized')

    def test_vietqr_url_uses_the_managed_payment_destination(self):
        config = {
            **license_manager.DEFAULT_CONFIG,
            'prices': dict(license_manager.DEFAULT_CONFIG['prices']),
        }
        with patch.object(license_manager, 'load_app_config', return_value=config), \
             patch.object(license_manager, 'get_hardware_id', return_value='AMS-1BF9-3933-68E9'):
            data = license_manager.generate_vietqr_url('vip')

        self.assertEqual(data['bank_code'], license_manager.MANAGED_PAYMENT_CONFIG['bank_code'])
        self.assertEqual(data['bank_account'], license_manager.MANAGED_PAYMENT_CONFIG['bank_account'])
        self.assertIn('AMS%201BF9393368E9%20VIP', data['qr_image_url'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
