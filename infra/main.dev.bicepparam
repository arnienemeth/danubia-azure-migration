using './main.bicep'

param env = 'dev'
param location = 'swedencentral'
param budgetAmount = 3
param budgetStartDate = '2026-11-01'

// Read from an environment variable, so the e-mail address is never committed to the public repo.
// Locally it comes from .env (scripts\load-env.ps1); in GitHub Actions from a repository variable.
param budgetEmail = readEnvironmentVariable('BUDGET_EMAIL')
