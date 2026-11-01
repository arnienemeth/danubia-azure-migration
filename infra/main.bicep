// =============================================================================
// Danubia Components - landing zone "lite" (Project 1)
// Deployed at SUBSCRIPTION scope: creates resource groups, guardrails, budget
// and the shared platform services every later project builds on.
// =============================================================================
targetScope = 'subscription'

@description('Azure region for all resources. Sweden Central = EU data residency.')
param location string = 'swedencentral'

@description('Environment name, used in resource names and tags.')
@allowed(['dev', 'prod'])
param env string = 'dev'

@description('E-mail address that receives budget alerts.')
param budgetEmail string

@description('Monthly budget for the WHOLE subscription, in the billing currency (EUR).')
param budgetAmount int = 3

@description('First day of the month the budget starts. Must not be in the past when first created.')
param budgetStartDate string

@description('EU regions where Danubia resources may be created.')
param allowedLocations array = ['swedencentral', 'westeurope', 'northeurope', 'germanywestcentral']

// Tags on everything: who owns it, what it costs against, which project created it
var tags = {
  company: 'danubia'
  env: env
  owner: 'it-platform'
  costCenter: 'IT-001'
  project: 'p01-landing-zone'
  managedBy: 'bicep'
}
var regionCode = 'swc'
var alertEmails = [trim(budgetEmail)] // trim: a pasted secret often carries a space or line break

// ---------------------------------------------------------------- resource groups
// One group per lifecycle: shared platform, data (SQL, storage), applications
resource rgPlatform 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-danubia-platform-${env}-${regionCode}'
  location: location
  tags: tags
}

resource rgData 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-danubia-data-${env}-${regionCode}'
  location: location
  tags: tags
}

resource rgApps 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-danubia-apps-${env}-${regionCode}'
  location: location
  tags: tags
}

// ---------------------------------------------------------------- shared platform services
module platform 'modules/platform.bicep' = {
  name: 'danubia-platform'
  scope: rgPlatform
  params: {
    location: location
    env: env
    regionCode: regionCode
    tags: tags
  }
}

// ---------------------------------------------------------------- guardrails (Azure Policy)
// Assigned per Danubia resource group, so older projects in this subscription are not affected.
module guardrailsPlatform 'modules/guardrails.bicep' = {
  name: 'danubia-guardrails-platform'
  scope: rgPlatform
  params: { allowedLocations: allowedLocations }
}

module guardrailsData 'modules/guardrails.bicep' = {
  name: 'danubia-guardrails-data'
  scope: rgData
  params: { allowedLocations: allowedLocations }
}

module guardrailsApps 'modules/guardrails.bicep' = {
  name: 'danubia-guardrails-apps'
  scope: rgApps
  params: { allowedLocations: allowedLocations }
}

// ---------------------------------------------------------------- audit trail
// Send the subscription's Activity Log (who created, changed, deleted what) to Log Analytics.
// Activity Log ingestion into Log Analytics is free.
resource activityLog 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'danubia-activity-to-log-analytics'
  properties: {
    workspaceId: platform.outputs.logAnalyticsId
    logs: [
      { category: 'Administrative', enabled: true }
      { category: 'Security', enabled: true }
      { category: 'Policy', enabled: true }
      { category: 'Alert', enabled: true }
    ]
  }
}

// ---------------------------------------------------------------- cost guardrail
resource budget 'Microsoft.Consumption/budgets@2023-05-01' = {
  name: 'budget-danubia-monthly'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStartDate }
    notifications: {
      actual50: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 50
        thresholdType: 'Actual'
        contactEmails: alertEmails
      }
      actual100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Actual'
        contactEmails: alertEmails
      }
      forecast100: {
        enabled: true
        operator: 'GreaterThanOrEqualTo'
        threshold: 100
        thresholdType: 'Forecasted'
        contactEmails: alertEmails
      }
    }
  }
}

output resourceGroups array = [rgPlatform.name, rgData.name, rgApps.name]
output keyVaultName string = platform.outputs.keyVaultName
output logAnalyticsName string = platform.outputs.logAnalyticsName
