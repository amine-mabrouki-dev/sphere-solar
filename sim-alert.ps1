# sim-alert.ps1 — Simulate an inverter alarm via MQTT
# Usage:
#   .\sim-alert.ps1          → alarm=7 (default)
#   .\sim-alert.ps1 101      → alarm=101
#   .\sim-alert.ps1 clear    → alarm=0 (clear all alerts)

param([string]$AlarmCode = "7")

$MQTT_HOST  = if ($env:MQTT_HOST)  { $env:MQTT_HOST }  else { "broker.hivemq.com" }
$MQTT_PORT  = if ($env:MQTT_PORT)  { $env:MQTT_PORT }  else { "1883" }
$SITE_ID    = if ($env:SITE_ID)    { $env:SITE_ID }    else { "1" }
$INV_SERIAL = if ($env:INV_SERIAL) { $env:INV_SERIAL } else { "SOLIS-S5GR3P12K-01" }

$alarm = if ($AlarmCode -eq "clear") { 0 } else { [int]$AlarmCode }
$ts    = [int][double]::Parse((Get-Date -UFormat %s))
$topic = "site/$SITE_ID/inv/$INV_SERIAL/telemetry"

$payload = @{
    site_id = [int]$SITE_ID
    inv     = $INV_SERIAL
    ts      = $ts
    pv_v    = 320.5
    pv_i    = 7.8
    pv_p    = 2500.0
    ac_v    = [math]::Round(230.0 + ((Get-Random -Minimum -50 -Maximum 50) / 10.0), 1)
    ac_i    = 10.8
    freq    = 50.0
    e_day   = 1.22
    e_total = 9001.5
    temp    = 45.0
    alarm   = $alarm
} | ConvertTo-Json -Compress

Write-Host "Publishing to $topic on ${MQTT_HOST}:$MQTT_PORT"
Write-Host "Payload: $payload"

py -3.12 -c @"
import paho.mqtt.publish as publish
publish.single(
    '$topic',
    payload='''$payload''',
    hostname='$MQTT_HOST',
    port=$MQTT_PORT,
    qos=1
)
print('Published OK')
"@
