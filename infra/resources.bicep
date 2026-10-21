// Everything inside rg-slidingdoors: Log Analytics + Application Insights, Container Registry (Basic),
// a consumption Container Apps environment and ONE container app (scale 0-1) pulling with a managed identity.
param location string
param tags object
param token string
param webExists bool
param minReplicas int

var port = 8000 // = PORT in backend/Dockerfile
var webName = 'ca-web-${token}'
var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest' // until the first `azd deploy`
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${token}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: 1 } // hard cap on ingestion cost
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${token}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'cr${token}'
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-web-${token}'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${token}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

module existingWeb 'modules/fetch-image.bicep' = {
  name: 'fetch-web-image'
  params: {
    exists: webExists
    name: webName
  }
}

// Probes only for our image: the placeholder listens on 80, not on /api/health:8000.
var probes = [
  {
    type: 'Startup'
    httpGet: { path: '/api/health', port: port }
    periodSeconds: 3
    failureThreshold: 20
  }
  {
    type: 'Readiness'
    httpGet: { path: '/api/health', port: port }
    periodSeconds: 10
  }
  {
    type: 'Liveness'
    httpGet: { path: '/api/health', port: port }
    periodSeconds: 30
  }
]

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: webName
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identity.id}': {} }
  }
  dependsOn: [acrPull]
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: port
        transport: 'auto' // HTTP/1.1 + WebSocket (/api/matches/{id}/live)
        allowInsecure: false
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identity.id
        }
      ]
      secrets: [
        {
          name: 'appinsights-connection-string'
          value: appInsights.properties.ConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webExists ? existingWeb.outputs.containers[0].image : placeholderImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'PORT', value: string(port) }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection-string' }
            { name: 'OTEL_SERVICE_NAME', value: 'sliding-doors-api' }
          ]
          probes: webExists ? probes : []
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 1
      }
    }
  }
}

output registryLoginServer string = registry.properties.loginServer
output registryName string = registry.name
output webName string = web.name
output webUri string = 'https://${web.properties.configuration.ingress.fqdn}'
output appInsightsName string = appInsights.name
