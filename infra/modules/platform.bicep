// Shared platform services in rg-danubia-platform: logging and secrets.
param location string
param env string
param regionCode string
param tags object

// Log Analytics: central place for logs and audit trails.
// The daily cap makes it impossible for logging to blow the budget.
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-danubia-${env}-${regionCode}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: json('0.1') }
  }
}

// Key Vault: the only place secrets live. RBAC mode = access is granted with Entra ID roles,
// the same way as every other Azure resource (no separate vault access policies).
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-dnb-${env}-${take(uniqueString(resourceGroup().id), 8)}' // globally unique, max 24 chars
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7 // demo: short, so it can be torn down. Production: 90 + purge protection
    publicNetworkAccess: 'Enabled' // demo: no private endpoint (they cost ~EUR 7/month). Access still needs Entra ID + RBAC
  }
}

// Every read or change of a secret is written to Log Analytics
resource keyVaultAudit 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'kv-audit-to-log-analytics'
  scope: keyVault
  properties: {
    workspaceId: logAnalytics.id
    logs: [{ categoryGroup: 'audit', enabled: true }]
  }
}

output logAnalyticsId string = logAnalytics.id
output logAnalyticsName string = logAnalytics.name
output keyVaultName string = keyVault.name
