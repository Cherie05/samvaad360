-- Repair only the service user created for this repository in this session.
-- Immutable IDs are verified against the repository API and the login error.
USE ROLE ACCOUNTADMIN;
ALTER USER SAMVAAD_GITHUB_DEPLOYER SET WORKLOAD_IDENTITY=(
 TYPE=OIDC
 ISSUER='https://token.actions.githubusercontent.com'
 SUBJECT='repo:Cherie05@134769533/samvaad360@1405935541:ref:refs/heads/main'
);
