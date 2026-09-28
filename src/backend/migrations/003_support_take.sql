-- Soporte puede ver las solicitudes abiertas sin asignar y tomarlas (requests.take).
-- Idempotente. Ejecutar sobre el esquema de VitaDev, por ejemplo: SET search_path TO vitadev;
BEGIN;
INSERT INTO permissions(code) VALUES('requests.take') ON CONFLICT DO NOTHING;
INSERT INTO profile_permissions(profile_code,permission_code) VALUES('SUPPORT','requests.take') ON CONFLICT DO NOTHING;
INSERT INTO schema_migrations(version) VALUES(3) ON CONFLICT DO NOTHING;
COMMIT;
