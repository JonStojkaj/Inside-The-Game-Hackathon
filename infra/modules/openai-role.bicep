// Ask Sliding Doors: lets the container app's managed identity call the EXISTING Azure OpenAI resource
// (keyless, DefaultAzureCredential with AZURE_CLIENT_ID). Deployed into the OpenAI resource's own resource group,
// which may differ from rg-slidingdoors; requires Owner / User Access Administrator there.
targetScope = 'resourceGroup'

param openAiName string
param principalId string

var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd' // Cognitive Services OpenAI User

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiName
}

resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, principalId, openAiUserRoleId)
  scope: openAi
  properties: {
    principalId: principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
  }
}
