{{- define "kube-oidc-issuer-reflector.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "kube-oidc-issuer-reflector.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "kube-oidc-issuer-reflector.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
app.kubernetes.io/name: {{ include "kube-oidc-issuer-reflector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "kube-oidc-issuer-reflector.imageTag" -}}
{{- if eq .Chart.AppVersion "0.0.0" }}
{{- required "image.tag must be set when using the unpackaged development chart" .Values.image.tag }}
{{- else }}
{{- default .Chart.AppVersion .Values.image.tag }}
{{- end }}
{{- end }}

{{- define "kube-oidc-issuer-reflector.selectorLabels" -}}
app.kubernetes.io/name: {{ include "kube-oidc-issuer-reflector.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "kube-oidc-issuer-reflector.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "kube-oidc-issuer-reflector.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- required "serviceAccount.name must be set when serviceAccount.create is false" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
