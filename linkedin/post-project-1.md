Before a 250-person company moves a single file to Azure, this has to exist.

I'm simulating a full cloud migration for a fictional Slovak manufacturer: Danubia Components, 250 employees, an out-of-support SQL Server, 10,000 files on a shared drive, and a board that wants Azure within 18 months.

Project 1 of 10 is done. Nothing has been migrated yet, and that's the point.

🔍 Assessment first
I built the "old server room" on my laptop (SQL Server in Docker, 40,000 ERP rows, 10,226 files, 518,000 machine readings) and wrote a Python assessment that scans it the way a consultant would.
It found:
• plain-text admin passwords in an IT notes file (CRITICAL)
• an HR export with birth numbers and IBANs in a public folder
• salary and bank-account columns with no masking
• 55% of the files untouched for 2+ years, ready for cheaper storage

🛡️ Then the landing zone, all in Bicep
• EU regions only, enforced by Azure Policy with Deny (GDPR)
• every resource must carry a cost-centre tag
• a €3/month budget with alerts before the money is spent
• Key Vault in RBAC mode, every secret read logged in Log Analytics

🔐 Deployments without a single stored secret
GitHub Actions signs in to Azure with OpenID Connect: short-lived tokens, trusted only for one repo and branch.
Something I learned the hard way: GitHub now puts immutable owner and repo IDs into the token subject. My first trust rule used the old name-only format and Azure rejected it. That change means a renamed or re-created repo can't impersonate yours.

💶 Cost of Project 1: €0.

Next: 250 user accounts with MFA and least-privilege roles, created from Python.

Repo: https://github.com/arnienemeth/danubia-azure-migration

#Azure #CloudMigration #Bicep #Python #GitHubActions #FinOps #GDPR #CloudSecurity
