-- Run once in Snowsight (Projects -> Worksheets -> + SQL Worksheet) as ACCOUNTADMIN.
-- Lets Claude/your Mac connect as YOU with a key pair (no password/MFA prompts).
-- The private half lives only at ~/.snowflake/<your-key>.p8 on your Mac.
-- To revoke later:  ALTER USER "<your_user_name>" UNSET RSA_PUBLIC_KEY;
-- (The username has dots, so it must be double-quoted (and quoted names are case-sensitive); IDENTIFIER(CURRENT_USER())
--  would misread the dots as database.schema.object separators.)

USE ROLE ACCOUNTADMIN;
ALTER USER "<your_user_name>" SET RSA_PUBLIC_KEY = '<contents of your .pub key, without the BEGIN/END lines>';

-- Should show RSA_PUBLIC_KEY_FP = SHA256:<fingerprint of your key>
DESC USER "<your_user_name>";
