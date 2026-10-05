-- One-time setup for the explicitly requested private GitHub deployment.
-- Run in Snowsight as ACCOUNTADMIN. No passwords, keys or billing changes.
-- Existing users are deliberately not overwritten.
USE ROLE ACCOUNTADMIN;
CREATE USER SAMVAAD_GITHUB_DEPLOYER
 TYPE=SERVICE
 WORKLOAD_IDENTITY=(
  TYPE=OIDC
  ISSUER='https://token.actions.githubusercontent.com'
  SUBJECT='repo:Cherie05/samvaad360:ref:refs/heads/main'
 )
 DEFAULT_ROLE=SAMVAAD_HACKATHON
 DEFAULT_WAREHOUSE=SAMVAAD_XS;
GRANT ROLE SAMVAAD_HACKATHON TO USER SAMVAAD_GITHUB_DEPLOYER;
