import _isolation  # noqa: F401  Debe ir antes que el backend.
import sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/backend"))
from database_config import load_environment, connection_options


class ConfigTests(unittest.TestCase):
    def test_environment_precedence_and_no_expansion(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text(
                'SUPABASE_DB_URL="postgresql://user:p$word@host:5432/db"\nSUPABASE_SSLROOTCERT=local.crt\nPATH=untrusted\n'
            )
            env = {"SUPABASE_SSLROOTCERT": "deployment.crt"}
            load_environment(path, env)
            self.assertEqual(env["SUPABASE_SSLROOTCERT"], "deployment.crt")
            self.assertEqual(env["SUPABASE_DB_URL"], "postgresql://user:p$word@host:5432/db")
            self.assertNotIn("PATH", env)

    def test_invalid_url_error_does_not_include_secret(self):
        with self.assertRaises(ValueError) as error:
            connection_options({"SUPABASE_DB_URL": "postgresql://user:private-value-host:5432/db"})
        self.assertNotIn("private-value", str(error.exception))

    def test_tls_cannot_be_disabled_by_dsn(self):
        _, options = connection_options(
            {"SUPABASE_DB_URL": "postgresql://user:pass@host:5432/db?sslmode=disable"}
        )
        self.assertEqual(options["sslmode"], "verify-full")
        self.assertEqual(options["keepalives"], 1)
        self.assertEqual(options["keepalives_idle"], 30)

    def test_missing_certificate_fails_before_connecting(self):
        with self.assertRaises(ValueError):
            connection_options(
                {
                    "SUPABASE_DB_URL": "postgresql://user:pass@host:5432/db",
                    "SUPABASE_SSLROOTCERT": "missing-certificate-file",
                }
            )


if __name__ == "__main__":
    unittest.main()
