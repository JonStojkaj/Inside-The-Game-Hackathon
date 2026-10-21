// Image of an already deployed container app (azd pattern), so `azd provision` does not reset it
// to the placeholder. Separate module: a template cannot read the app it is deploying.
param exists bool
param name string

resource app 'Microsoft.App/containerApps@2024-03-01' existing = if (exists) {
  name: name
}

output containers array = exists ? app.properties.template.containers : []
