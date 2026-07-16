{{- define "cmdb-core.fullname" -}}
{{- .Release.Name }}-cmdb-core
{{- end -}}

{{- define "cmdb-core.labels" -}}
app.kubernetes.io/name: cmdb-core
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "cmdb-core.secretName" -}}
{{- if .Values.existingSecret -}}
{{ .Values.existingSecret }}
{{- else -}}
{{ include "cmdb-core.fullname" . }}
{{- end -}}
{{- end -}}
