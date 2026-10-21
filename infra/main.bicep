// Sliding Doors: one Azure Container App (API + web player + baked exports) for `azd up`.
targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment (resource name token and azd-env-name tag).')
param environmentName string

@description('Region of every resource.')
param location string = 'swedencentral'

@description('Resource group that holds everything; `azd down` deletes it.')
param resourceGroupName string = 'rg-slidingdoors'

@description('Set by azd once the web service is deployed: keeps its image on re-provision.')
param webExists bool = false

@minValue(0)
@maxValue(1)
@description('0 = scale to zero when idle (no cost, ~10 s cold start); 1 = always warm (for recording the demo).')
param minReplicas int = 0

var tags = { 'azd-env-name': environmentName }
var token = toLower(uniqueString(subscription().id, environmentName, location))

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    token: token
    webExists: webExists
    minReplicas: minReplicas
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output SERVICE_WEB_NAME string = resources.outputs.webName
output SERVICE_WEB_URI string = resources.outputs.webUri
output APPLICATIONINSIGHTS_NAME string = resources.outputs.appInsightsName
