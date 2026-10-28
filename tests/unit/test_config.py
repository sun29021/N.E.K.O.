import tomllib
import unittest

from tests.helpers import make_settings, temp_dir

from neko.configuration.settings import dump_overrides, load_settings, save_user_overrides, settings_from_dict
from neko.core.errors import ConfigError


class ConfigTests(unittest.TestCase):
    def test_defaults_load_and_are_safe(self):
        s = make_settings(temp_dir())
        self.assertFalse(s.privacy.allow_network)
        self.assertFalse(s.privacy.allow_cloud_models)
        self.assertFalse(s.models.allow_model_downloads)
        self.assertFalse(s.voice.wakeword_enabled)
        self.assertFalse(s.tools.computer_control_enabled)
        self.assertFalse(s.remote.enabled)
        self.assertEqual(s.models.ollama_url, "http://127.0.0.1:11434")

    def test_data_dir_is_outside_repo(self):
        tmp = temp_dir()
        s = make_settings(tmp)
        self.assertTrue(str(s.db_path).startswith(str(tmp)))

    def test_unknown_key_rejected(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"app": {"no_such_key": 1}})

    def test_wrong_type_rejected(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"privacy": {"allow_network": "yes"}})

    def test_public_ollama_url_rejected(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"models": {"ollama_url": "http://8.8.8.8:11434"}})

    def test_remote_endpoint_must_be_private_https(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"remote": {"enabled": True, "endpoints": [{"name": "x", "url": "http://192.168.1.5:11434"}]}})
        with self.assertRaises(ConfigError):
            settings_from_dict({"remote": {"enabled": True, "endpoints": [{"name": "x", "url": "https://example.com"}]}})
        s = settings_from_dict({"remote": {"enabled": True, "endpoints": [{"name": "d", "url": "https://192.168.1.5:11443"}]}})
        self.assertEqual(s.remote.endpoints[0].name, "d")

    def test_version_mismatch(self):
        with self.assertRaises(ConfigError):
            settings_from_dict({"config_version": 99})

    def test_dump_and_save_roundtrip(self):
        tmp = temp_dir()
        text = dump_overrides({"app": {"user_name": 'Sun "S"'}, "tools": {"allowed_roots": ["D:\\Notes"],
                                                                          "allowed_apps": {"paint": "mspaint.exe"}}})
        data = tomllib.loads(text)
        self.assertEqual(data["app"]["user_name"], 'Sun "S"')
        self.assertEqual(data["tools"]["allowed_apps"]["paint"], "mspaint.exe")
        path = save_user_overrides({"app": {"verbosity": "brief"}}, tmp / "config.toml")
        s = load_settings(path, extra={"app": {"data_dir": str(tmp)}})
        self.assertEqual(s.app.verbosity, "brief")

    def test_config_with_byte_order_mark_loads(self):
        tmp = temp_dir()
        p = tmp / "config.toml"
        p.write_bytes(b"\xef\xbb\xbfconfig_version = 1\n[app]\nverbosity = \"brief\"\n")
        s = load_settings(p, extra={"app": {"data_dir": str(tmp)}})
        self.assertEqual(s.app.verbosity, "brief")

    def test_defaults_file_has_no_bom(self):
        from neko.configuration.settings import _DEFAULTS_PATH

        self.assertFalse(_DEFAULTS_PATH.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_save_rejects_invalid(self):
        tmp = temp_dir()
        with self.assertRaises(ConfigError):
            save_user_overrides({"app": {"verbosity": "chatty"}}, tmp / "config.toml")
        self.assertFalse((tmp / "config.toml").exists())


if __name__ == "__main__":
    unittest.main()
