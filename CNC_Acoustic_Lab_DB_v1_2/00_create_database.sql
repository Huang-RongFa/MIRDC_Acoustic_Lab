-- CNC Acoustic Lab | FIRST connect to database `postgres` or another existing maintenance DB.
-- Execute this SQL *separately*. PostgreSQL CREATE DATABASE must not run inside BEGIN/COMMIT.
-- Requires CREATEDB privilege; does not create logins or manage passwords.
-- If the database already exists, STOP and inspect it rather than rerunning blindly.
CREATE DATABASE cnc_acoustic_lab WITH ENCODING = 'UTF8' TEMPLATE = template0;
