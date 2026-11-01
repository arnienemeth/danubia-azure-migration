// Azure Policy guardrails for one resource group. Uses Microsoft's built-in policy definitions.
param allowedLocations array

// Built-in "Allowed locations": denies any resource outside the listed regions.
// (It ignores 'global' resources by design.)
resource euOnly 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'danubia-eu-only'
  properties: {
    displayName: 'Danubia: resources only in EU regions'
    description: 'GDPR data residency: Danubia data and services stay in the EU.'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', 'e56962a6-4747-49cd-b67b-bf8b01975c4c')
    parameters: {
      listOfAllowedLocations: { value: allowedLocations }
    }
    nonComplianceMessages: [
      { message: 'Danubia policy: only EU regions are allowed (GDPR data residency).' }
    ]
  }
}

// Built-in "Require a tag on resources": every resource must say which cost centre pays for it.
resource requireCostCenter 'Microsoft.Authorization/policyAssignments@2023-04-01' = {
  name: 'danubia-require-costcenter'
  properties: {
    displayName: 'Danubia: resources need a costCenter tag'
    description: 'FinOps: every resource can be charged back to a cost centre.'
    policyDefinitionId: tenantResourceId('Microsoft.Authorization/policyDefinitions', '871b6d14-10aa-478d-b590-94f262ecfa99')
    parameters: {
      tagName: { value: 'costCenter' }
    }
    nonComplianceMessages: [
      { message: 'Danubia policy: add a costCenter tag (for example IT-001).' }
    ]
  }
}
