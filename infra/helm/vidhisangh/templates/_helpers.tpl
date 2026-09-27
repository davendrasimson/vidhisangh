{{/*
Expand the name of the chart.
*/}}
{{- define "vidhisangh.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "vidhisangh.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Chart name and version label.
*/}}
{{- define "vidhisangh.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "vidhisangh.labels" -}}
helm.sh/chart: {{ include "vidhisangh.chart" . }}
{{ include "vidhisangh.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: vidhisangh
{{- end -}}

{{/*
Selector labels (shared across components; component label added per-workload).
*/}}
{{- define "vidhisangh.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vidhisangh.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/*
Component fullnames.
*/}}
{{- define "vidhisangh.backend.fullname" -}}
{{- printf "%s-backend" (include "vidhisangh.fullname" .) -}}
{{- end -}}

{{- define "vidhisangh.frontend.fullname" -}}
{{- printf "%s-frontend" (include "vidhisangh.fullname" .) -}}
{{- end -}}

{{- define "vidhisangh.worker.fullname" -}}
{{- printf "%s-worker" (include "vidhisangh.fullname" .) -}}
{{- end -}}

{{/*
Fully qualified image reference: registry/repository:tag.
Usage: {{ include "vidhisangh.image" (dict "root" . "component" .Values.backend) }}
*/}}
{{- define "vidhisangh.image" -}}
{{- $tag := .component.image.tag | default .root.Values.image.tag | default .root.Chart.AppVersion -}}
{{- $digest := .component.image.digest | default "" -}}
{{- if $digest -}}
{{- printf "%s/%s:%s@%s" .root.Values.image.registry .component.image.repository $tag $digest -}}
{{- else -}}
{{- printf "%s/%s:%s" .root.Values.image.registry .component.image.repository $tag -}}
{{- end -}}
{{- end -}}
